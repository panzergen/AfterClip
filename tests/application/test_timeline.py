from pathlib import Path

from app.application.timeline import (
    find_transcript_srt,
    parse_speaker_vtt,
    parse_srt,
    resolve_speaker,
    write_master_timeline,
)
from app.domain.models import SpeakerInterval, TimelineEntry

SPEAKER_VTT = """WEBVTT

00:00:00.500 --> 00:00:04.000
<v Metin ONARCAN> Hello there.

00:00:04.000 --> 00:00:08.000
<v Ayse DEMIR> Hi, welcome back.
"""


def test_parse_speaker_vtt_extracts_speaker_intervals(tmp_path: Path):
    path = tmp_path / "speakers.vtt"
    path.write_text(SPEAKER_VTT, encoding="utf-8")
    intervals = parse_speaker_vtt(path)
    assert len(intervals) == 2
    assert intervals[0] == SpeakerInterval(500, 4000, "Metin ONARCAN")
    assert intervals[1].start_ms == 4000 and intervals[1].end_ms == 8000
    assert intervals[1].speaker == "Ayse DEMIR"


def test_parse_speaker_vtt_malformed_does_not_crash(tmp_path: Path):
    path = tmp_path / "broken.vtt"
    path.write_text("not a vtt\n00:00:garbage --> xx\n<v Name> text\n", encoding="utf-8")
    assert parse_speaker_vtt(path) == ()
    assert parse_speaker_vtt(tmp_path / "missing.vtt") == ()
    assert parse_speaker_vtt(None) == ()


def test_parse_speaker_vtt_accepts_short_timestamps_and_common_labels(tmp_path: Path):
    path = tmp_path / "speakers.vtt"
    path.write_text(
        "WEBVTT\n\n"
        "00:00.000 --> 00:05.080\nSpeaker Alice: Hello\n\n"
        "00:05.080 --> 00:09.500\n[SPEAKER_02]: Welcome\n\n"
        "00:09.500 --> 00:12.000\n<v Bob Smith> Thanks\n",
        encoding="utf-8",
    )
    intervals = parse_speaker_vtt(path)
    assert intervals == (
        SpeakerInterval(0, 5080, "Alice"),
        SpeakerInterval(5080, 9500, "SPEAKER_02"),
        SpeakerInterval(9500, 12000, "Bob Smith"),
    )


def test_parse_speaker_vtt_accepts_cue_identifier_speakers(tmp_path: Path):
    path = tmp_path / "cue-speakers.vtt"
    path.write_text(
        "WEBVTT\n\n"
        "Alice\n00:00.000 --> 00:02.000\nHello\n\n"
        "Speaker 2\n00:02.000 --> 00:04.000\nWelcome\n",
        encoding="utf-8",
    )
    assert parse_speaker_vtt(path) == (
        SpeakerInterval(0, 2000, "Alice"),
        SpeakerInterval(2000, 4000, "Speaker 2"),
    )


def test_parse_srt_entries(tmp_path: Path):
    path = tmp_path / "sample.srt"
    path.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\nHello world\n\n2\n00:00:02,000 --> 00:00:04,500\nSecond line\n",
        encoding="utf-8",
    )
    entries = parse_srt(path, "TRANSCRIPTION")
    assert len(entries) == 2
    assert entries[0].start_ms == 0 and entries[0].end_ms == 2000
    assert entries[0].text == "Hello world"
    assert entries[1].end_ms == 4500 and entries[1].text == "Second line"


def test_resolve_speaker_uses_maximum_overlap():
    intervals = (SpeakerInterval(0, 2500, "Alice"), SpeakerInterval(2500, 4000, "Bob"))
    assert resolve_speaker(intervals, 0, 3000) == "Alice"
    assert resolve_speaker(intervals, 3000, 4000) == "Bob"
    assert resolve_speaker(intervals, 9000, 10000) is None


def test_write_master_timeline_merges_entries_and_speakers(tmp_path: Path):
    transcript = tmp_path / "sample.srt"
    transcript.write_text("1\n00:00:00,000 --> 00:00:02,000\nHello world\n", encoding="utf-8")
    vision = tmp_path / "vision_analysis.srt"
    vision.write_text(
        "1\n00:00:01,000 --> 00:00:03,000\nFILE: frame_001.png\nDESCRIPTION: A dashboard screen\n",
        encoding="utf-8",
    )
    speakers_path = tmp_path / "speakers.vtt"
    speakers_path.write_text(SPEAKER_VTT, encoding="utf-8")
    timeline_path, jsonl_path = write_master_timeline(
        tmp_path, transcript, vision, parse_speaker_vtt(speakers_path)
    )
    markdown = timeline_path.read_text(encoding="utf-8")
    assert "[TRANSCRIPTION]" in markdown and "[SPEAKER: Metin ONARCAN]" in markdown
    assert "[VISION]" in markdown and "![Frame](Vision/frames/frame_001.png)" in markdown
    lines = [line for line in jsonl_path.read_text(encoding="utf-8").splitlines() if line]
    assert len(lines) == 2
    assert '"event_type": "transcription"' in lines[0] and '"speaker": "Metin ONARCAN"' in lines[0]
    assert '"event_type": "vision"' in lines[1] and "frame_001.png" in lines[1]


def test_write_master_timeline_embeds_frames_on_request(tmp_path: Path):
    frames_dir = tmp_path / "Vision" / "frames"
    frames_dir.mkdir(parents=True)
    (frames_dir / "frame_001.png").write_bytes(b"png-bytes")
    vision = tmp_path / "vision_analysis.srt"
    vision.write_text(
        "1\n00:00:01,000 --> 00:00:03,000\nFILE: frame_001.png\nDESCRIPTION: A dashboard screen\n",
        encoding="utf-8",
    )
    timeline_path, jsonl_path = write_master_timeline(tmp_path, None, vision, (), embed_frames=True)
    markdown = timeline_path.read_text(encoding="utf-8")
    assert "![Frame](Vision/frames/frame_001.png)" in markdown
    assert "data:image" not in markdown
    html_report = tmp_path / "FullReportAndTimeline.htm"
    assert html_report.is_file()
    html_text = html_report.read_text(encoding="utf-8")
    assert "<img src='data:image/png;base64," in html_text
    assert __import__("base64").b64encode(b"png-bytes").decode("ascii") in html_text
    assert "A dashboard screen" in html_text
    jsonl = [line for line in jsonl_path.read_text(encoding="utf-8").splitlines() if line]
    assert "data:image" not in jsonl[0]
    assert '"frame_path": "Vision/frames/frame_001.png"' in jsonl[0]


def test_write_master_timeline_without_embed_writes_no_html(tmp_path: Path):
    vision = tmp_path / "vision_analysis.srt"
    vision.write_text(
        "1\n00:00:01,000 --> 00:00:03,000\nFILE: ghost.png\nDESCRIPTION: A dashboard screen\n",
        encoding="utf-8",
    )
    timeline_path, _ = write_master_timeline(tmp_path, None, vision, ())
    assert "![Frame](Vision/frames/ghost.png)" in timeline_path.read_text(encoding="utf-8")
    assert not (tmp_path / "FullReportAndTimeline.htm").exists()


def test_full_report_includes_summary_and_highlights(tmp_path: Path):
    vision = tmp_path / "vision_analysis.srt"
    vision.write_text(
        "1\n00:00:01,000 --> 00:00:03,000\nFILE: ghost.png\nDESCRIPTION: A dashboard screen\n",
        encoding="utf-8",
    )
    analysis = "# AI Analysis\n\n- **Model:** `llava`\n\n## Summary\n\nMeeting covered infra fixes.\n\n## Key Highlights\n\n- 00:00:01 important point\n"
    timeline_path, _ = write_master_timeline(
        tmp_path, None, vision, (), embed_frames=True, analysis_markdown=analysis
    )
    html_text = (tmp_path / "FullReportAndTimeline.htm").read_text(encoding="utf-8")
    assert "<h2>Summary</h2>" in html_text and "Meeting covered infra fixes." in html_text
    assert "<h2>Key Highlights</h2>" in html_text and "00:00:01 important point" in html_text
    assert "<h2>Timeline</h2>" in html_text


def test_write_master_timeline_merges_transcript_segments(tmp_path: Path):
    transcript = tmp_path / "sample.srt"
    transcript.write_text(
        "1\n00:00:00,000 --> 00:00:05,000\nFirst sentence\n\n"
        "2\n00:00:05,000 --> 00:00:12,000\nSecond sentence\n\n"
        "3\n00:00:12,000 --> 00:01:00,000\nThird sentence\n",
        encoding="utf-8",
    )
    timeline_path, jsonl_path = write_master_timeline(
        tmp_path, transcript, None, (), transcript_merge_seconds=30.0
    )
    markdown = timeline_path.read_text(encoding="utf-8")
    assert markdown.count("[TRANSCRIPTION]") == 2
    assert "First sentence Second sentence" in markdown
    lines = [line for line in jsonl_path.read_text(encoding="utf-8").splitlines() if line]
    assert "First sentence Second sentence" in lines[0]
    assert "Third sentence" in lines[1]


def test_merge_transcript_entries_respects_max_seconds():
    from app.application.timeline import merge_transcript_entries

    entries = (
        TimelineEntry(0, 5000, "00:00:00,000", "00:00:05,000", "TRANSCRIPTION", "one"),
        TimelineEntry(5000, 20000, "00:00:05,000", "00:00:20,000", "TRANSCRIPTION", "two"),
        TimelineEntry(20000, 45000, "00:00:20,000", "00:00:45,000", "TRANSCRIPTION", "three"),
    )
    merged = merge_transcript_entries(entries, 30.0)
    assert len(merged) == 2
    assert merged[0].start_ms == 0 and merged[0].end_ms == 20000
    assert merged[0].text == "one two"
    assert merged[1].text == "three"


def test_merge_transcript_entries_breaks_on_speaker_change():
    from app.application.timeline import merge_transcript_entries

    speakers = (SpeakerInterval(0, 10000, "Alice"), SpeakerInterval(10000, 30000, "Bob"))
    entries = (
        TimelineEntry(0, 5000, "00:00:00,000", "00:00:05,000", "TRANSCRIPTION", "one"),
        TimelineEntry(5000, 10000, "00:00:05,000", "00:00:10,000", "TRANSCRIPTION", "two"),
        TimelineEntry(10000, 15000, "00:00:10,000", "00:00:15,000", "TRANSCRIPTION", "three"),
        TimelineEntry(15000, 20000, "00:00:15,000", "00:00:20,000", "TRANSCRIPTION", "four"),
    )
    merged = merge_transcript_entries(entries, 30.0, speakers)
    assert len(merged) == 2
    assert merged[0].start_ms == 0 and merged[0].end_ms == 10000
    assert merged[0].text == "one two"
    assert merged[1].start_ms == 10000 and merged[1].end_ms == 20000
    assert merged[1].text == "three four"


def test_write_master_timeline_speaker_aware_merge(tmp_path: Path):
    transcript = tmp_path / "sample.srt"
    transcript.write_text(
        "1\n00:00:00,000 --> 00:00:05,000\nHello there\n\n"
        "2\n00:00:05,000 --> 00:00:09,000\nWelcome back\n\n"
        "3\n00:00:09,000 --> 00:00:14,000\nLet us begin\n\n"
        "4\n00:00:14,000 --> 00:00:20,000\nHere is the plan\n",
        encoding="utf-8",
    )
    speakers = (SpeakerInterval(0, 9000, "Alice"), SpeakerInterval(9000, 30000, "Bob"))
    timeline_path, _ = write_master_timeline(
        tmp_path, transcript, None, speakers, transcript_merge_seconds=30.0
    )
    markdown = timeline_path.read_text(encoding="utf-8")
    assert markdown.count("[TRANSCRIPTION]") == 2
    assert "[SPEAKER: Alice]" in markdown and "Hello there Welcome back" in markdown
    assert "[SPEAKER: Bob]" in markdown and "Let us begin Here is the plan" in markdown


def test_write_master_timeline_missing_frame_falls_back_to_relative(tmp_path: Path):
    vision = tmp_path / "vision_analysis.srt"
    vision.write_text(
        "1\n00:00:01,000 --> 00:00:03,000\nFILE: ghost.png\nDESCRIPTION: A dashboard screen\n",
        encoding="utf-8",
    )
    timeline_path, _ = write_master_timeline(tmp_path, None, vision, (), embed_frames=True)
    assert "![Frame](Vision/frames/ghost.png)" in timeline_path.read_text(encoding="utf-8")


def test_find_transcript_srt_prefers_audio_stem(tmp_path: Path):
    preferred = tmp_path / "converted_audio.srt"
    preferred.write_text("x", encoding="utf-8")
    assert find_transcript_srt(tmp_path, "converted_audio") == preferred
    fallback_dir = tmp_path / "fallback"
    fallback_dir.mkdir()
    only = fallback_dir / "other.srt"
    only.write_text("x", encoding="utf-8")
    assert find_transcript_srt(fallback_dir, "missing_stem") == only
    assert find_transcript_srt(tmp_path / "empty", "x") is None
