"""Prompt scope resolution (Phase 1).

Three prompt states:
- global: saved in prompts.json, used by the next job.
- preset: full snapshot stored inside a preset (replace mode).
- custom: unsaved session edits, used for the next job only.

This module is Qt-free so the CLI, MCP server and GUI share it.
"""

from dataclasses import dataclass

from app.domain.presets import Preset
from app.domain.prompts import PromptSet, build_prompt_set, prompt_set_from_snapshot


@dataclass(frozen=True)
class ResolvedPrompts:
    prompt_set: PromptSet
    source: str  # global | preset | custom | default
    preset_name: str = ""


def apply_preset_to_prompts(preset: Preset | None, base: PromptSet) -> PromptSet:
    """Apply a preset's prompt payload to a base set (replace/inherit/legacy)."""
    if preset is None:
        return base
    if preset.prompt_mode == "replace" and preset.prompts:
        return prompt_set_from_snapshot(preset.prompts)
    if preset.prompt_mode == "legacy-partial" and preset.prompt_overrides:
        return base.with_overrides(preset.prompt_overrides)
    # Covers inherit, replace without a snapshot, and legacy without overrides.
    return base


def resolve_for_job(
    custom: PromptSet | dict[str, str] | None,
    preset: Preset | None,
    global_prompts: PromptSet | None,
) -> ResolvedPrompts:
    """Resolve the PromptSet used for the next job.

    Precedence: session custom > preset snapshot > global store > defaults.
    ``custom`` may be a PromptSet, a dict of overrides, or None.
    """
    base = global_prompts or PromptSet()
    if custom is not None:
        if isinstance(custom, PromptSet):
            return ResolvedPrompts(
                prompt_set=custom,
                source="custom",
                preset_name=preset.name if preset else "",
            )
        if isinstance(custom, dict) and custom:
            return ResolvedPrompts(
                prompt_set=base.with_overrides(custom),
                source="custom",
                preset_name=preset.name if preset else "",
            )
    if preset is not None:
        if preset.prompt_mode == "replace" and preset.prompts:
            return ResolvedPrompts(
                prompt_set=prompt_set_from_snapshot(preset.prompts),
                source="preset",
                preset_name=preset.name,
            )
        if preset.prompt_mode == "legacy-partial" and preset.prompt_overrides:
            return ResolvedPrompts(
                prompt_set=base.with_overrides(preset.prompt_overrides),
                source="preset",
                preset_name=preset.name,
            )
        return ResolvedPrompts(prompt_set=base, source="global", preset_name=preset.name)
    return ResolvedPrompts(prompt_set=base, source="global")


def resolve_cli_prompts(
    preset: Preset | None, global_prompts: PromptSet | None = None
) -> PromptSet:
    """CLI/MCP helper: global store with preset replace/legacy semantics."""
    base = global_prompts or PromptSet()
    return apply_preset_to_prompts(preset, base)


def preset_badge(
    preset: Preset | None, has_unsaved: bool, global_is_default: bool = False
) -> str:
    """Badge text for the preset selector (Phase 1 UI)."""
    if has_unsaved:
        return "Custom"
    if preset is None:
        return "Saved" if not global_is_default else "Default"
    if preset.prompt_mode == "replace" and preset.prompts:
        return "Applied"
    if preset.prompt_mode == "legacy-partial":
        return "Legacy"
    return "Inherited"


def snapshot_from_prompt_set(prompt_set: PromptSet) -> dict[str, str]:
    """Full nine-template snapshot for a replace-mode preset."""
    return dict(prompt_set.to_dict())


def empty_snapshot() -> dict[str, str]:
    return dict(PromptSet().to_dict())
