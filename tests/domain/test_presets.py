import types

from app.domain.presets import Preset


def make_form():
    return types.SimpleNamespace(
        whisperModel="base",
        language="en",
        reportLanguage="tr",
        cloudSelected=True,
        analysisEnabled=True,
        visionEnabled=False,
        analysisModelText="gemini-2.5-flash",
        visionModelText="",
        intervalMode=True,
        sceneMode=True,
        frameInterval=15,
        sceneSensitivity=0.4,
        frameResolutionIndex=1,
        segmentIndex=3,
        embedFrames=True,
    )


def test_capture_and_apply_roundtrip():
    form = make_form()
    preset = Preset.capture("meeting", form, {"summary": "x {lang} {transcript}"})
    assert preset.name == "meeting"
    assert preset.prompt_overrides["summary"].startswith("x")

    target = types.SimpleNamespace()
    preset.apply_to(target)
    assert target.whisperModel == "base"
    assert target.frameInterval == 15
    assert target.cloudSelected is True
    assert target.visionEnabled is False
    assert target.segmentIndex == 3


def test_from_dict_ignores_unknown_and_defaults_missing():
    preset = Preset.from_dict({"name": "x", "whisper_model": "small", "bogus": 1})
    assert preset.name == "x"
    assert preset.whisper_model == "small"
    assert preset.frame_interval == 10  # default


def test_from_dict_normalizes_bad_prompt_overrides():
    preset = Preset.from_dict({"name": "x", "prompt_overrides": ["not", "a", "dict"]})
    assert preset.prompt_overrides == {}


def test_to_dict_roundtrip():
    preset = Preset.capture("m", make_form())
    assert Preset.from_dict(preset.to_dict()) == preset
