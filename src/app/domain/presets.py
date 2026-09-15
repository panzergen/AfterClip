"""Media-type presets (Phase 4 WS-B).

A preset bundles a saved job configuration (Whisper model, languages, AI
toggles, frame settings) with optional prompt-template overrides, so a user can
switch a whole setup with one click and reuse it across media types.
"""

from dataclasses import asdict, dataclass, field

FRAME_RESOLUTIONS = ("full", "mid", "low")


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
        return cls(**values)

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
        cls, name: str, form, prompt_overrides: dict[str, str] | None = None
    ) -> "Preset":
        """Snapshot the current job form into a preset."""
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
            prompt_overrides=dict(prompt_overrides or {}),
        )
