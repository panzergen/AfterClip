import base64
import datetime
import html as html_module
import io
import json
import logging
import re
from pathlib import Path
from urllib.parse import quote

from app.application.markdown_html import render_markdown
from app.application.summary import clean_summary_output
from app.domain.models import SpeakerInterval, TimelineEntry

LOGGER = logging.getLogger(__name__)

VTT_TIME = r"(?:\d{2}:)?\d{2}:\d{2}[.,]\d{3}"
VTT_TIMESTAMP_PATTERN = re.compile(rf"({VTT_TIME})\s*-->\s*({VTT_TIME})")
SRT_TIMESTAMP_PATTERN = re.compile(r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})")
SPEAKER_TAG_PATTERN = re.compile(r"<v\s+([^>]+)>")
BRACKET_SPEAKER_PATTERN = re.compile(r"^\s*\[([^\]]+)\]\s*:?\s*")
EXPLICIT_SPEAKER_PATTERN = re.compile(
    r"^\s*(?:speaker|spk)\s*[_\- ]?\s*([^:]+?)\s*:\s*",
    re.IGNORECASE,
)
NAME_SPEAKER_PATTERN = re.compile(
    r"^\s*([A-ZÀ-ÖØ-Ý][\wÀ-ÖØ-öø-ÿ.-]*(?:\s+[A-ZÀ-ÖØ-Ý][\wÀ-ÖØ-öø-ÿ.-]*){1,3})\s*:\s*"
)
VISION_FILE_PATTERN = re.compile(r"FILE:\s*([^\n]+)")
VISION_DESCRIPTION_PATTERN = re.compile(r"DESCRIPTION:\s*([\s\S]+)")


def timestamp_to_ms(timestamp: str, millisecond_separator: str) -> int:
    parts = timestamp.split(":")
    if len(parts) == 2:
        hours = 0
        minutes, second_part = parts
    else:
        hours, minutes, second_part = parts
    seconds, millis = second_part.replace(",", ".").split(".")
    return int(hours) * 3600000 + int(minutes) * 60000 + int(seconds) * 1000 + int(millis)


def vtt_duration_seconds(vtt_path: Path | str | None) -> float | None:
    """End timestamp of the last WebVTT cue, or None when it cannot be read.

    Unlike ``parse_speaker_vtt`` this does not require speaker tags: it is used
    to check whether a supplied transcript file covers the whole media file.
    """
    if not vtt_path:
        return None
    path = Path(vtt_path)
    if not path.is_file():
        return None
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    ends: list[int] = []
    for timestamp_match in VTT_TIMESTAMP_PATTERN.finditer(content):
        try:
            ends.append(timestamp_to_ms(timestamp_match.group(2), "."))
        except (ValueError, IndexError):
            continue
    return max(ends) / 1000.0 if ends else None


def parse_speaker_vtt(vtt_path: Path | str | None) -> tuple[SpeakerInterval, ...]:
    """Parse a WebVTT file carrying ``<v Speaker>`` tags.

    Malformed or missing files never raise: the job continues without
    speaker information (T15 policy).
    """
    if not vtt_path:
        return ()
    path = Path(vtt_path)
    if not path.is_file():
        LOGGER.warning("Speaker VTT file was not found: %s", path)
        return ()
    intervals: list[SpeakerInterval] = []
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as error:
        LOGGER.warning("Speaker VTT could not be read: %s", error)
        return ()
    for block in re.split(r"\n\s*\n", content.strip()):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        timestamp_index = next(
            (index for index, line in enumerate(lines) if "-->" in line),
            None,
        )
        if timestamp_index is None:
            continue
        timestamp_match = VTT_TIMESTAMP_PATTERN.search(lines[timestamp_index])
        if not timestamp_match:
            continue
        raw_text = " ".join(lines[timestamp_index + 1 :]).strip()
        speaker = _extract_speaker(raw_text)
        if not speaker and timestamp_index:
            speaker = _extract_cue_speaker(lines[timestamp_index - 1])
        if not speaker:
            continue
        try:
            intervals.append(
                SpeakerInterval(
                    timestamp_to_ms(timestamp_match.group(1), "."),
                    timestamp_to_ms(timestamp_match.group(2), "."),
                    speaker,
                )
            )
        except (ValueError, IndexError):
            continue
    if intervals:
        LOGGER.info("Loaded %d speaker interval(s) from %s", len(intervals), path.name)
    else:
        LOGGER.warning("No speaker labels found in VTT file: %s", path)
    return tuple(intervals)


def _extract_speaker(text: str) -> str:
    tag_match = SPEAKER_TAG_PATTERN.search(text)
    if tag_match:
        return SPEAKER_TAG_PATTERN.sub("", tag_match.group(1)).strip()
    for pattern in (BRACKET_SPEAKER_PATTERN, EXPLICIT_SPEAKER_PATTERN, NAME_SPEAKER_PATTERN):
        match = pattern.match(text)
        if match:
            speaker = match.group(1).strip()
            if speaker:
                return speaker
    return ""


def _extract_cue_speaker(text: str) -> str:
    """Extract a speaker name used as a WebVTT cue identifier."""
    label = text.strip()
    if not label or label.lower() == "webvtt" or label.isdigit():
        return ""
    if re.fullmatch(r"(?:speaker|spk)[_\s-]*[\w.-]+", label, re.IGNORECASE):
        return label
    if re.fullmatch(r"[A-ZÀ-ÖØ-Ý][\wÀ-ÖØ-öø-ÿ.-]*(?:\s+[A-ZÀ-ÖØ-Ý][\wÀ-ÖØ-öø-ÿ.-]*){0,3}", label):
        return label
    return ""


def parse_srt(srt_path: Path, context_type: str) -> tuple[TimelineEntry, ...]:
    """Parse an SRT subtitle file into timeline entries."""
    entries: list[TimelineEntry] = []
    try:
        content = srt_path.read_text(encoding="utf-8", errors="ignore")
    except OSError as error:
        LOGGER.warning("Subtitle file could not be read: %s", error)
        return ()
    parts = SRT_TIMESTAMP_PATTERN.split(content)
    for index in range(1, len(parts) - 2, 3):
        text = re.sub(r"\n+\d+$", "", parts[index + 2].strip()).strip()
        if not text:
            continue
        try:
            entries.append(
                TimelineEntry(
                    timestamp_to_ms(parts[index], ","),
                    timestamp_to_ms(parts[index + 1], ","),
                    parts[index],
                    parts[index + 1],
                    context_type,
                    text,
                )
            )
        except (ValueError, IndexError):
            continue
    return tuple(entries)


def resolve_speaker(
    intervals: tuple[SpeakerInterval, ...], start_ms: int, end_ms: int
) -> str | None:
    """Return the speaker with the greatest overlap for an interval."""
    best_speaker = None
    max_overlap = 0
    for interval in intervals:
        overlap = min(end_ms, interval.end_ms) - max(start_ms, interval.start_ms)
        if overlap > max_overlap and interval.speaker:
            max_overlap = overlap
            best_speaker = interval.speaker
    return best_speaker


def find_transcript_srt(transcript_dir: Path, audio_stem: str) -> Path | None:
    """Locate the transcription SRT produced for the prepared audio."""
    candidates = [transcript_dir / f"{audio_stem}.srt", transcript_dir / "converted_audio.srt"]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    for candidate in sorted(transcript_dir.glob("*.srt")):
        if candidate.name.endswith(".raw.srt") or candidate.stem.endswith("_vision_analysis"):
            continue
        return candidate
    return None


def find_vision_srt(job_dir: Path, base_name: str) -> Path | None:
    for candidate in (
        job_dir / "Vision" / "vision_analysis.srt",
        job_dir / f"{base_name}_vision_analysis.srt",
    ):
        if candidate.is_file():
            return candidate
    return None


def merge_transcript_entries(
    entries: tuple[TimelineEntry, ...],
    max_seconds: float,
    speaker_intervals: tuple[SpeakerInterval, ...] = (),
) -> tuple[TimelineEntry, ...]:
    """Merge consecutive transcript entries into blocks of at most `max_seconds`.

    A speaker change (from the speaker VTT) always starts a new block even
    before the time limit; without speaker information the merge is purely
    time-based.
    """
    merged: list[TimelineEntry] = []
    current_speaker: object = _UNSET
    for entry in entries:
        speaker = resolve_speaker(speaker_intervals, entry.start_ms, entry.end_ms)
        if (
            merged
            and (entry.end_ms - merged[-1].start_ms) <= max_seconds * 1000
            and speaker == current_speaker
        ):
            first = merged.pop()
            merged.append(
                TimelineEntry(
                    first.start_ms,
                    entry.end_ms,
                    first.start_str,
                    entry.end_str,
                    first.context_type,
                    f"{first.text} {entry.text}".strip(),
                )
            )
        else:
            merged.append(entry)
        current_speaker = speaker
    return tuple(merged)


_UNSET = object()


def _format_seconds(value) -> str:
    try:
        total = int(float(value))
    except (TypeError, ValueError):
        return str(value or "Unknown")
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def _format_milliseconds(value: int) -> str:
    seconds = max(0, int(value)) / 1000.0
    whole = int(seconds)
    millis = round((seconds - whole) * 1000)
    return f"{whole // 3600:02d}:{(whole % 3600) // 60:02d}:{whole % 60:02d},{millis:03d}"


def _coverage_status(metadata: dict, entries: list[TimelineEntry], clip_end: float | None) -> str:
    coverage_end = max((entry.end_ms for entry in entries), default=0) / 1000.0
    expected_end: float | None = None
    if clip_end is not None:
        expected_end = float(clip_end)
    else:
        try:
            expected_end = float(metadata.get("duration"))
        except (TypeError, ValueError):
            expected_end = None
    if expected_end is None or expected_end <= 0:
        return "coverage end unknown"
    # Trailing silence can end the last entry slightly before the container
    # duration; only call it incomplete when more than 5% (or 30 s) is missing.
    tolerance = max(30.0, expected_end * 0.05)
    if coverage_end >= expected_end - tolerance:
        return "complete"
    missing = expected_end - coverage_end
    return f"incomplete — timeline ends {_format_seconds(missing)} before the expected end"


def _source_metadata_lines(
    metadata: dict,
    report_language: str,
    transcript_language: str,
    clip_start: float | None,
    clip_end: float | None,
    entries: list[TimelineEntry],
    transcript_count: int,
    vision_count: int,
    topic_count: int,
) -> list[str]:
    """A compact, AI-readable provenance block for Master_Timeline.md."""
    media_type = metadata.get("media_type") if isinstance(metadata.get("media_type"), dict) else {}
    file_name = str(metadata.get("file_name") or "Unknown")
    creation_date = str(metadata.get("creation_date") or "Unknown")
    duration = _format_seconds(metadata.get("duration"))
    media_label = str(media_type.get("media_type") or "Unknown")
    confidence = media_type.get("confidence")
    if confidence is not None:
        media_label += f" (confidence {confidence})"
    clip_label = (
        "Full file"
        if clip_start is None and clip_end is None
        else f"{clip_start or 0} --> {clip_end if clip_end is not None else 'end'}"
    )
    coverage_end = max((entry.end_ms for entry in entries), default=0)
    coverage_status = _coverage_status(metadata, entries, clip_end)
    generated = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    lines = [
        f"> **Source file:** `{file_name}`  \n",
        f"> **Source creation date:** `{creation_date}`  \n",
        f"> **Duration:** `{duration}`  \n",
        f"> **Media type:** {media_label}  \n",
        f"> **File size:** `{metadata.get('file_size_mb', 'Unknown')} MB`  \n",
        f"> **Format:** `{metadata.get('format', 'Unknown')}`  \n",
        f"> **Clip range:** `{clip_label}`  \n",
        f"> **Transcription language:** `{transcript_language or 'Unknown'}`  \n",
        f"> **Report language:** `{report_language or 'Unknown'}`  \n",
        f"> **Generated:** `{generated}`  \n",
        f"> **Coverage:** `00:00:00,000 --> {_format_milliseconds(coverage_end)}` · "
        f"{coverage_status} · {transcript_count} transcription blocks · "
        f"{vision_count} vision frames · {topic_count} topic sections  \n",
        "> **Related files:** `AI_Analysis.md`, `Topics.md`, `Summary_Report.md`, "
        "`multimodal_timeline.jsonl`, `multimodal_timeline.meta.json`, "
        "`FullReportAndTimeline.htm`, `Transcripts/converted_audio.txt`, "
        "`Transcripts/converted_audio.srt`, `Vision/frames/`\n\n",
    ]
    return lines


def write_master_timeline(
    job_dir: Path,
    transcript_srt: Path | None,
    vision_srt: Path | None,
    speaker_intervals: tuple[SpeakerInterval, ...],
    embed_frames: bool = False,
    transcript_merge_seconds: float | None = None,
    analysis_markdown: str | None = None,
    topics: tuple = (),
    source_metadata: dict | None = None,
    report_language: str = "",
    transcript_language: str = "",
    clip_start: float | None = None,
    clip_end: float | None = None,
    html_mode: str = "",
    source_video_uri: str = "",
) -> tuple[Path, Path]:
    """Write ``Master_Timeline.md`` and ``multimodal_timeline.jsonl``.

    The Markdown stays lean for AI consumption: relative frame paths only, no
    binary data. Topic sections add ``## title`` headings. The HTML report mode
    is ``lean`` (external frame links), ``thumbnails`` (small embedded previews),
    ``full`` (original frames embedded) or ``none``.
    """
    all_entries: list[TimelineEntry] = []
    if transcript_srt:
        all_entries.extend(parse_srt(transcript_srt, "TRANSCRIPTION"))
    if vision_srt:
        all_entries.extend(parse_srt(vision_srt, "VISION"))
    transcript_entries = [entry for entry in all_entries if entry.context_type != "VISION"]
    vision_entries = [entry for entry in all_entries if entry.context_type == "VISION"]
    if transcript_merge_seconds and transcript_merge_seconds > 0:
        transcript_entries = list(
            merge_transcript_entries(
                tuple(transcript_entries), transcript_merge_seconds, speaker_intervals
            )
        )
    entries = sorted(transcript_entries + vision_entries, key=lambda entry: entry.start_ms)
    timeline_path = job_dir / "Master_Timeline.md"
    jsonl_path = job_dir / "multimodal_timeline.jsonl"
    payloads: list[dict] = []
    topic_list = list(topics)
    metadata = source_metadata or {}
    markdown_lines = [
        "# Master Chronological Timeline\n\n",
        *_source_metadata_lines(
            metadata,
            report_language,
            transcript_language,
            clip_start,
            clip_end,
            entries,
            len(transcript_entries),
            len(vision_entries),
            len(topic_list),
        ),
        "## How to read this timeline\n\n",
        "- Entries are ordered by **start time**. A `TRANSCRIPTION` entry and a "
        "`VISION` entry can overlap; vision time is the frame timestamp, not a "
        "separate speech event.\n",
        "- A `TRANSCRIPTION` entry is the cleaned Whisper transcript. A "
        "`SPEAKER: name` label comes from the supplied VTT or voiceprints; it is "
        "absent when no diarization source was supplied.\n",
        "- The transcript is machine-generated ASR. Treat names and technical "
        "terms as potentially misspelled unless they also appear in a vision "
        "description.\n",
        "- A `VISION` entry describes a screen frame. The image link is relative to "
        "this job folder. `[unreadable]` means the text could not be read; "
        "`(no visible screen content)` means the frame had no usable screen content.\n",
        "- `##` headings are topic sections, not timeline entries. Each heading "
        "includes its topic time range. Cite an entry by its start timestamp.\n",
        "- Timestamps use `HH:MM:SS,mmm`, relative to the source file (or the "
        "selected clip start).\n",
        "- The machine-readable companion is `multimodal_timeline.jsonl` "
        "(one JSON object per line).\n\n---\n\n",
    ]
    mode = html_mode if html_mode in {"lean", "thumbnails", "full", "none"} else ""
    if not mode:
        mode = "full" if embed_frames else "lean"
    topic_index = 0
    html_path = job_dir / "FullReportAndTimeline.htm"
    # Stream the HTML report instead of accumulating every embedded frame in
    # memory: a large job otherwise holds all base64 frames at once.
    html_file = None
    if mode != "none":
        summary, highlights = split_ai_analysis(analysis_markdown or "")
        topics_summary = "\n".join(
            f"- `[{topic.start_str} --> {topic.end_str}]` {topic.title}" for topic in topic_list
        )
        html_file = html_path.open("w", encoding="utf-8")
        html_file.write(_html_head(str(metadata.get("file_name") or "")))
        html_file.write(
            _html_report_sections(
                summary,
                highlights,
                topics_summary,
                metadata=metadata,
                report_language=report_language,
                transcript_language=transcript_language,
                clip_start=clip_start,
                clip_end=clip_end,
            )
        )
        html_file.write(
            _html_video_player(
                source_video_uri,
                str(metadata.get("file_name") or ""),
            )
        )
        html_file.write("<h2>Timeline</h2>")
    else:
        html_path.unlink(missing_ok=True)
    for entry in entries:
        while topic_index < len(topic_list) and entry.start_ms >= topic_list[topic_index].start_ms:
            topic = topic_list[topic_index]
            markdown_lines.append(
                f"\n## [{topic.start_str} --> {topic.end_str}] {topic.title}\n\n"
            )
            if html_file is not None:
                html_file.write(
                    "<h2 class='topic'>"
                    f"{html_module.escape(topic.title)}"
                    f"<span class='badge'>[{html_module.escape(topic.start_str)} --&gt; "
                    f"{html_module.escape(topic.end_str)}]</span></h2>"
                )
            topic_index += 1
        payload, html_row, lines = _render_entry(entry, speaker_intervals, job_dir, mode)
        if html_file is not None:
            html_file.write(html_row)
        payloads.append(payload)
        markdown_lines.extend(lines)
    timeline_path.write_text("".join(markdown_lines), encoding="utf-8")
    _write_jsonl(jsonl_path, payloads)
    _write_timeline_meta(
        job_dir / "multimodal_timeline.meta.json",
        metadata,
        report_language,
        transcript_language,
        clip_start,
        clip_end,
        entries,
        len(transcript_entries),
        len(vision_entries),
        len(topic_list),
    )
    if html_file is not None:
        html_file.write(_html_seek_script())
        html_file.write("</body></html>")
        html_file.close()
    return timeline_path, jsonl_path


def _write_jsonl(jsonl_path: Path, payloads: list[dict]) -> None:
    with jsonl_path.open("w", encoding="utf-8") as jsonl:
        for payload in payloads:
            jsonl.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _write_timeline_meta(
    path: Path,
    metadata: dict,
    report_language: str,
    transcript_language: str,
    clip_start: float | None,
    clip_end: float | None,
    entries: list[TimelineEntry],
    transcript_count: int,
    vision_count: int,
    topic_count: int,
) -> None:
    """Machine-readable provenance for the JSONL timeline."""
    media_type = metadata.get("media_type") if isinstance(metadata.get("media_type"), dict) else {}
    duration = metadata.get("duration")
    expected_end_seconds = clip_end
    if expected_end_seconds is None:
        try:
            expected_end_seconds = float(duration)
        except (TypeError, ValueError):
            expected_end_seconds = None
    coverage_end_ms = max((entry.end_ms for entry in entries), default=0)
    payload = {
        "schema_version": 1,
        "generated_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": {
            "file_name": metadata.get("file_name") or "Unknown",
            "creation_date": metadata.get("creation_date") or "Unknown",
            "duration_seconds": duration,
            "file_size_mb": metadata.get("file_size_mb"),
            "format": metadata.get("format"),
            "bit_rate": metadata.get("bit_rate"),
            "media_type": media_type.get("media_type"),
            "media_type_confidence": media_type.get("confidence"),
        },
        "languages": {
            "transcription": transcript_language or None,
            "report": report_language or None,
        },
        "clip": {"start_seconds": clip_start, "end_seconds": clip_end},
        "coverage": {
            "start_ms": 0,
            "end_ms": coverage_end_ms,
            "expected_end_ms": int(expected_end_seconds * 1000)
            if expected_end_seconds is not None
            else None,
            "status": _coverage_status(metadata, entries, clip_end),
            "entries": len(entries),
            "transcription_blocks": transcript_count,
            "vision_frames": vision_count,
            "topic_sections": topic_count,
        },
        "related_files": [
            "Master_Timeline.md",
            "multimodal_timeline.jsonl",
            "AI_Analysis.md",
            "Topics.md",
            "Summary_Report.md",
            "FullReportAndTimeline.htm",
            "Transcripts/converted_audio.txt",
            "Transcripts/converted_audio.srt",
            "Vision/frames/",
        ],
        "entry_schema": {
            "timestamp_start_ms": "integer",
            "timestamp_end_ms": "integer",
            "event_type": "transcription | vision",
            "transcription": {"speaker": "string | null", "text": "string"},
            "vision": {"frame_path": "string | null", "description": "string"},
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _render_entry(
    entry: TimelineEntry,
    speaker_intervals: tuple[SpeakerInterval, ...],
    job_dir: Path,
    html_mode: str,
):
    """One entry -> (jsonl payload, html row, markdown lines)."""
    speaker = resolve_speaker(speaker_intervals, entry.start_ms, entry.end_ms)
    speaker_badge = f" `[SPEAKER: {speaker}]`" if speaker else ""
    start_badge = f"[{entry.start_str} --> {entry.end_str}]"
    play_button = (
        f"<button class='play' type='button' data-start-ms='{entry.start_ms}'>"
        "▶ Play from here</button>"
    )
    if entry.context_type == "VISION":
        file_match = VISION_FILE_PATTERN.search(entry.text)
        description_match = VISION_DESCRIPTION_PATTERN.search(entry.text)
        frame_name = file_match.group(1).strip() if file_match else None
        description = description_match.group(1).strip() if description_match else entry.text
        frame_link = f"Vision/frames/{frame_name}" if frame_name else None
        html_frame_link = frame_link
        thumbnail_link = None
        if frame_name and html_mode == "full":
            embedded = _embedded_frame_data(job_dir / "Vision" / "frames" / frame_name)
            if embedded:
                html_frame_link = embedded
        elif frame_name and html_mode == "thumbnails":
            thumbnail_link = _embedded_thumbnail_data(
                job_dir / "Vision" / "frames" / frame_name
            )
            if thumbnail_link:
                html_frame_link = thumbnail_link
        lines = [f"### `{start_badge}` `[VISION]`\n"]
        if frame_link:
            lines.append(f"![Frame]({frame_link})\n")
        lines.append(f"> {description}\n\n---\n\n")
        image_html = ""
        if html_frame_link:
            image = f"<img src='{html_frame_link}' alt='Frame'>"
            if thumbnail_link and frame_link:
                image = f"<a href='{frame_link}' target='_blank' rel='noopener'>{image}</a>"
            image_html = image
        html_row = (
            f"<div class='entry'><span class='badge'>[{html_module.escape(entry.start_str)} --> "
            f"{html_module.escape(entry.end_str)}] VISION</span>"
            + play_button
            + image_html
            + f"<blockquote>{html_module.escape(description)}</blockquote></div>"
        )
        payload = {
            "timestamp_start_ms": entry.start_ms,
            "timestamp_end_ms": entry.end_ms,
            "event_type": "vision",
            "vision": {
                "frame_path": f"Vision/frames/{frame_name}" if frame_name else None,
                "description": description,
            },
        }
        return payload, html_row, lines
    lines = [
        f"### `{start_badge}` `[TRANSCRIPTION]`{speaker_badge}\n",
        f"> {entry.text}\n\n---\n\n",
    ]
    speaker_html = f" &middot; {html_module.escape(speaker)}" if speaker else ""
    html_row = (
        f"<div class='entry'><span class='badge'>[{html_module.escape(entry.start_str)} --> "
        f"{html_module.escape(entry.end_str)}] TRANSCRIPTION{speaker_html}</span>"
        + play_button
        + f"<blockquote>{html_module.escape(entry.text)}</blockquote></div>"
    )
    payload = {
        "timestamp_start_ms": entry.start_ms,
        "timestamp_end_ms": entry.end_ms,
        "event_type": "transcription",
        "transcription": {"speaker": speaker, "text": entry.text},
    }
    return payload, html_row, lines


_TRAILING_RULE = re.compile(r"\n\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_LEADING_RULE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*\n+")


def _known_heading(name: str) -> re.Pattern[str]:
    return re.compile(rf"^##\s+{re.escape(name)}\s*$", re.IGNORECASE | re.MULTILINE)


def _analysis_section(markdown: str, name: str, stops: tuple[str, ...]) -> str | None:
    """Body of a known ``## name`` report section, up to the next known one.

    Only the report's own section names end the body; headings that belong to
    the summary content (``## 1. Bölüm``, ``## Decisions``) are kept.
    """
    match = _known_heading(name).search(markdown)
    if not match:
        return None
    end = len(markdown)
    for stop in stops:
        stop_match = _known_heading(stop).search(markdown, match.end())
        if stop_match:
            end = min(end, stop_match.start())
    body = markdown[match.end() : end].strip()
    body = _LEADING_RULE.sub("", body)
    return _TRAILING_RULE.sub("", body).strip()


def split_ai_analysis(markdown: str | None) -> tuple[str, str]:
    """Extract the Summary and Key Highlights sections from AI_Analysis.md.

    A following ``## Topics`` list must never be folded into Key Highlights
    (it is rendered on its own).
    """
    if not markdown:
        return "", ""
    summary = _analysis_section(markdown, "Summary", ("Key Highlights", "Topics"))
    if summary is None:
        return clean_summary_output(markdown.strip()), ""
    highlights = _analysis_section(markdown, "Key Highlights", ("Topics", "Summary")) or ""
    return clean_summary_output(summary), highlights


def _html_video_player(source_uri: str = "", file_name: str = "") -> str:
    primary = source_uri
    fallback = quote(file_name, safe="") if file_name else ""
    src = primary or fallback
    src_attr = f" src='{src}'" if src else ""
    fallback_attr = f" data-fallback-src='{fallback}'" if fallback else ""
    return (
        "<section id='big-player' class='player' "
        "title='Drop the source video here, or choose it to enable timestamp seeking.'>"
        "<div class='player-head'><strong>Source video</strong>"
        "<span class='hint'>Drop the original file here, or choose it. "
        "It is not uploaded and is not embedded in this report.</span></div>"
        "<input id='video-file' type='file' accept='video/*'>"
        "<div id='video-status' class='hint'>"
        "The report uses the original source address by default; if it was "
        "moved, drop the video here or choose it.</div>"
        "<div id='big-video-slot' class='video-slot'>"
        f"<video id='source-video' controls playsinline preload='metadata'{src_attr}"
        f"{fallback_attr}></video>"
        "</div></section>"
        "<div id='mini-player' class='mini-player' aria-hidden='true'>"
        "<div class='mini-head'><strong>Source video</strong>"
        "<button id='maximize-video' type='button'>Maximize</button></div>"
        "<div id='mini-video-slot' class='mini-slot'></div></div>"
    )


def _html_seek_script() -> str:
    return (
        "<script>(function(){"
        "const video=document.getElementById('source-video');"
        "const picker=document.getElementById('video-file');"
        "const status=document.getElementById('video-status');"
        "const big=document.getElementById('big-player');"
        "const bigSlot=document.getElementById('big-video-slot');"
        "const mini=document.getElementById('mini-player');"
        "const miniSlot=document.getElementById('mini-video-slot');"
        "const maximize=document.getElementById('maximize-video');"
        "let objectUrl=null,fallbackTried=false;"
        "if(!video||!picker||!status||!big||!bigSlot||!mini||!miniSlot)return;"
        "function loadFile(file){"
        "if(!file||!file.type||file.type.indexOf('video/')!==0){"
        "status.textContent='That file is not a video.';return;}"
        "if(objectUrl)URL.revokeObjectURL(objectUrl);"
        "objectUrl=URL.createObjectURL(file);fallbackTried=true;"
        "video.src=objectUrl;status.textContent='Loaded: '+file.name;video.load();"
        "}"
        "picker.addEventListener('change',function(){"
        "loadFile(picker.files&&picker.files[0]);});"
        "['dragenter','dragover'].forEach(function(name){"
        "big.addEventListener(name,function(event){event.preventDefault();"
        "big.classList.add('dragover');});});"
        "['dragleave','drop'].forEach(function(name){"
        "big.addEventListener(name,function(event){event.preventDefault();"
        "big.classList.remove('dragover');});});"
        "big.addEventListener('drop',function(event){"
        "loadFile(event.dataTransfer.files&&event.dataTransfer.files[0]);});"
        "video.addEventListener('error',function(){"
        "const fallback=video.dataset.fallbackSrc||'';"
        "if(!fallbackTried&&fallback){fallbackTried=true;"
        "status.textContent='Primary source not found; trying '+fallback;"
        "video.src=fallback;video.load();return;}"
        "status.textContent='Video not found. Drop the source file here or choose it.';"
        "});"
        "function moveVideo(target){"
        "const time=video.currentTime||0;const playing=!video.paused;"
        "const rate=video.playbackRate;target.appendChild(video);"
        "try{video.currentTime=time;}catch(error){}"
        "video.playbackRate=rate;if(playing){const p=video.play();"
        "if(p&&p.catch)p.catch(function(){});}}"
        "let inMini=false;function setMini(value){if(value===inMini)return;"
        "inMini=value;if(value){mini.classList.add('visible');"
        "mini.setAttribute('aria-hidden','false');moveVideo(miniSlot);}"
        "else{mini.classList.remove('visible');mini.setAttribute('aria-hidden','true');"
        "moveVideo(bigSlot);}}"
        "if('IntersectionObserver' in window){"
        "new IntersectionObserver(function(entries){"
        "const visible=entries[0].isIntersecting;"
        "if(!visible&&video.src)setMini(true);else setMini(false);"
        "},{threshold:0.15}).observe(big);}"
        "if(maximize)maximize.addEventListener('click',function(){setMini(false);"
        "big.scrollIntoView({behavior:'smooth',block:'start'});});"
        "document.addEventListener('click',function(event){"
        "const button=event.target.closest('button.play');if(!button)return;"
        "if(!video.src){status.textContent='Choose the source video first.';"
        "picker.click();return;}"
        "const ms=Number(button.dataset.startMs||0);"
        "video.currentTime=ms/1000;const play=video.play();"
        "if(play&&play.catch)play.catch(function(){});"
        "});"
        "})();</script>"
    )


def _html_head(file_name: str = "") -> str:
    title = f"AfterClip — {file_name}" if file_name else "AfterClip Full Report & Timeline"
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>{html_module.escape(title)}</title>"
        f"<style>{HTML_STYLE}</style></head><body>"
    )


def _html_metadata(
    metadata: dict,
    report_language: str,
    transcript_language: str,
    clip_start: float | None,
    clip_end: float | None,
) -> str:
    media_type = metadata.get("media_type") if isinstance(metadata.get("media_type"), dict) else {}
    media_label = str(media_type.get("media_type") or "Unknown")
    if media_type.get("confidence") is not None:
        media_label += f" (confidence {media_type.get('confidence')})"
    clip_label = (
        "Full file"
        if clip_start is None and clip_end is None
        else f"{clip_start or 0} --> {clip_end if clip_end is not None else 'end'}"
    )
    fields = (
        ("Source file", metadata.get("file_name") or "Unknown"),
        ("Source creation date", metadata.get("creation_date") or "Unknown"),
        ("Duration", _format_seconds(metadata.get("duration"))),
        ("Media type", media_label),
        ("Transcription language", transcript_language or "Unknown"),
        ("Report language", report_language or "Unknown"),
        ("Clip range", clip_label),
        (
            "Generated",
            datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        ),
    )
    cells = "".join(
        f"<div><span>{html_module.escape(label)}</span>"
        f"<strong>{html_module.escape(str(value))}</strong></div>"
        for label, value in fields
    )
    return f"<div class='meta'>{cells}</div>"


def _html_report_sections(
    summary: str,
    highlights: str,
    topics_summary: str,
    *,
    metadata: dict | None = None,
    report_language: str = "",
    transcript_language: str = "",
    clip_start: float | None = None,
    clip_end: float | None = None,
) -> str:
    sections = "<h1>AfterClip Full Report &amp; Timeline</h1>"
    sections += _html_metadata(
        metadata or {},
        report_language,
        transcript_language,
        clip_start,
        clip_end,
    )
    if summary:
        sections += (
            f"<h2>Summary</h2><div class='prose'>"
            f"{render_markdown(summary, heading_offset=1)}</div>"
        )
    if highlights:
        sections += (
            f"<h2>Key Highlights</h2><div class='prose'>"
            f"{render_markdown(highlights, heading_offset=1)}</div>"
        )
    if topics_summary:
        sections += (
            f"<h2>Topics</h2><div class='prose'>"
            f"{render_markdown(topics_summary, heading_offset=1)}</div>"
        )
    return sections


HTML_STYLE = (
    "body{font-family:'Segoe UI',sans-serif;margin:24px auto;max-width:900px;"
    "background:#f5f6f8;color:#222}"
    "h1{margin-bottom:4px}h2{margin-top:28px;border-bottom:1px solid #ddd;padding-bottom:4px}"
    ".meta{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px 16px;"
    "background:#fff;border:1px solid #ddd;border-radius:8px;padding:12px 16px;"
    "margin:12px 0}.meta span{display:block;color:#666;font-size:11px;"
    "text-transform:uppercase;letter-spacing:.04em}.meta strong{font-weight:600}"
    ".prose{background:#fff;border:1px solid #ddd;border-radius:8px;padding:12px 16px}"
    ".prose h2,.prose h3,.prose h4{margin:18px 0 8px;border:0;padding:0}"
    ".prose ul,.prose ol{margin:8px 0 12px 22px;padding:0}"
    ".prose li{margin:4px 0}.prose p{margin:8px 0}"
    ".prose table{border-collapse:collapse;width:100%;margin:10px 0;font-size:13px}"
    ".prose th,.prose td{border:1px solid #ddd;padding:6px 8px;text-align:left;vertical-align:top}"
    ".prose th{background:#f0f2f5}.prose code{background:#f0f2f5;padding:1px 4px;border-radius:3px}"
    ".entry{background:#fff;border:1px solid #ddd;border-radius:8px;"
    "padding:12px 16px;margin:12px 0}"
    ".badge{font-size:12px;color:#666;letter-spacing:.4px}"
    ".topic{margin-top:28px;border-bottom:1px solid #ddd;padding-bottom:4px}"
    ".topic .badge{margin-left:8px;font-weight:400}"
    "img{max-width:640px;border-radius:6px;display:block;margin:8px 0}"
    "blockquote{margin:8px 0 0}"
    ".player{background:#fff;border:2px dashed #b9cdea;border-radius:8px;padding:12px 16px;"
    "margin:12px 0;scroll-margin-top:16px}.player.dragover{background:#eef3fb;"
    "border-color:#245b9e}.player-head{display:flex;flex-wrap:wrap;gap:8px;"
    "align-items:baseline}.player video{width:100%;max-height:420px;background:#000;"
    "border-radius:6px;display:block;margin-top:8px}.player .hint{color:#666;"
    "font-size:12px;margin-top:4px}.video-slot{min-height:1px}"
    ".mini-player{position:fixed;left:16px;bottom:16px;width:320px;z-index:50;"
    "background:#fff;border:1px solid #ddd;border-radius:8px;padding:8px;"
    "box-shadow:0 6px 24px rgba(0,0,0,.18);display:none}"
    ".mini-player.visible{display:block}.mini-head{display:flex;align-items:center;"
    "justify-content:space-between;gap:8px;font-size:12px;margin-bottom:6px}"
    ".mini-head button{background:#eef3fb;color:#245b9e;border:1px solid #b9cdea;"
    "border-radius:5px;padding:2px 7px;font-size:11px;cursor:pointer}"
    ".mini-slot video{max-height:170px;margin:0}"
    ".play{float:right;background:#eef3fb;color:#245b9e;border:1px solid #b9cdea;"
    "border-radius:5px;padding:3px 8px;font-size:12px;cursor:pointer}"
    ".play:hover{background:#dfeafb}"
    "@media (max-width:700px){.mini-player{left:12px;right:12px;bottom:12px;width:auto}}"
)


def _embedded_frame_data(frame_path: Path) -> str | None:
    """Base64 data URI for a frame; None when the file is missing."""
    try:
        encoded = base64.b64encode(frame_path.read_bytes()).decode("ascii")
    except OSError:
        return None
    return f"data:image/png;base64,{encoded}"


def _embedded_thumbnail_data(frame_path: Path, max_width: int = 640, quality: int = 72):
    """Small JPEG data URI for the standalone report; None on failure."""
    try:
        from PIL import Image

        with Image.open(frame_path) as image:
            image = image.convert("RGB")
            image.thumbnail((max_width, max_width))
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=quality, optimize=True)
    except Exception as error:
        LOGGER.warning("Could not create thumbnail for %s: %s", frame_path, error)
        return None
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"
