from pathlib import Path

from app.application.service_io import compact_timestamped_transcript

SRT = """1
00:00:00,000 --> 00:00:05,000
Hello world.

2
00:00:05,000 --> 00:00:12,000
Second line.

3
00:00:20,000 --> 00:00:24,000
After a gap.

4
00:00:31,000 --> 00:00:35,000
Last line.
"""


def test_compact_timestamped_transcript_keeps_one_timestamp_per_block(tmp_path: Path):
    path = tmp_path / "transcript.srt"
    path.write_text(SRT, encoding="utf-8")

    text = compact_timestamped_transcript(path, interval_seconds=10)

    assert text == (
        "[00:00:00] Hello world. Second line.\n"
        "[00:00:20] After a gap.\n"
        "[00:00:31] Last line."
    )
    assert "-->" not in text
    assert "1\n00:" not in text


def test_compact_timestamped_transcript_handles_missing_or_empty_files(tmp_path: Path):
    assert compact_timestamped_transcript(None) == ""
    assert compact_timestamped_transcript(tmp_path / "missing.srt") == ""
    empty = tmp_path / "empty.srt"
    empty.write_text("not an srt", encoding="utf-8")
    assert compact_timestamped_transcript(empty) == ""
