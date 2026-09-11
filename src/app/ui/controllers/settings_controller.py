from PySide6.QtCore import Property, QObject, Signal, Slot

from app.infrastructure.gemini import GEMINI_KEY_NAME, GeminiClient, GeminiKeyMissing
from app.infrastructure.secrets import KeyringSecretStore
from app.infrastructure.settings import JsonSettingsStore

SEGMENT_CHOICES = (
    ("Whisper default (no merging)", 0.0),
    ("15 seconds", 15.0),
    ("30 seconds", 30.0),
    ("60 seconds", 60.0),
)
DEFAULT_SEGMENT_SECONDS = 30.0
SEGMENT_SETTINGS_KEY = "transcript_segment_seconds"
GEMINI_MODEL_SETTINGS_KEY = "gemini_model"
REPORT_LANGUAGE_SETTINGS_KEY = "report_language"
GEMINI_MODEL_CHOICES = ("gemini-flash-latest", "gemini-2.5-flash", "gemini-2.5-pro")


def load_transcript_merge_seconds(store: JsonSettingsStore | None = None) -> float | None:
    try:
        value = float(
            (store or JsonSettingsStore()).get(SEGMENT_SETTINGS_KEY) or DEFAULT_SEGMENT_SECONDS
        )
    except (TypeError, ValueError):
        value = DEFAULT_SEGMENT_SECONDS
    return value if value > 0 else None


class SettingsController(QObject):
    """Persistent application settings (stored in %LOCALAPPDATA%/AfterClip).

    The Gemini API key is never written here: it goes to the Windows
    Credential Manager via KeyringSecretStore (T19/T20).
    """

    def __init__(
        self,
        store: JsonSettingsStore | None = None,
        key_store: KeyringSecretStore | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.store = store or JsonSettingsStore()
        self.key_store = key_store or KeyringSecretStore()
        try:
            current = float(self.store.get(SEGMENT_SETTINGS_KEY) or DEFAULT_SEGMENT_SECONDS)
        except (TypeError, ValueError):
            current = DEFAULT_SEGMENT_SECONDS
        self._segment_index = next(
            (position for position, (_, value) in enumerate(SEGMENT_CHOICES) if value == current),
            2,
        )
        self._report_language = str(self.store.get(REPORT_LANGUAGE_SETTINGS_KEY) or "")
        self._gemini_model = str(self.store.get(GEMINI_MODEL_SETTINGS_KEY) or "")
        self._key_status_text = ""
        self._key_input = ""
        self._refresh_key_status()

    def _get_segment_index(self) -> int:
        return self._segment_index

    def _set_segment_index(self, value: int) -> None:
        self._segment_index = int(value)
        self.segmentIndexChanged.emit()

    def _get_report_language(self) -> str:
        return self._report_language

    def _set_report_language(self, value: str) -> None:
        self._report_language = str(value)
        self.reportLanguageChanged.emit()

    def _get_gemini_model(self) -> str:
        return self._gemini_model

    def _set_gemini_model(self, value: str) -> None:
        self._gemini_model = str(value)
        self.geminiModelChanged.emit()

    def _get_gemini_models(self) -> list:
        return list(GEMINI_MODEL_CHOICES)

    def _get_segment_labels(self) -> list:
        return [label for label, _value in SEGMENT_CHOICES]

    def _get_key_status_text(self) -> str:
        return self._key_status_text

    def _get_key_stored(self) -> bool:
        return "stored in Windows Credential Manager" in self._key_status_text

    def _get_model_options(self) -> list:
        return getattr(self, "_model_options", list(GEMINI_MODEL_CHOICES))

    segmentIndexChanged = Signal()
    reportLanguageChanged = Signal()
    geminiModelChanged = Signal()
    keyStatusChanged = Signal()
    modelOptionsChanged = Signal()
    keyInputChanged = Signal()

    segmentIndex = Property(int, _get_segment_index, _set_segment_index, notify=segmentIndexChanged)
    reportLanguage = Property(
        str, _get_report_language, _set_report_language, notify=reportLanguageChanged
    )
    geminiModel = Property(str, _get_gemini_model, _set_gemini_model, notify=geminiModelChanged)
    geminiModels = Property("QVariantList", _get_gemini_models, constant=True)
    segmentLabels = Property("QVariantList", _get_segment_labels, constant=True)
    keyStatusText = Property(str, _get_key_status_text, notify=keyStatusChanged)
    keyStored = Property(bool, _get_key_stored, notify=keyStatusChanged)
    modelOptions = Property("QVariantList", _get_model_options, notify=modelOptionsChanged)

    def _get_key_input(self) -> str:
        return self._key_input

    def _set_key_input(self, value: str) -> None:
        self._key_input = str(value)
        self.keyInputChanged.emit()

    keyInput = Property(str, _get_key_input, _set_key_input, notify=keyInputChanged)

    @Slot()
    def saveKey(self) -> None:
        """No-arg: QML string args to slots crash in this PySide6 build."""
        key = self._key_input.strip()
        if not key:
            self._set_key_status("Paste a key first.", ok=False)
            return
        self.key_store.set(GEMINI_KEY_NAME, key)
        self._key_input = ""
        self.keyInputChanged.emit()
        self._refresh_key_status()

    @Slot()
    def deleteKey(self) -> None:
        self.key_store.delete(GEMINI_KEY_NAME)
        self._refresh_key_status()

    @Slot()
    def loadModels(self) -> None:
        try:
            models = GeminiClient(
                key_getter=lambda: self.key_store.get(GEMINI_KEY_NAME)
            ).list_models()
        except (GeminiKeyMissing, Exception) as error:
            self._set_key_status(f"Could not load models: {error}", ok=False)
            return
        if models:
            self._gemini_model = models[0] if not self._gemini_model else self._gemini_model
            self.geminiModelChanged.emit()
            self._model_options = list(models)
            self.modelOptionsChanged.emit()
            self._set_key_status(f"Loaded {len(models)} models from the Gemini API.", ok=True)

    def _refresh_key_status(self) -> None:
        if self.key_store.get(GEMINI_KEY_NAME):
            self._set_key_status(
                "A Gemini API key is stored in Windows Credential Manager.", ok=True
            )
        else:
            self._set_key_status(
                "No Gemini API key stored. Cloud analysis is unavailable until one is saved.",
                ok=False,
            )

    def _set_key_status(self, text: str, ok: bool) -> None:
        self._key_status_text = text
        self._key_status_ok = ok
        self.keyStatusChanged.emit()

    @Slot()
    def save(self) -> None:
        value = SEGMENT_CHOICES[self._segment_index][1]
        self.store.set(SEGMENT_SETTINGS_KEY, value)
        self.store.set(GEMINI_MODEL_SETTINGS_KEY, self._gemini_model.strip())
        self.store.set(REPORT_LANGUAGE_SETTINGS_KEY, self._report_language.strip())

    def segment_seconds(self) -> float | None:
        value = SEGMENT_CHOICES[self._segment_index][1]
        return value if value > 0 else None

    def gemini_model(self) -> str:
        return self._gemini_model.strip() or "gemini-2.0-flash"

    def report_language(self) -> str:
        return self._report_language.strip()
