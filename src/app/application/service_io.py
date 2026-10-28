import datetime
import hashlib
import json
import logging
import re
from pathlib import Path

from app.application.timeline import find_transcript_srt, parse_srt
from app.application.vision_sanitizer import VisionSanitizerConfig, sanitize_description
from app.domain.models import TranscriptionRequest
from app.infrastructure.atomic_file import atomic_write_text as write_atomic_text

LOGGER = logging.getLogger(__name__)

SCENE_TIMESTAMP_PATTERN = re.compile(r"(\d{2})h(\d{2})m(\d{2})s")
INTERVAL_FRAME_PATTERN = re.compile(r"interval_(\d+)$")
HIGHLIGHT_FRAME_PATTERN = re.compile(r"highlight_(\d+)$")


def atomic_write_text(path: Path, text: str) -> None:
    """Write text via a temp file + replace so a crash cannot truncate it."""
    write_atomic_text(path, text)


def validate_request(request: TranscriptionRequest) -> None:
    if not request.input_path.is_file():
        raise ValueError(f"Input file was not found: {request.input_path}")
    if not request.model.strip():
        raise ValueError("A Whisper model is required.")
    if request.clip_start is not None and request.clip_start < 0:
        raise ValueError("Clip start cannot be negative.")
    if request.clip_end is not None and request.clip_end < 0:
        raise ValueError("Clip end cannot be negative.")
    if (
        request.clip_start is not None
        and request.clip_end is not None
        and request.clip_end <= request.clip_start
    ):
        raise ValueError("Clip end must be greater than clip start.")


def parse_clip_time(value: str) -> float | None:
    text = value.strip()
    if not text:
        return None
    try:
        parts = [float(part) for part in text.split(":")]
    except ValueError as error:
        raise ValueError("Clip times must use seconds, MM:SS, or HH:MM:SS.") from error
    if len(parts) == 1:
        result = parts[0]
    elif len(parts) == 2:
        result = parts[0] * 60 + parts[1]
    elif len(parts) == 3:
        result = parts[0] * 3600 + parts[1] * 60 + parts[2]
    else:
        raise ValueError("Clip times must use seconds, MM:SS, or HH:MM:SS.")
    if result < 0:
        raise ValueError("Clip times cannot be negative.")
    return result


def next_available_job_dir(output_dir: Path, base_name: str) -> Path:
    candidate = output_dir / base_name
    if not candidate.exists():
        return candidate
    number = 1
    while True:
        candidate = output_dir / f"{base_name}{number}"
        if not candidate.exists():
            return candidate
        number += 1


def find_resumable_job_dir(output_dir: Path, base_name: str, input_path: Path) -> Path | None:
    candidates = [path for path in output_dir.glob(f"{base_name}*") if path.is_dir()]
    for candidate in sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True):
        state_path = candidate / "job_state.json"
        if not state_path.exists():
            continue
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            if state.get("input_path") == str(input_path) and state.get("status") in {
                "cancelled",
                "failed",
                "running",
            }:
                return candidate
        except (OSError, json.JSONDecodeError):
            continue
    return None


def find_reusable_job_dir(output_dir: Path, input_path: Path) -> Path | None:
    """Most recent job folder for this exact input with a completed transcription.

    Used by the optional "reuse existing transcription" run mode: the folder is
    matched by the input path recorded in its ``job_state.json``, so outputs
    are never mixed between different source files.
    """
    if not output_dir.is_dir():
        return None
    target = str(input_path)
    matches: list[tuple[float, Path, dict]] = []
    for state_path in output_dir.glob("*/job_state.json"):
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if state.get("input_path") != target:
            continue
        matches.append((state_path.stat().st_mtime, state_path.parent, state))
    for _, job_dir, state in sorted(matches, key=lambda item: item[0], reverse=True):
        completed = state.get("steps", {}).get("transcription", {}).get("status") == "completed"
        if completed and any((job_dir / "Transcripts").glob("*.srt")):
            return job_dir
    return None


def load_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"steps": {}}


def save_state(path: Path, state: dict) -> None:
    atomic_write_text(path, json.dumps(state, ensure_ascii=False, indent=2))


def srt_transcript_text(srt_path: Path | None) -> str:
    if not srt_path:
        return ""
    return "\n".join(entry.text for entry in parse_srt(srt_path, "TRANSCRIPTION"))


def detect_transcript_language(transcript_dir: Path, audio_stem: str) -> str:
    """Whisper-detected language code from ``<stem>.json`` ("" when unavailable).

    Whisper's JSON output carries the detected (or forced) language, so this is
    the video's actual spoken language even when the user left the language
    hint on auto-detect.
    """
    candidate = transcript_dir / f"{audio_stem}.json"
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    code = str(payload.get("language", "")).strip().lower().replace("_", "-").split("-")[0]
    if len(code) in (2, 3) and code.isalpha():
        return code
    return ""


def resolve_report_language(request, transcript_dir: Path | None = None, audio_stem: str = "") -> str:
    """Language code for summaries/highlights/vision/topics.

    Precedence: explicit report language, else Whisper-detected video language,
    else the transcription hint, else English. This keeps unconfigured jobs in
    the video's language instead of silently defaulting to English.
    """
    selected = (getattr(request, "output_language", "") or "").strip()
    if selected:
        return selected
    if transcript_dir is not None:
        detected = detect_transcript_language(transcript_dir, audio_stem)
        if detected:
            return detected
    hint = (getattr(request, "language", "") or "").strip()
    return hint or "en"


def prompt_set_fingerprint(prompt_set) -> str:
    """Stable hash of a PromptSet's templates ("" when unavailable).

    Stored in ``job_state.json`` when an analysis step completes so a resumed
    job can tell whether the prompts changed since and must re-run instead of
    reusing stale outputs.
    """
    to_dict = getattr(prompt_set, "to_dict", None)
    if not callable(to_dict):
        return ""
    try:
        payload = json.dumps(to_dict(), ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return ""
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def frame_window(frame: Path, frame_interval: int) -> float:
    """Display duration of one frame's timeline entry (seconds)."""
    if frame.stem.startswith("interval") and "highlight" not in frame.stem:
        return max(1.0, float(frame_interval))
    return 5.0


def frame_timestamp(
    frame: Path, frame_interval: int, clip_start: float | None, highlight_times: tuple[float, ...]
) -> float:
    """Recover a frame's media timestamp from its extracted file name.

    Highlight frames map back to the user's marked times; scene frames carry
    an HHhMMmSSs stamp (relative to the clip seek); interval frames are
    index * interval past the clip start.
    """
    name = frame.stem
    highlight_match = HIGHLIGHT_FRAME_PATTERN.search(name)
    if highlight_match:
        index = int(highlight_match.group(1)) - 1
        return float(highlight_times[index]) if 0 <= index < len(highlight_times) else 0.0
    offset = float(clip_start or 0.0)
    scene_match = SCENE_TIMESTAMP_PATTERN.search(name)
    if scene_match:
        hours, minutes, seconds = (int(part) for part in scene_match.groups())
        return offset + hours * 3600 + minutes * 60 + seconds
    interval_match = INTERVAL_FRAME_PATTERN.search(name)
    if interval_match:
        return offset + int(interval_match.group(1)) * max(1, frame_interval)
    return 0.0


def transcript_context(transcript_dir: Path, audio_stem: str, timestamp: float) -> str:
    """Transcript text spoken at `timestamp`; falls back to the nearest entry."""
    srt_path = find_transcript_srt(transcript_dir, audio_stem)
    if srt_path is None:
        return ""
    entries = parse_srt(srt_path, "TRANSCRIPTION")
    if not entries:
        return ""
    timestamp_ms = int(timestamp * 1000)
    overlapping = [
        entry.text for entry in entries if entry.start_ms <= timestamp_ms <= entry.end_ms
    ]
    if overlapping:
        return " ".join(overlapping)
    preceding = [entry for entry in entries if entry.end_ms <= timestamp_ms]
    if preceding:
        return preceding[-1].text
    return entries[0].text


def srt_timestamp(seconds: float) -> str:
    total_ms = max(0, round(seconds * 1000))
    hours, remainder = divmod(total_ms, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def write_fallback_vision_srt(
    job_dir: Path, frame_interval: int, clip_start: float | None, highlight_times: tuple[float, ...]
) -> Path | None:
    """Vision SRT for extracted frames without AI descriptions.

    Guarantees extracted frames appear in the master timeline even when the
    vision step never ran; a later vision run overwrites this file.
    """
    frames_dir = job_dir / "Vision" / "frames"
    frames = sorted(frames_dir.glob("*.png")) if frames_dir.is_dir() else ()
    if not frames:
        return None
    vision_dir = job_dir / "Vision"
    vision_dir.mkdir(parents=True, exist_ok=True)
    srt_path = vision_dir / "vision_analysis.srt"
    with srt_path.open("w", encoding="utf-8") as vision_srt:
        for number, frame in enumerate(frames, 1):
            timestamp = frame_timestamp(frame, frame_interval, clip_start, highlight_times)
            window = frame_window(frame, frame_interval)
            vision_srt.write(
                f"{number}\n"
                f"{srt_timestamp(timestamp)} --> {srt_timestamp(timestamp + window)}\n"
                f"FILE: {frame.name}\n"
                f"DESCRIPTION: (no AI description)\n\n"
            )
    return srt_path


VISION_FILE_LINE = re.compile(r"FILE:\s*(.+)")
VISION_DESCRIPTION_LINE = re.compile(r"DESCRIPTION:\s*([\s\S]+)")


def parse_vision_descriptions(
    srt_path: Path | None, config: VisionSanitizerConfig | None = None
) -> dict[str, str]:
    """Map frame file name -> AI description from a vision SRT (empty when absent).

    Descriptions are run through the vision sanitizer on read, so a stale cache
    written before the sanitizer existed is still cleaned for the timeline
    without re-running the vision model.
    """
    if not srt_path:
        return {}
    path = Path(srt_path)
    if not path.is_file():
        return {}
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {}
    descriptions: dict[str, str] = {}
    for block in re.split(r"\n\s*\n", content):
        file_match = VISION_FILE_LINE.search(block)
        if not file_match:
            continue
        description_match = VISION_DESCRIPTION_LINE.search(block)
        raw = description_match.group(1).strip() if description_match else ""
        descriptions[file_match.group(1).strip()] = sanitize_description(raw, config).text
    return descriptions


def write_vision_timeline_srt(
    job_dir: Path,
    frame_interval: int,
    clip_start: float | None,
    highlight_times: tuple[float, ...],
    descriptions: dict[str, str] | None = None,
) -> Path | None:
    """Vision SRT covering every extracted frame for the master timeline.

    Descriptions from a partial AI run are kept by frame name; frames without
    one are listed with a placeholder so no extracted frame is dropped.
    """
    frames_dir = job_dir / "Vision" / "frames"
    frames = sorted(frames_dir.glob("*.png")) if frames_dir.is_dir() else ()
    if not frames:
        return None
    lookup = descriptions or {}
    path = job_dir / "Vision" / "timeline_frames.srt"
    with path.open("w", encoding="utf-8") as vision_srt:
        for number, frame in enumerate(frames, 1):
            timestamp = frame_timestamp(frame, frame_interval, clip_start, highlight_times)
            window = frame_window(frame, frame_interval)
            description = lookup.get(frame.name) or "(no AI description)"
            vision_srt.write(
                f"{number}\n"
                f"{srt_timestamp(timestamp)} --> {srt_timestamp(timestamp + window)}\n"
                f"FILE: {frame.name}\n"
                f"DESCRIPTION: {description}\n\n"
            )
    return path


def write_report(
    path: Path, request: TranscriptionRequest, status: str, metadata: dict, steps: dict
) -> None:
    stream_lines = []
    for stream in metadata.get("streams", []):
        stream_lines.append(
            ", ".join(f"{key}={value}" for key, value in stream.items() if value is not None)
        )
    step_lines = ["| Step | Status | Duration (seconds) |", "| --- | --- | ---: |"]
    for step in steps.values():
        step_lines.append(
            f"| {step.get('name', 'Unknown')} | {step.get('status', 'unknown')} "
            f"| {step.get('duration_seconds', '')} |"
        )
    usage = metadata.get("cloud_usage")
    usage_lines = ""
    if usage:
        cost = usage.get("estimated_cost_usd")
        cost_text = f"${cost}" if cost is not None else "unavailable for this model"
        usage_lines = (
            "\n## Cloud Usage (approximate)\n\n"
            f"- **Provider:** `{usage.get('provider', '')}`\n"
            f"- **Model:** `{usage.get('model', '')}`\n"
            f"- **Requests:** `{usage.get('requests', 0)}`\n"
            f"- **Input tokens:** `{usage.get('input_tokens', 0)}`\n"
            f"- **Output tokens:** `{usage.get('output_tokens', 0)}`\n"
            f"- **Images sent:** `{usage.get('images', 0)}`\n"
            f"- **Estimated cost:** {cost_text}\n"
            f"- **Note:** {usage.get('cost_note', 'Approximate; provider pricing applies.')}\n"
        )
    media_guess = metadata.get("media_type") if isinstance(metadata.get("media_type"), dict) else {}
    media_type_line = ""
    if media_guess:
        media_type_line = (
            f"- **Media type:** `{media_guess.get('media_type', 'unknown')}` "
            f"(confidence {media_guess.get('confidence', 0)}, {media_guess.get('tier', '')})\n"
        )
    clip_start = request.clip_start if request.clip_start is not None else 0
    clip_end = request.clip_end if request.clip_end is not None else "end"
    content = (
        "# AfterClip Processing Report\n\n"
        "- **Report version:** `1`\n\n"
        "## Input Media Metadata\n\n"
        f"- **File name:** `{metadata.get('file_name', request.input_path.name)}`\n"
        f"- **File size (MB):** `{metadata.get('file_size_mb', 'Unknown')}`\n"
        f"- **Duration (seconds):** `{metadata.get('duration', 'Unknown')}`\n"
        f"- **Creation date:** `{metadata.get('creation_date', 'Unknown')}`\n"
        f"- **Format:** `{metadata.get('format', 'Unknown')}`\n"
        f"- **Bit rate:** `{metadata.get('bit_rate', 'Unknown')}`\n"
        f"{media_type_line}"
        f"- **Streams:** `{'; '.join(stream_lines) or 'Unknown'}`\n\n"
        "## Requested Task\n\n"
        f"{request.user_task or 'No additional task was requested.'}\n\n"
        "## Processing Steps\n\n" + "\n".join(step_lines) + "\n\n"
        f"- **Status:** `{status}`\n"
        f"- **Updated:** `{datetime.datetime.now().isoformat(timespec='seconds')}`\n"
        f"- **Input:** `{request.input_path}`\n"
        f"- **Output name:** `{request.output_name or request.input_path.stem}`\n"
        f"- **Model:** `{request.model}`\n"
        f"- **Language:** `{request.language or 'Auto-detect'}`\n"
        f"- **Clip range:** `{clip_start} -> {clip_end}`\n"
        f"{usage_lines}"
    )
    atomic_write_text(path, content)
