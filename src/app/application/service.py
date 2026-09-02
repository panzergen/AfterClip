from collections.abc import Callable
import datetime
import json
from pathlib import Path
import shutil
import time

from app.application.ports import CancelToken, MediaTool, ProcessingCancelled, TranscriptionProvider
from app.domain.models import ProgressEvent, TranscriptionRequest, TranscriptionResult
from app.infrastructure.process import get_media_metadata


class TranscriptionService:
    def __init__(self, provider: TranscriptionProvider, media_tool: MediaTool):
        self.provider = provider
        self.media_tool = media_tool

    def run(
        self,
        request: TranscriptionRequest,
        on_event: Callable[[ProgressEvent], None],
        cancel_token: CancelToken,
    ) -> TranscriptionResult:
        validate_request(request)
        job_dir = find_resumable_job_dir(request.output_dir, request.input_path.stem, request.input_path)
        if job_dir is None:
            job_dir = next_available_job_dir(request.output_dir, request.input_path.stem)
        transcript_dir = job_dir / "Transcripts"
        work_dir = job_dir / "temp"
        transcript_dir.mkdir(parents=True, exist_ok=True)
        work_dir.mkdir(parents=True, exist_ok=True)
        report_path = job_dir / "Summary_Report.md"
        state_path = job_dir / "job_state.json"
        state = load_state(state_path)
        steps = state.get("steps", {})
        metadata = get_media_metadata(request.input_path)
        write_report(report_path, request, "Running", metadata, steps)
        state.update({"status": "running", "user_task": request.user_task, "input_path": str(request.input_path), "steps": steps})
        save_state(state_path, state)

        if steps.get("media_preparation", {}).get("status") == "completed":
            audio_path = Path(state["audio_path"])
            if not audio_path.exists():
                steps.pop("media_preparation", None)
        if "audio_path" not in locals():
            audio_path = run_step(
                "media_preparation", "Media preparation", 5,
                lambda: self.media_tool.prepare_audio(request.input_path, work_dir, cancel_token, request.clip_start, request.clip_end),
                steps, state, state_path, report_path, request, metadata, on_event,
            )
            state["audio_path"] = str(audio_path)
            save_state(state_path, state)
        if cancel_token.is_cancelled():
            mark_finished(state, state_path, report_path, request, metadata, steps, "Cancelled")
            raise JobCancelled
        on_event(ProgressEvent("Transcription", 20))
        try:
            if steps.get("transcription", {}).get("status") == "completed":
                files = tuple(sorted(transcript_dir.glob(f"{audio_path.stem}.*")))
                if not files:
                    steps.pop("transcription", None)
                else:
                    result = TranscriptionResult(transcript_dir, files)
            if "result" not in locals():
                started = time.monotonic()
                steps["transcription"] = {"name": "Transcription", "status": "running"}
                save_state(state_path, {**state, "steps": steps, "current_step": "transcription"})
                write_report(report_path, request, "Running", metadata, steps)
                result = self.provider.transcribe(
                    TranscriptionRequest(audio_path, transcript_dir, request.model, request.language, request.user_task),
                    lambda message: on_event(ProgressEvent(message)),
                    cancel_token,
                )
                steps["transcription"] = {"name": "Transcription", "status": "completed", "duration_seconds": round(time.monotonic() - started, 2)}
                save_state(state_path, {**state, "steps": steps, "current_step": None})
                on_event(ProgressEvent(f"Transcription finished in {steps['transcription']['duration_seconds']} seconds", 95))
            if request.extract_frames:
                run_step(
                    "frame_extraction", "Frame extraction", 98,
                    lambda: self.media_tool.extract_interval_frames(
                        request.input_path, job_dir / "Vision" / "frames", request.frame_interval,
                        cancel_token, request.clip_start, request.clip_end,
                    ),
                    steps, state, state_path, report_path, request, metadata, on_event,
                )
        except ProcessingCancelled as error:
            mark_finished(state, state_path, report_path, request, metadata, steps, "Cancelled")
            raise JobCancelled from error
        except Exception:
            mark_finished(state, state_path, report_path, request, metadata, steps, "Failed")
            raise
        shutil.rmtree(work_dir, ignore_errors=True)
        mark_finished(state, state_path, report_path, request, metadata, steps, "Succeeded")
        on_event(ProgressEvent("Transcription complete", 100))
        return result


class JobCancelled(Exception):
    """Raised when the active job is cancelled between processing steps."""


def validate_request(request: TranscriptionRequest) -> None:
    if not request.input_path.is_file():
        raise ValueError(f"Input file was not found: {request.input_path}")
    if not request.model.strip():
        raise ValueError("A Whisper model is required.")
    if request.clip_start is not None and request.clip_start < 0:
        raise ValueError("Clip start cannot be negative.")
    if request.clip_end is not None and request.clip_end < 0:
        raise ValueError("Clip end cannot be negative.")
    if request.clip_start is not None and request.clip_end is not None and request.clip_end <= request.clip_start:
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
            if state.get("input_path") == str(input_path) and state.get("status") in {"cancelled", "failed", "running"}:
                return candidate
        except (OSError, json.JSONDecodeError):
            continue
    return None


def load_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"steps": {}}


def save_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def run_step(key, name, percent, action, steps, state, state_path, report_path, request, metadata, on_event):
    started = time.monotonic()
    steps[key] = {"name": name, "status": "running"}
    save_state(state_path, {**state, "steps": steps, "current_step": key})
    write_report(report_path, request, "Running", metadata, steps)
    on_event(ProgressEvent(name, percent))
    try:
        result = action()
    except ProcessingCancelled as error:
        steps[key] = {"name": name, "status": "cancelled", "duration_seconds": round(time.monotonic() - started, 2)}
        save_state(state_path, {**state, "steps": steps, "current_step": key, "status": "cancelled"})
        write_report(report_path, request, "Cancelled", metadata, steps)
        raise JobCancelled from error
    except Exception:
        steps[key] = {"name": name, "status": "failed", "duration_seconds": round(time.monotonic() - started, 2)}
        save_state(state_path, {**state, "steps": steps, "current_step": key, "status": "failed"})
        write_report(report_path, request, "Failed", metadata, steps)
        raise
    steps[key] = {"name": name, "status": "completed", "duration_seconds": round(time.monotonic() - started, 2)}
    save_state(state_path, {**state, "steps": steps, "current_step": None})
    write_report(report_path, request, "Running", metadata, steps)
    on_event(ProgressEvent(f"{name} finished in {steps[key]['duration_seconds']} seconds", percent))
    return result


def mark_finished(state, state_path, report_path, request, metadata, steps, status):
    state.update({"status": status, "steps": steps, "current_step": None})
    save_state(state_path, state)
    write_report(report_path, request, status, metadata, steps)


def write_report(path: Path, request: TranscriptionRequest, status: str, metadata: dict, steps: dict) -> None:
    stream_lines = []
    for stream in metadata.get("streams", []):
        stream_lines.append(", ".join(f"{key}={value}" for key, value in stream.items() if value is not None))
    step_lines = ["| Step | Status | Duration (seconds) |", "| --- | --- | ---: |"]
    for step in steps.values():
        step_lines.append(f"| {step.get('name', 'Unknown')} | {step.get('status', 'unknown')} | {step.get('duration_seconds', '')} |")
    path.write_text(
        "# AfterClip Processing Report\n\n"
        "## Input Media Metadata\n\n"
        f"- **File name:** `{metadata.get('file_name', request.input_path.name)}`\n"
        f"- **File size (MB):** `{metadata.get('file_size_mb', 'Unknown')}`\n"
        f"- **Duration (seconds):** `{metadata.get('duration', 'Unknown')}`\n"
        f"- **Format:** `{metadata.get('format', 'Unknown')}`\n"
        f"- **Bit rate:** `{metadata.get('bit_rate', 'Unknown')}`\n"
        f"- **Streams:** `{'; '.join(stream_lines) or 'Unknown'}`\n\n"
        "## Requested Task\n\n"
        f"{request.user_task or 'No additional task was requested.'}\n\n"
        "## Processing Steps\n\n"
        + "\n".join(step_lines) + "\n\n"
        f"- **Status:** `{status}`\n"
        f"- **Updated:** `{datetime.datetime.now().isoformat(timespec='seconds')}`\n"
        f"- **Input:** `{request.input_path}`\n"
        f"- **Model:** `{request.model}`\n"
        f"- **Language:** `{request.language or 'Auto-detect'}`\n"
        f"- **Clip range:** `{request.clip_start if request.clip_start is not None else 0} -> {request.clip_end if request.clip_end is not None else 'end'}`\n",
        encoding="utf-8",
    )
