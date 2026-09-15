import json

from app.application.transcript_sanitizer import (
    DEFAULT_BLOCKLIST,
    SanitizerConfig,
    load_segments,
    render_srt,
    render_text,
    sanitize_segments,
)


def seg(text, start=0.0, end=1.0, no_speech=0.0, logprob=-0.2, compression=1.2):
    return {
        "text": text,
        "start": start,
        "end": end,
        "no_speech_prob": no_speech,
        "avg_logprob": logprob,
        "compression_ratio": compression,
    }


def test_clean_segments_are_kept():
    result = sanitize_segments([seg("hello world")], SanitizerConfig())
    assert len(result.kept) == 1
    assert result.removed == []
    assert result.flagged == []


def test_empty_and_blocklist_removed():
    result = sanitize_segments([seg("   "), seg("Thanks for watching!")], SanitizerConfig())
    assert result.kept == []
    assert {decision.reason for decision in result.removed} == {"empty", "blocklist"}


def test_high_no_speech_removed():
    result = sanitize_segments([seg("mmh", no_speech=0.9)], SanitizerConfig())
    assert [decision.reason for decision in result.removed] == ["no_speech"]


def test_high_compression_removed():
    result = sanitize_segments([seg("la la la", compression=3.0)], SanitizerConfig())
    assert [decision.reason for decision in result.removed] == ["compression"]


def test_repetition_beyond_limit_removed():
    segments = [seg("same line") for _ in range(5)]
    result = sanitize_segments(segments, SanitizerConfig(max_repetition=3))
    assert len(result.kept) == 2  # first two kept; the loop is cut from the third
    assert all(decision.reason == "repetition" for decision in result.removed)


def test_low_logprob_flagged_not_removed():
    result = sanitize_segments([seg("uncertain words", logprob=-1.5)], SanitizerConfig())
    assert len(result.kept) == 1
    assert [decision.reason for decision in result.flagged] == ["low_logprob"]


def test_config_from_dict_handles_junk():
    config = SanitizerConfig.from_dict({"no_speech_threshold": "bad", "blocklist": "nope"})
    assert config.no_speech_threshold == 0.6
    assert config.blocklist == DEFAULT_BLOCKLIST
    assert SanitizerConfig.from_dict(None) == SanitizerConfig()


def test_config_roundtrip():
    config = SanitizerConfig(enabled=False, no_speech_threshold=0.7, blocklist=("x",))
    assert SanitizerConfig.from_dict(config.to_dict()) == config


def test_report_lists_removed_and_flagged():
    result = sanitize_segments(
        [seg("ok"), seg("Thanks for watching"), seg("?", logprob=-2.0)], SanitizerConfig()
    )
    report = result.report()
    assert report["removed_count"] == 1
    assert report["flagged_count"] == 1
    assert report["kept_count"] == 2
    assert report["removed"][0]["reason"] == "blocklist"


def test_load_segments_tolerates_missing_and_corrupt(tmp_path):
    assert load_segments(tmp_path / "missing.json") == []
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert load_segments(bad) == []
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"segments": [{"text": "hi"}, "junk"]}), encoding="utf-8")
    assert load_segments(good) == [{"text": "hi"}]


def test_render_srt_and_text():
    segments = [seg("hello", start=0.0, end=1.5), seg("world", start=1.5, end=3.0)]
    srt = render_srt(segments)
    assert "00:00:00,000 --> 00:00:01,500" in srt
    assert "2\n00:00:01,500 --> 00:00:03,000\nworld" in srt
    assert render_text(segments) == "hello\nworld"
