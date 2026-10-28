from app.application.prompt_scope import (
    apply_preset_to_prompts,
    preset_badge,
    resolve_cli_prompts,
    resolve_for_job,
)
from app.domain.presets import Preset
from app.domain.prompts import DEFAULT_PROMPTS, PromptSet, build_prompt_set


def test_replace_preset_overwrites_every_template_including_defaults():
    base = build_prompt_set({"summary": "OLD {lang} {transcript}"})
    snapshot = dict(PromptSet().to_dict())
    snapshot["summary"] = "NEW {lang} {transcript}"
    preset = Preset(name="p", prompt_mode="replace", prompts=snapshot)
    resolved = apply_preset_to_prompts(preset, base)
    assert resolved.summary == "NEW {lang} {transcript}"
    # A template equal to the default in the snapshot restores the default.
    assert resolved.highlights == DEFAULT_PROMPTS["highlights"]


def test_inherit_preset_leaves_prompts_unchanged():
    base = build_prompt_set({"summary": "KEEP {lang} {transcript}"})
    preset = Preset(name="p", prompt_mode="inherit", prompts=None)
    assert apply_preset_to_prompts(preset, base) == base


def test_legacy_preset_merges_overrides():
    base = PromptSet()
    preset = Preset(
        name="p",
        prompt_mode="legacy-partial",
        prompts=None,
        prompt_overrides={"summary": "LEGACY {lang} {transcript}"},
    )
    resolved = apply_preset_to_prompts(preset, base)
    assert resolved.summary == "LEGACY {lang} {transcript}"
    assert resolved.highlights == DEFAULT_PROMPTS["highlights"]


def test_resolve_for_job_prefers_custom_over_preset():
    global_set = build_prompt_set({"summary": "GLOBAL {lang} {transcript}"})
    preset = Preset(
        name="p",
        prompt_mode="replace",
        prompts={**PromptSet().to_dict(), "summary": "PRESET {lang} {transcript}"},
    )
    custom = build_prompt_set({"summary": "CUSTOM {lang} {transcript}"})
    resolved = resolve_for_job(custom, preset, global_set)
    assert resolved.source == "custom"
    assert resolved.prompt_set.summary == "CUSTOM {lang} {transcript}"


def test_resolve_cli_replace_and_legacy():
    base = PromptSet()
    replace = Preset(
        name="r",
        prompt_mode="replace",
        prompts={**PromptSet().to_dict(), "summary": "R {lang} {transcript}"},
    )
    assert resolve_cli_prompts(replace, base).summary == "R {lang} {transcript}"
    legacy = Preset(
        name="l",
        prompt_mode="legacy-partial",
        prompt_overrides={"summary": "L {lang} {transcript}"},
    )
    resolved = resolve_cli_prompts(legacy, base)
    assert resolved.summary == "L {lang} {transcript}"
    inherit = Preset(name="i", prompt_mode="inherit")
    assert resolve_cli_prompts(inherit, base) == base


def test_preset_badge_states():
    replace = Preset(name="r", prompt_mode="replace", prompts=dict(PromptSet().to_dict()))
    assert preset_badge(replace, False) == "Applied"
    assert preset_badge(replace, True) == "Custom"
    assert preset_badge(Preset(name="i", prompt_mode="inherit"), False) == "Inherited"
    legacy = Preset(
        name="l", prompt_mode="legacy-partial", prompt_overrides={"summary": "x"}
    )
    assert preset_badge(legacy, False) == "Legacy"
    assert preset_badge(None, False) == "Saved"
