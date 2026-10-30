import base64
import html as html_module
import json
import logging
import re
from pathlib import Path

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


def write_master_timeline(
    job_dir: Path,
    transcript_srt: Path | None,
    vision_srt: Path | None,
    speaker_intervals: tuple[SpeakerInterval, ...],
    embed_frames: bool = False,
    transcript_merge_seconds: float | None = None,
    analysis_markdown: str | None = None,
    topics: tuple = (),
) -> tuple[Path, Path]:
    """Write ``Master_Timeline.md`` and ``multimodal_timeline.jsonl``.

    The Markdown stays lean for AI consumption: relative frame paths only, no
    binary data. Topic sections add ``## title`` headings. When `embed_frames`
    is set, a human-readable ``FullReportAndTimeline.htm`` is written alongside
    with frames embedded as base64 plus the AI summary, highlights and topics.
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
    markdown_lines = [
        "# Master Chronological Timeline\n\n",
        "This document combines **Audio Transcription**, **Speaker Diarization**, "
        "and **Vision AI Scene Analysis**"
        " in a unified chronological sequence.\n\n---\n\n",
    ]
    topic_list = list(topics)
    topic_index = 0
    # Stream the HTML report instead of accumulating every embedded frame in
    # memory: a large job otherwise holds all base64 frames at once.
    html_file = None
    if embed_frames:
        summary, highlights = split_ai_analysis(analysis_markdown or "")
        topics_summary = "\n".join(
            f"- `[{topic.start_str} --> {topic.end_str}]` {topic.title}" for topic in topic_list
        )
        html_file = (job_dir / "FullReportAndTimeline.htm").open("w", encoding="utf-8")
        html_file.write(_html_head())
        html_file.write(_html_report_sections(summary, highlights, topics_summary))
        html_file.write("<h2>Timeline</h2>")
    for entry in entries:
        while topic_index < len(topic_list) and entry.start_ms >= topic_list[topic_index].start_ms:
            topic = topic_list[topic_index]
            markdown_lines.append(f"\n## {topic.title}\n\n")
            if html_file is not None:
                html_file.write(
                    "<h2 class='topic'>"
                    f"{html_module.escape(topic.title)}"
                    f"<span class='badge'>[{html_module.escape(topic.start_str)} --&gt; "
                    f"{html_module.escape(topic.end_str)}]</span></h2>"
                )
            topic_index += 1
        payload, html_row, lines = _render_entry(entry, speaker_intervals, job_dir, embed_frames)
        if html_file is not None:
            html_file.write(html_row)
        payloads.append(payload)
        markdown_lines.extend(lines)
    timeline_path.write_text("".join(markdown_lines), encoding="utf-8")
    _write_jsonl(jsonl_path, payloads)
    if html_file is not None:
        html_file.write("</body></html>")
        html_file.close()
    return timeline_path, jsonl_path


def _write_jsonl(jsonl_path: Path, payloads: list[dict]) -> None:
    with jsonl_path.open("w", encoding="utf-8") as jsonl:
        for payload in payloads:
            jsonl.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _render_entry(
    entry: TimelineEntry,
    speaker_intervals: tuple[SpeakerInterval, ...],
    job_dir: Path,
    embed_frames: bool,
):
    """One entry -> (jsonl payload, html row, markdown lines)."""
    speaker = resolve_speaker(speaker_intervals, entry.start_ms, entry.end_ms)
    speaker_badge = f" `[SPEAKER: {speaker}]`" if speaker else ""
    start_badge = f"[{entry.start_str} --> {entry.end_str}]"
    if entry.context_type == "VISION":
        file_match = VISION_FILE_PATTERN.search(entry.text)
        description_match = VISION_DESCRIPTION_PATTERN.search(entry.text)
        frame_name = file_match.group(1).strip() if file_match else None
        description = description_match.group(1).strip() if description_match else entry.text
        frame_link = f"Vision/frames/{frame_name}" if frame_name else None
        html_frame_link = frame_link
        if embed_frames and frame_name:
            embedded = _embedded_frame_data(job_dir / "Vision" / "frames" / frame_name)
            if embedded:
                html_frame_link = embedded
        lines = [f"### `{start_badge}` `[VISION]`\n"]
        if frame_link:
            lines.append(f"![Frame]({frame_link})\n")
        lines.append(f"> {description}\n\n---\n\n")
        html_row = (
            f"<div class='entry'><span class='badge'>[{html_module.escape(entry.start_str)} --> "
            f"{html_module.escape(entry.end_str)}] VISION</span>"
            + (f"<img src='{html_frame_link}' alt='Frame'>" if html_frame_link else "")
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
        f"<blockquote>{html_module.escape(entry.text)}</blockquote></div>"
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


def _html_head() -> str:
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<title>AfterClip Full Report & Timeline</title>"
        f"<style>{HTML_STYLE}</style></head><body>"
    )


def _html_report_sections(summary: str, highlights: str, topics_summary: str) -> str:
    sections = "<h1>AfterClip Full Report &amp; Timeline</h1>"
    if summary:
        sections += (
            f"<h2>Summary</h2><div class='prose'>"
            f"{html_module.escape(summary).replace(chr(10), '<br>')}</div>"
        )
    if highlights:
        sections += (
            f"<h2>Key Highlights</h2><div class='prose'>"
            f"{html_module.escape(highlights).replace(chr(10), '<br>')}</div>"
        )
    if topics_summary:
        topics_html = html_module.escape(topics_summary).replace(chr(10), "<br>")
        sections += f"<h2>Topics</h2><div class='prose'>{topics_html}</div>"
    return sections


HTML_STYLE = (
    "body{font-family:'Segoe UI',sans-serif;margin:24px auto;max-width:900px;"
    "background:#f5f6f8;color:#222}"
    "h1{margin-bottom:4px}h2{margin-top:28px;border-bottom:1px solid #ddd;padding-bottom:4px}"
    ".prose{background:#fff;border:1px solid #ddd;border-radius:8px;padding:12px 16px}"
    ".entry{background:#fff;border:1px solid #ddd;border-radius:8px;"
    "padding:12px 16px;margin:12px 0}"
    ".badge{font-size:12px;color:#666;letter-spacing:.4px}"
    ".topic{margin-top:28px;border-bottom:1px solid #ddd;padding-bottom:4px}"
    ".topic .badge{margin-left:8px;font-weight:400}"
    "img{max-width:640px;border-radius:6px;display:block;margin:8px 0}"
    "blockquote{margin:8px 0 0}"
)


def _embedded_frame_data(frame_path: Path) -> str | None:
    """Base64 data URI for a frame; None when the file is missing."""
    try:
        encoded = base64.b64encode(frame_path.read_bytes()).decode("ascii")
    except OSError:
        return None
    return f"data:image/png;base64,{encoded}"
