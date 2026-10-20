from pathlib import Path

from PySide6.QtCore import Property, QObject, Signal, Slot

from app.application.provider_registry import is_cloud
from app.infrastructure.gemini import DEFAULT_GEMINI_MODEL
from app.infrastructure.settings import JsonSettingsStore
from app.ui.controllers.formatting import local_path
from app.ui.controllers.settings_controller import (
    GEMINI_MODEL_SETTINGS_KEY,
    REPORT_LANGUAGE_SETTINGS_KEY,
    SEGMENT_CHOICES,
    SEGMENT_SETTINGS_KEY,
)

PROVIDER_LABELS = {
    "ollama": "Ollama (local)",
    "gemini": "Gemini (cloud)",
    "openrouter": "OpenRouter (cloud)",
    "opencode_go": "OpenCode Go (cloud)",
    "opencode_zen": "OpenCode Zen (cloud)",
}
WHISPER_MODELS = ("tiny", "base", "small", "medium", "large", "turbo")
FRAME_RESOLUTION_LABELS = (
    "Full (original resolution)",
    "Mid - 1024px",
    "Low - 768px (faster vision)",
)
SUPPORT_FILE_EXTENSIONS = (".vtt", ".txt", ".srt", ".doc", ".docx", ".md", ".png", ".jpg", ".jpeg")
GEMINI_STATIC_MODELS = ["gemini-flash-latest", "gemini-2.5-flash", "gemini-2.5-pro"]
ANALYSIS_MODEL_CHOICE_KEY = "analysis_model_choice"
VISION_MODEL_CHOICE_KEY = "vision_model_choice"
SEGMENT_INDEX_MAPPING = {0.0: 0, 15.0: 1, 30.0: 2, 60.0: 3}


def support_note(path: str) -> str:
    return "speaker diarization" if Path(path).suffix.lower() == ".vtt" else "stored for later use"


class JobFormController(QObject):
    """Right-column job settings: output, languages, support files, AI, visual context."""

    outputChanged = Signal(str)

    def __init__(self, default_output_dir: Path, input_dir: Path, parent=None):
        super().__init__(parent)
        self.input_dir = input_dir
        self.ollama_reachable = False
        self._output_dir = str(default_output_dir)
        self._language = ""
        self._report_language = ""
        self._task = ""
        self._support_files: list[dict] = []
        self._cloud_selected = False
        self._cloud_provider = "gemini"
        self._ai_status = ""
        self._ai_status_color = ""
        self._whisper_model = "turbo"
        self._segment_index = SEGMENT_INDEX_MAPPING[30.0]
        self._analysis_allowed = False
        self._vision_allowed = False
        self._analysis_enabled = False
        self._vision_enabled = False
        self._analysis_model_text = ""
        self._vision_model_text = ""
        self._analysis_model_user_set = False
        self._vision_model_user_set = False
        self._analysis_model_enabled = False
        self._vision_model_enabled = False
        self._interval_mode = False
        self._scene_mode = True
        self._frame_interval = 10
        self._scene_sensitivity = 0.35
        self._frame_resolution_index = 0
        self._embed_frames = False
        self._reuse_transcription = False
        self._transcript_filter = True
        self._voiceprint_enabled = False
        self._analysis_entries: list[dict] = []
        self._vision_entries: list[dict] = []
        self._apply_stored_defaults()
        self.refresh_provider_state()

    # -- stored defaults ------------------------------------------------------

    def _apply_stored_defaults(self) -> None:
        try:
            store = JsonSettingsStore()
        except Exception:
            store = None
        stored_model = store.get(GEMINI_MODEL_SETTINGS_KEY) if store else None
        self._analysis_model_text = str(stored_model or DEFAULT_GEMINI_MODEL)
        self._vision_model_text = str(stored_model or DEFAULT_GEMINI_MODEL)
        stored_report_language = store.get(REPORT_LANGUAGE_SETTINGS_KEY) if store else None
        if stored_report_language:
            self._report_language = str(stored_report_language)
        stored_segment = store.get(SEGMENT_SETTINGS_KEY) if store else None
        self._segment_index = SEGMENT_INDEX_MAPPING.get(
            float(stored_segment) if stored_segment else 30.0, 2
        )

    # -- Qt properties: basic group ---------------------------------------------

    def _get_output_dir(self) -> str:
        return self._output_dir

    def _set_output_dir(self, value: str) -> None:
        text = local_path(value).strip()
        if self._output_dir != text:
            self._output_dir = text
            self.outputChanged.emit(text)
            self.outputDirChanged.emit()

    def _get_language(self) -> str:
        return self._language

    def _set_language(self, value: str) -> None:
        self._language = str(value)
        self.languageChanged.emit()

    def _get_report_language(self) -> str:
        return self._report_language

    def _set_report_language(self, value: str) -> None:
        self._report_language = str(value)
        self.reportLanguageChanged.emit()

    def _get_task(self) -> str:
        return self._task

    def _set_task(self, value: str) -> None:
        self._task = str(value)
        self.taskChanged.emit()

    def _get_support_files(self) -> list:
        return self._support_files

    def _get_whisper_model(self) -> str:
        return self._whisper_model

    def _set_whisper_model(self, value: str) -> None:
        self._whisper_model = str(value)
        self.whisperModelChanged.emit()

    def _get_segment_index(self) -> int:
        return self._segment_index

    def _set_segment_index(self, value: int) -> None:
        self._segment_index = int(value)
        self.segmentIndexChanged.emit()

    outputDirChanged = Signal()
    languageChanged = Signal()
    reportLanguageChanged = Signal()
    taskChanged = Signal()
    supportFilesChanged = Signal()
    whisperModelChanged = Signal()
    segmentIndexChanged = Signal()

    outputDir = Property(str, _get_output_dir, _set_output_dir, notify=outputDirChanged)
    language = Property(str, _get_language, _set_language, notify=languageChanged)
    reportLanguage = Property(
        str, _get_report_language, _set_report_language, notify=reportLanguageChanged
    )
    task = Property(str, _get_task, _set_task, notify=taskChanged)
    supportFiles = Property("QVariantList", _get_support_files, notify=supportFilesChanged)

    def _get_whisper_models(self) -> list:
        return list(WHISPER_MODELS)

    def _get_segment_labels(self) -> list:
        return [label for label, _value in SEGMENT_CHOICES]

    def _get_resolution_labels(self) -> list:
        return list(FRAME_RESOLUTION_LABELS)

    whisperModel = Property(str, _get_whisper_model, _set_whisper_model, notify=whisperModelChanged)
    segmentIndex = Property(int, _get_segment_index, _set_segment_index, notify=segmentIndexChanged)
    whisperModels = Property("QVariantList", _get_whisper_models, constant=True)
    segmentLabels = Property("QVariantList", _get_segment_labels, constant=True)
    resolutionLabels = Property("QVariantList", _get_resolution_labels, constant=True)

    # -- Qt properties: provider toggle ------------------------------------------

    def _get_cloud_selected(self) -> bool:
        return self._cloud_selected

    def _set_cloud_selected(self, value: bool) -> None:
        self._cloud_selected = bool(value)
        self.cloudSelectedChanged.emit()
        self.refresh_provider_state()

    def _get_ai_status(self) -> str:
        return self._ai_status

    def _get_ai_status_color(self) -> str:
        return self._ai_status_color

    cloudSelectedChanged = Signal()
    aiStatusChanged = Signal()

    cloudSelected = Property(
        bool, _get_cloud_selected, _set_cloud_selected, notify=cloudSelectedChanged
    )
    aiStatus = Property(str, _get_ai_status, notify=aiStatusChanged)
    aiStatusColor = Property(str, _get_ai_status_color, notify=aiStatusChanged)

    # -- Qt properties: AI + vision ------------------------------------------------

    def _get_analysis_allowed(self) -> bool:
        return self._analysis_allowed

    def _get_vision_allowed(self) -> bool:
        return self._vision_allowed

    def _get_analysis_enabled(self) -> bool:
        return self._analysis_enabled

    def _set_analysis_enabled(self, value: bool) -> None:
        self._analysis_enabled = bool(value)
        self.analysisEnabledChanged.emit()
        self.refresh_provider_state()

    def _get_vision_enabled(self) -> bool:
        return self._vision_enabled

    def _set_vision_enabled(self, value: bool) -> None:
        self._vision_enabled = bool(value)
        self.visionEnabledChanged.emit()
        self.refresh_provider_state()

    def _get_analysis_model_text(self) -> str:
        return self._analysis_model_text

    def _set_analysis_model_text(self, value: str) -> None:
        self._analysis_model_text = str(value)
        self._analysis_model_user_set = True
        self.analysisModelTextChanged.emit()

    def _get_vision_model_text(self) -> str:
        return self._vision_model_text

    def _set_vision_model_text(self, value: str) -> None:
        self._vision_model_text = str(value)
        self._vision_model_user_set = True
        self.visionModelTextChanged.emit()

    def _get_analysis_model_enabled(self) -> bool:
        return self._analysis_model_enabled

    def _get_vision_model_enabled(self) -> bool:
        return self._vision_model_enabled

    def _get_analysis_entries(self) -> list:
        return self._analysis_entries

    def _get_vision_entries(self) -> list:
        return self._vision_entries

    analysisEnabledChanged = Signal()
    visionEnabledChanged = Signal()
    analysisModelTextChanged = Signal()
    visionModelTextChanged = Signal()
    aiStateChanged = Signal()
    catalogChanged = Signal()

    analysisAllowed = Property(bool, _get_analysis_allowed, notify=aiStateChanged)
    visionAllowed = Property(bool, _get_vision_allowed, notify=aiStateChanged)
    analysisEnabled = Property(
        bool, _get_analysis_enabled, _set_analysis_enabled, notify=analysisEnabledChanged
    )
    visionEnabled = Property(
        bool, _get_vision_enabled, _set_vision_enabled, notify=visionEnabledChanged
    )
    analysisModelEnabled = Property(bool, _get_analysis_model_enabled, notify=aiStateChanged)
    visionModelEnabled = Property(bool, _get_vision_model_enabled, notify=aiStateChanged)
    analysisModelText = Property(
        str, _get_analysis_model_text, _set_analysis_model_text, notify=analysisModelTextChanged
    )
    visionModelText = Property(
        str, _get_vision_model_text, _set_vision_model_text, notify=visionModelTextChanged
    )
    analysisEntries = Property("QVariantList", _get_analysis_entries, notify=catalogChanged)
    visionEntries = Property("QVariantList", _get_vision_entries, notify=catalogChanged)

    # -- Qt properties: visual context ------------------------------------------------

    def _get_interval_mode(self) -> bool:
        return self._interval_mode

    def _set_interval_mode(self, value: bool) -> None:
        self._interval_mode = bool(value)
        self.intervalModeChanged.emit()

    def _get_scene_mode(self) -> bool:
        return self._scene_mode

    def _set_scene_mode(self, value: bool) -> None:
        self._scene_mode = bool(value)
        self.sceneModeChanged.emit()

    def _get_frame_interval(self) -> int:
        return self._frame_interval

    def _set_frame_interval(self, value: int) -> None:
        self._frame_interval = int(value)
        self.frameIntervalChanged.emit()

    def _get_scene_sensitivity(self) -> float:
        return self._scene_sensitivity

    def _set_scene_sensitivity(self, value: float) -> None:
        self._scene_sensitivity = float(value)
        self.sceneSensitivityChanged.emit()

    def _get_frame_resolution_index(self) -> int:
        return self._frame_resolution_index

    def _set_frame_resolution_index(self, value: int) -> None:
        self._frame_resolution_index = int(value)
        self.frameResolutionIndexChanged.emit()

    def _get_embed_frames(self) -> bool:
        return self._embed_frames

    def _set_embed_frames(self, value: bool) -> None:
        self._embed_frames = bool(value)
        self.embedFramesChanged.emit()

    def _get_reuse_transcription(self) -> bool:
        return self._reuse_transcription

    def _set_reuse_transcription(self, value: bool) -> None:
        self._reuse_transcription = bool(value)
        self.reuseTranscriptionChanged.emit()

    def _get_transcript_filter(self) -> bool:
        return self._transcript_filter

    def _set_transcript_filter(self, value: bool) -> None:
        self._transcript_filter = bool(value)
        self.transcriptFilterChanged.emit()

    def _get_voiceprint_enabled(self) -> bool:
        return self._voiceprint_enabled

    def _set_voiceprint_enabled(self, value: bool) -> None:
        self._voiceprint_enabled = bool(value)
        self.voiceprintEnabledChanged.emit()

    intervalModeChanged = Signal()
    sceneModeChanged = Signal()
    frameIntervalChanged = Signal()
    sceneSensitivityChanged = Signal()
    frameResolutionIndexChanged = Signal()
    embedFramesChanged = Signal()
    reuseTranscriptionChanged = Signal()
    transcriptFilterChanged = Signal()
    voiceprintEnabledChanged = Signal()

    intervalMode = Property(
        bool, _get_interval_mode, _set_interval_mode, notify=intervalModeChanged
    )
    sceneMode = Property(bool, _get_scene_mode, _set_scene_mode, notify=sceneModeChanged)
    frameInterval = Property(
        int, _get_frame_interval, _set_frame_interval, notify=frameIntervalChanged
    )
    sceneSensitivity = Property(
        float, _get_scene_sensitivity, _set_scene_sensitivity, notify=sceneSensitivityChanged
    )
    frameResolutionIndex = Property(
        int,
        _get_frame_resolution_index,
        _set_frame_resolution_index,
        notify=frameResolutionIndexChanged,
    )
    embedFrames = Property(bool, _get_embed_frames, _set_embed_frames, notify=embedFramesChanged)
    reuseTranscription = Property(
        bool,
        _get_reuse_transcription,
        _set_reuse_transcription,
        notify=reuseTranscriptionChanged,
    )
    transcriptFilter = Property(
        bool,
        _get_transcript_filter,
        _set_transcript_filter,
        notify=transcriptFilterChanged,
    )
    voiceprintEnabled = Property(
        bool,
        _get_voiceprint_enabled,
        _set_voiceprint_enabled,
        notify=voiceprintEnabledChanged,
    )

    # -- support files -----------------------------------------------------------

    def _get_support_files_to_add(self) -> list:
        return []

    def _set_support_files_to_add(self, paths) -> None:
        """QVariant list property: QML list arguments to slots crash here."""
        self.add_support_files(list(paths or []))

    supportFilesToAdd = Property(
        "QVariantList",
        _get_support_files_to_add,
        _set_support_files_to_add,
        notify=supportFilesChanged,
    )

    def add_support_files(self, paths: list) -> None:
        existing = {entry["path"] for entry in self._support_files}
        for path in paths:
            path = local_path(path)
            if path not in existing:
                existing.add(path)
                self._support_files.append(
                    {"name": Path(path).name, "path": path, "note": support_note(path)}
                )
        self.supportFilesChanged.emit()

    @Slot(int)
    def removeSupportFile(self, row: int) -> None:
        if 0 <= row < len(self._support_files):
            del self._support_files[row]
            self.supportFilesChanged.emit()

    def clear_support_files(self) -> None:
        """Drop every support file (called when the input media changes)."""
        if self._support_files:
            self._support_files = []
            self.supportFilesChanged.emit()

    def support_files(self) -> tuple[str, ...]:
        return tuple(entry["path"] for entry in self._support_files)

    def speaker_vtt_from_support(self) -> str:
        for path in self.support_files():
            if Path(path).suffix.lower() == ".vtt":
                return path
        return ""

    # -- provider state ------------------------------------------------------------

    def is_gemini_selected(self) -> bool:
        return self._cloud_selected

    @Slot(bool)
    def set_ollama_enabled(self, reachable: bool) -> None:
        self.ollama_reachable = reachable
        self.refresh_provider_state()

    @Slot()
    def refresh_provider_state(self) -> None:
        if self.is_gemini_selected():
            self._analysis_allowed = True
            self._vision_allowed = True
            self._analysis_model_enabled = self._analysis_enabled
            self._vision_model_enabled = self._vision_enabled
            self._ensure_gemini_models()
            self._set_ai_status(
                "Cloud: transcript text and/or frames are sent to Google Gemini.", "#8a5a00"
            )
            return
        enabled = self.ollama_reachable
        self._analysis_allowed = enabled
        self._vision_allowed = enabled
        self._analysis_model_enabled = enabled and self._analysis_enabled
        self._vision_model_enabled = enabled and self._vision_enabled
        if enabled:
            self._set_ai_status("", "")
            return
        self._set_ai_status(
            "Ollama is offline; start Ollama to enable local AI analysis.", "#a33a2b"
        )

    def _set_ai_status(self, text: str, color: str) -> None:
        if self._ai_status != text or self._ai_status_color != color:
            self._ai_status = text
            self._ai_status_color = color
            self.aiStatusChanged.emit()
        self.aiStateChanged.emit()

    def _ensure_gemini_models(self) -> None:
        # Static fallback only for Gemini; OpenRouter/OpenCode Go rely on the
        # live /models section so no invalid model names are offered.
        if self._cloud_provider != "gemini":
            return
        if not any(entry.get("provider") == "gemini" for entry in self._analysis_entries):
            self._analysis_entries = self._analysis_entries + [
                {"label": name, "header": False, "provider": "gemini", "name": name}
                for name in GEMINI_STATIC_MODELS
            ]
            self.catalogChanged.emit()
        if not any(entry.get("provider") == "gemini" for entry in self._vision_entries):
            self._vision_entries = self._vision_entries + [
                {"label": name, "header": False, "provider": "gemini", "name": name}
                for name in GEMINI_STATIC_MODELS
            ]
            self.catalogChanged.emit()

    def refresh_models(self, enabled: bool) -> None:
        self.refresh_provider_state()

    # -- model catalog ----------------------------------------------------------------

    @Slot(object)
    def populate_models(self, sections) -> None:
        stored_model = self.store_value(GEMINI_MODEL_SETTINGS_KEY)
        choices = {False: self._load_model_choice(False), True: self._load_model_choice(True)}
        for want_vision in (False, True):
            entries: list[dict] = []
            for section in sections:
                entries.append(
                    {
                        "label": section.title,
                        "header": True,
                        "provider": section.provider,
                        "name": "",
                    }
                )
                for entry in section.entries:
                    if want_vision and not entry.vision_capable:
                        continue
                    if not want_vision and not entry.text_capable:
                        continue
                    entries.append(
                        {
                            "label": entry.name,
                            "header": False,
                            "provider": entry.provider,
                            "name": entry.name,
                        }
                    )
            if want_vision:
                previous, self._vision_entries = self._vision_model_text, entries
            else:
                previous, self._analysis_entries = self._analysis_model_text, entries
            choice = choices[want_vision]
            user_set = self._vision_model_user_set if want_vision else self._analysis_model_user_set
            if not user_set and choice:
                # Restore the model (and its provider) used last session.
                previous = str(choice.get("name") or "")
                provider = str(choice.get("provider") or "")
                if provider:
                    self._cloud_provider = provider
                    self._cloud_selected = is_cloud(provider)
                    self.cloudSelectedChanged.emit()
            elif not want_vision and not previous and stored_model:
                previous = str(stored_model)
            if previous:
                if want_vision:
                    if self._vision_model_text != previous:
                        self._vision_model_text = previous
                        self.visionModelTextChanged.emit()
                else:
                    if self._analysis_model_text != previous:
                        self._analysis_model_text = previous
                        self.analysisModelTextChanged.emit()
        self.catalogChanged.emit()
        self.refresh_provider_state()

    def store_value(self, key: str):
        try:
            return JsonSettingsStore().get(key)
        except Exception:
            return None

    def _load_model_choice(self, analysis: bool):
        key = ANALYSIS_MODEL_CHOICE_KEY if analysis else VISION_MODEL_CHOICE_KEY
        value = self.store_value(key)
        return value if isinstance(value, dict) and value.get("name") else None

    def _store_model_choice(self, analysis: bool, provider: str, name: str) -> None:
        key = ANALYSIS_MODEL_CHOICE_KEY if analysis else VISION_MODEL_CHOICE_KEY
        try:
            JsonSettingsStore().set(key, {"provider": provider, "name": name})
        except Exception:
            pass

    @Slot(int)
    def selectAnalysisModel(self, index: int) -> None:
        self._on_model_activated(self._analysis_entries, index, analysis=True)

    @Slot(int)
    def selectVisionModel(self, index: int) -> None:
        self._on_model_activated(self._vision_entries, index, analysis=False)

    def _on_model_activated(self, entries: list, index: int, analysis: bool) -> None:
        if not 0 <= index < len(entries):
            return
        entry = entries[index]
        if entry.get("header"):
            return
        provider = entry.get("provider")
        self._cloud_selected = is_cloud(provider)
        if is_cloud(provider):
            self._cloud_provider = provider
        self.cloudSelectedChanged.emit()
        # Reflect the picked model in the combo/property (the combo only knows
        # the selected index, the request is built from this text).
        name = str(entry.get("name") or "")
        if analysis:
            self._analysis_model_user_set = True
            if self._analysis_model_text != name:
                self._analysis_model_text = name
                self.analysisModelTextChanged.emit()
        else:
            self._vision_model_user_set = True
            if self._vision_model_text != name:
                self._vision_model_text = name
                self.visionModelTextChanged.emit()
        self._store_model_choice(analysis, str(provider or ""), name)
        self.refresh_provider_state()

    def _resolve_model(self, entries: list, text: str, analysis: bool) -> tuple[str, str] | None:
        text = text.strip()
        if not text:
            return None
        for entry in entries:
            if not entry.get("header") and entry.get("name") == text:
                return (entry.get("provider"), text)
        return (self._cloud_provider, text) if self.is_gemini_selected() else ("ollama", text)

    def selected_ai_model(self) -> tuple[str, str] | None:
        return self._resolve_model(self._analysis_entries, self._analysis_model_text, analysis=True)

    def selected_vision_model(self) -> tuple[str, str] | None:
        return self._resolve_model(self._vision_entries, self._vision_model_text, analysis=False)

    @staticmethod
    def _lookup_model(entries: list, text: str) -> tuple[str, str] | None:
        """Resolve a model only when it exists in the loaded catalog (strict)."""
        text = text.strip()
        if not text:
            return None
        for entry in entries:
            if not entry.get("header") and entry.get("name") == text:
                return (entry.get("provider"), text)
        return None

    def lookup_ai_model(self) -> tuple[str, str] | None:
        return self._lookup_model(self._analysis_entries, self._analysis_model_text)

    def lookup_vision_model(self) -> tuple[str, str] | None:
        return self._lookup_model(self._vision_entries, self._vision_model_text)

    # -- derived values ---------------------------------------------------------------

    def selected_frame_modes(self) -> tuple[str, ...]:
        return tuple(
            mode
            for mode, checked in (("interval", self._interval_mode), ("scene", self._scene_mode))
            if checked
        )

    def selected_frame_resolution(self) -> str:
        return ("full", "mid", "low")[self._frame_resolution_index]

    def segment_override(self) -> float | None:
        return SEGMENT_CHOICES[self._segment_index][1] or None

    def output_text(self) -> str:
        return self._output_dir.strip()

    def snapshot(self) -> dict:
        """Settings captured when a batch job is enqueued."""
        selection = self.selected_ai_model()
        vision_selection = self.selected_vision_model()
        frame_modes = self.selected_frame_modes()
        return {
            "model": self._whisper_model,
            "language": self._language,
            "task": self._task.strip(),
            "speaker_vtt_path": self.speaker_vtt_from_support(),
            "support_files": self.support_files(),
            "extract_frames": bool(frame_modes),
            "frame_interval": self._frame_interval,
            "frame_modes": frame_modes,
            "frame_resolution": self.selected_frame_resolution(),
            "scene_sensitivity": self._scene_sensitivity,
            "embed_frames": self._embed_frames,
            "transcript_merge_seconds": self.segment_override(),
            "output_language": self._report_language,
            "text_provider_name": selection[0] if selection else "ollama",
            "text_model": selection[1] if selection else "",
            "analyze_text": self._analysis_enabled and selection is not None,
            "vision_provider_name": vision_selection[0] if vision_selection else "ollama",
            "vision_model": vision_selection[1] if vision_selection else "",
            "analyze_vision": self._vision_enabled and vision_selection is not None,
            "voiceprint_enabled": self._voiceprint_enabled,
        }
