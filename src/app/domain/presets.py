"""Media-type presets (Phase 4 WS-B, Phase 1 prompt packs).

A preset bundles a saved job configuration (Whisper model, languages, AI
toggles, frame settings) with an optional full prompt-template snapshot, so a
user can switch a whole setup with one click and reuse it across media types.

Prompt modes (Phase 1):
- ``replace``: carries a full snapshot of all templates; applying it replaces
  the global prompt set.
- ``inherit``: carries no prompt snapshot; applying it leaves prompts untouched.
- ``legacy-partial``: old presets with ``prompt_overrides`` only; applying them
  merges over the current prompts (old behaviour).
"""

from dataclasses import asdict, dataclass, field

FRAME_RESOLUTIONS = ("full", "mid", "low")

PROMPT_MODES = ("replace", "inherit", "legacy-partial")


@dataclass(frozen=True)
class Preset:
    name: str
    whisper_model: str = "turbo"
    language: str = ""
    report_language: str = ""
    cloud_selected: bool = False
    analysis_enabled: bool = False
    vision_enabled: bool = False
    analysis_model_text: str = ""
    vision_model_text: str = ""
    interval_mode: bool = True
    scene_mode: bool = False
    frame_interval: int = 10
    scene_sensitivity: float = 0.35
    frame_resolution_index: int = 0
    segment_index: int = 2
    embed_frames: bool = False
    prompt_mode: str = "replace"
    prompts: dict[str, str] | None = None
    prompt_overrides: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Preset":
        known = set(cls.__dataclass_fields__)
        values = {key: value for key, value in data.items() if key in known}
        overrides = values.get("prompt_overrides")
        if overrides is not None and not isinstance(overrides, dict):
            values["prompt_overrides"] = {}
        snapshot = values.get("prompts")
        if snapshot is not None:
            if not isinstance(snapshot, dict):
                values["prompts"] = None
            else:
                values["prompts"] = {
                    key: value
                    for key, value in snapshot.items()
                    if isinstance(key, str) and isinstance(value, str)
                } or None
        mode = values.get("prompt_mode")
        if not isinstance(mode, str) or mode not in PROMPT_MODES:
            # Infer the mode for old files that predate prompt_mode.
            if values.get("prompts"):
                values["prompt_mode"] = "replace"
            elif values.get("prompt_overrides"):
                values["prompt_mode"] = "legacy-partial"
            else:
                values["prompt_mode"] = "inherit"
        else:
            # A stored legacy-partial without overrides is effectively inherit,
            # but keep the stored mode for transparency.
            pass
        # Normalise a replace preset without a snapshot to inherit.
        if values.get("prompt_mode") == "replace" and not values.get("prompts"):
            # An old preset with only overrides keeps legacy behaviour.
            if values.get("prompt_overrides"):
                values["prompt_mode"] = "legacy-partial"
            else:
                values["prompt_mode"] = "inherit"
        return cls(**values)

    @property
    def has_prompt_snapshot(self) -> bool:
        return self.prompt_mode == "replace" and bool(self.prompts)

    @property
    def is_legacy_prompts(self) -> bool:
        return self.prompt_mode == "legacy-partial" and bool(self.prompt_overrides)

    def apply_to(self, form) -> None:
        """Write this preset's configuration into a JobFormController."""
        form.whisperModel = self.whisper_model
        form.language = self.language
        form.reportLanguage = self.report_language
        form.cloudSelected = self.cloud_selected
        form.analysisModelText = self.analysis_model_text
        form.visionModelText = self.vision_model_text
        form.analysisEnabled = self.analysis_enabled
        form.visionEnabled = self.vision_enabled
        form.intervalMode = self.interval_mode
        form.sceneMode = self.scene_mode
        form.frameInterval = self.frame_interval
        form.sceneSensitivity = self.scene_sensitivity
        form.frameResolutionIndex = self.frame_resolution_index
        form.segmentIndex = self.segment_index
        form.embedFrames = self.embed_frames

    @classmethod
    def capture(
        cls,
        name: str,
        form,
        prompt_overrides: dict[str, str] | None = None,
        *,
        prompts: dict[str, str] | None = None,
        include_prompts: bool | None = None,
    ) -> "Preset":
        """Snapshot the current job form into a preset.

        Phase 1: ``prompts`` is a full snapshot of all templates (replace mode)
        when ``include_prompts`` is true. ``prompt_overrides`` is legacy-only:
        passing it without ``prompts`` creates a ``legacy-partial`` preset for
        backward compatibility.
        """
        if prompts is None and include_prompts is None and prompt_overrides:
            # Legacy caller (pre-Phase 1): partial overrides only.
            return cls(
                name=name,
                whisper_model=form.whisperModel,
                language=form.language,
                report_language=form.reportLanguage,
                cloud_selected=form.cloudSelected,
                analysis_enabled=form.analysisEnabled,
                vision_enabled=form.visionEnabled,
                analysis_model_text=form.analysisModelText,
                vision_model_text=form.visionModelText,
                interval_mode=form.intervalMode,
                scene_mode=form.sceneMode,
                frame_interval=form.frameInterval,
                scene_sensitivity=form.sceneSensitivity,
                frame_resolution_index=form.frameResolutionIndex,
                segment_index=form.segmentIndex,
                embed_frames=form.embedFrames,
                prompt_mode="legacy-partial",
                prompts=None,
                prompt_overrides=dict(prompt_overrides),
            )
        include = True if include_prompts is None else bool(include_prompts)
        snapshot = dict(prompts) if prompts and include else None
        return cls(
            name=name,
            whisper_model=form.whisperModel,
            language=form.language,
            report_language=form.reportLanguage,
            cloud_selected=form.cloudSelected,
            analysis_enabled=form.analysisEnabled,
            vision_enabled=form.visionEnabled,
            analysis_model_text=form.analysisModelText,
            vision_model_text=form.visionModelText,
            interval_mode=form.intervalMode,
            scene_mode=form.sceneMode,
            frame_interval=form.frameInterval,
            scene_sensitivity=form.sceneSensitivity,
            frame_resolution_index=form.frameResolutionIndex,
            segment_index=form.segmentIndex,
            embed_frames=form.embedFrames,
            prompt_mode="replace" if snapshot else "inherit",
            prompts=snapshot,
            prompt_overrides={},
        )
