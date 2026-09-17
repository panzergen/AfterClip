from app.application.media_type import (
    MediaSignals,
    classify_tier1,
    merge_tier3,
    parse_classification_output,
    signals_from_metadata,
)


def _signals(**overrides):
    values = {
        "filename": "clip.mp4",
        "duration_seconds": 0.0,
        "has_video": False,
        "has_audio": False,
        "has_support_vtt": False,
    }
    values.update(overrides)
    return MediaSignals(**values)


def test_filename_keyword_meeting():
    guess = classify_tier1(
        _signals(
            filename="Falcon Weekly-20260101-Meeting Recording.mp4",
            has_video=True,
            has_audio=True,
            duration_seconds=3000,
        )
    )
    assert guess.media_type == "meeting"
    assert guess.confident is True
    assert guess.suggested_frame_mode == "interval"
    assert guess.suggested_preset == "meeting"


def test_tutorial_keyword_suggests_scene_frames():
    guess = classify_tier1(
        _signals(filename="docker tutorial part 1.mp4", has_video=True, duration_seconds=600)
    )
    assert guess.media_type == "tutorial"
    assert guess.suggested_frame_mode == "scene"


def test_audio_only_long_is_podcast():
    guess = classify_tier1(
        _signals(filename="episode-42.m4a", has_audio=True, duration_seconds=1800)
    )
    assert guess.media_type == "podcast"


def test_vtt_video_long_is_meeting():
    guess = classify_tier1(
        _signals(
            filename="recording.mp4",
            has_video=True,
            has_audio=True,
            has_support_vtt=True,
            duration_seconds=1200,
        )
    )
    assert guess.media_type == "meeting"
    assert guess.confidence >= 0.5


def test_no_signals_is_other_and_not_confident():
    guess = classify_tier1(_signals(filename="data.bin"))
    assert guess.media_type == "other"
    assert guess.confident is False


def test_signals_from_metadata():
    metadata = {
        "duration": "125.5",
        "streams": [
            {"type": "video", "width": 1920, "height": 1080},
            {"type": "audio", "sample_rate": "48000"},
        ],
    }
    signals = signals_from_metadata("C:/m/My Meeting.mp4", metadata)
    assert signals.has_video and signals.has_audio
    assert signals.width == 1920 and signals.height == 1080
    assert signals.duration_seconds == 125.5
    assert signals.filename == "My Meeting.mp4"


def test_parse_classification_output():
    parsed = parse_classification_output(
        'sure: {"media_type": "webinar", "confidence": 0.8, "reason": "vtt present"}'
    )
    assert parsed["media_type"] == "webinar"
    assert parsed["confidence"] == 0.8
    assert parse_classification_output("no json here") is None
    clamped = parse_classification_output('{"media_type": "bogus", "confidence": 5}')
    assert clamped["media_type"] == "other"
    assert clamped["confidence"] == 1.0


def test_merge_tier3_overrides_base():
    base = classify_tier1(_signals(filename="clip.mp4", has_video=True, duration_seconds=30))
    merged = merge_tier3(base, {"media_type": "presentation", "confidence": 0.7})
    assert merged.media_type == "presentation"
    assert merged.tier == "tier3"
    assert merged.confidence == 0.7
    assert merged.suggested_frame_mode == "scene"
