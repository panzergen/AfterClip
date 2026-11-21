from pathlib import Path

from app.application import media_integrity
from app.application.media_integrity import (
    MediaDurationReport,
    check_media_durations,
    compare_durations,
)


def test_compare_flags_truncated_audio_against_video_and_vtt():
    issues = compare_durations(4322.816, 1921.472, 4320.831)

    assert len(issues) == 2
    assert {(issue.left_label, issue.right_label) for issue in issues} == {
        ("Video metadata", "Processed audio"),
        ("Processed audio", "VTT"),
    }
    assert all(issue.difference_ratio > 0.5 for issue in issues)


def test_compare_accepts_differences_within_five_percent():
    assert compare_durations(100.0, 96.0, 99.0) == ()
    assert compare_durations(100.0, 95.0, None) == ()  # exactly 5% is allowed
    assert compare_durations(100.0, 94.9, None) != ()  # just over 5%


def test_compare_ignores_missing_durations():
    assert compare_durations(100.0, None, None) == ()
    assert compare_durations(None, None, None) == ()
    assert compare_durations(0.0, 100.0, None) == ()


def test_shortest_reports_the_truncated_track():
    report = MediaDurationReport(
        video_seconds=4322.0,
        audio_seconds=1921.0,
        vtt_seconds=4320.0,
        issues=compare_durations(4322.0, 1921.0, 4320.0),
    )

    assert report.shortest == ("Processed audio", 1921.0)


def test_check_media_durations_uses_clip_length(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(media_integrity, "_probe_audio_duration", lambda *args: 30.0)
    monkeypatch.setattr(media_integrity, "vtt_duration_seconds", lambda _path: 4320.0)

    report = check_media_durations(
        tmp_path / "input.mp4",
        video_seconds=100.0,
        clip_start=10.0,
        clip_end=40.0,
        vtt_path="full.vtt",
    )

    assert report.video_seconds == 30.0
    assert report.video_label == "Requested clip"
    assert report.vtt_seconds is None
    assert not report.has_warning


def test_check_media_durations_compares_full_media(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(media_integrity, "_probe_audio_duration", lambda *args: 1921.0)
    monkeypatch.setattr(media_integrity, "vtt_duration_seconds", lambda _path: 4320.0)

    report = check_media_durations(
        tmp_path / "input.mp4",
        video_seconds=4322.0,
        vtt_path="full.vtt",
    )

    assert report.has_warning
    assert report.video_seconds == 4322.0
    assert report.audio_seconds == 1921.0
    assert report.vtt_seconds == 4320.0
