import logging
from datetime import datetime

from PySide6.QtCore import Property, QObject, Signal, Slot

from app.application.cloud_consent import grant_consent, has_consent, revoke_consent
from app.application.provider_registry import KIND_GEMINI, cloud_provider_ids, get_provider
from app.application.transcript_sanitizer import SanitizerConfig
from app.domain.prompts import (
    TEMPLATE_NAMES,
    TEMPLATE_PLACEHOLDERS,
    PromptSet,
    validate_template,
)
from app.infrastructure.gemini import GeminiClient
from app.infrastructure.openai_compat import OpenAICompatClient
from app.infrastructure.prompts import JsonPromptStore
from app.infrastructure.secrets import KeyringSecretStore, SecretStoreUnavailableError
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
SANITIZER_SETTINGS_KEY = "transcript_filter"
GEMINI_MODEL_CHOICES = ("gemini-flash-latest", "gemini-2.5-flash", "gemini-2.5-pro")

#: Cloud providers offered in Settings, in registry order.
CLOUD_PROVIDER_IDS = cloud_provider_ids()
CLOUD_PROVIDER_LABELS = [get_provider(provider_id).label for provider_id in CLOUD_PROVIDER_IDS]


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
        prompt_store=None,
        parent=None,
    ):
        super().__init__(parent)
        self.store = store or JsonSettingsStore()
        self.key_store = key_store or KeyringSecretStore()
        self.prompt_store = prompt_store or JsonPromptStore()
        migrate = getattr(self.store, "migrate", None)
        if callable(migrate):
            try:
                migrate()
            except Exception as error:  # a broken settings file must not stop startup
                logging.getLogger(__name__).warning("Settings migration failed: %s", error)
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
        self._cloud_provider_index = 0
        self._key_status_text = ""
        self._key_stored = False
        self._key_input = ""
        self._prompt_index = 0
        self._prompt_text = ""
        self._prompt_status_text = ""
        self._prompt_status_ok = True
        self._load_prompt_editor()
        self._refresh_key_status()

    def _provider_id(self) -> str:
        return CLOUD_PROVIDER_IDS[self._cloud_provider_index]

    def _provider_spec(self):
        return get_provider(self._provider_id())

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
        return self._key_stored

    def _get_model_options(self) -> list:
        return getattr(self, "_model_options", list(GEMINI_MODEL_CHOICES))

    def _get_cloud_provider_index(self) -> int:
        return self._cloud_provider_index

    def _set_cloud_provider_index(self, value: int) -> None:
        index = int(value)
        if 0 <= index < len(CLOUD_PROVIDER_IDS) and index != self._cloud_provider_index:
            self._cloud_provider_index = index
            self.cloudProviderIndexChanged.emit()
            self._refresh_key_status()
            self.cloudConsentChanged.emit()

    def _get_cloud_provider_labels(self) -> list:
        return list(CLOUD_PROVIDER_LABELS)

    def _get_cloud_consent_granted(self) -> bool:
        return has_consent(self.store, self._provider_id())

    def _get_cloud_consent_text(self) -> str:
        label = self._provider_spec().label
        if has_consent(self.store, self._provider_id()):
            return (
                f"Consent granted: transcript text and/or extracted frames may be sent to "
                f"{label}. Revoke to require confirmation again."
            )
        return (
            f"Consent not granted. Before the first {label} job AfterClip asks for explicit "
            "confirmation of what leaves this machine."
        )

    def _get_prompt_names(self) -> list:
        return list(TEMPLATE_NAMES)

    def _get_prompt_placeholders(self) -> list:
        return sorted(TEMPLATE_PLACEHOLDERS.get(self._prompt_name(), ()))

    def _get_prompt_index(self) -> int:
        return self._prompt_index

    def _set_prompt_index(self, value: int) -> None:
        self.selectPrompt(int(value))

    def _get_prompt_text(self) -> str:
        return self._prompt_text

    def _set_prompt_text(self, value: str) -> None:
        self._prompt_text = str(value)
        self.promptTextChanged.emit()

    def _get_prompt_status_text(self) -> str:
        return self._prompt_status_text

    def _get_prompt_status_ok(self) -> bool:
        return self._prompt_status_ok

    segmentIndexChanged = Signal()
    reportLanguageChanged = Signal()
    geminiModelChanged = Signal()
    keyStatusChanged = Signal()
    modelOptionsChanged = Signal()
    keyInputChanged = Signal()
    cloudConsentChanged = Signal()
    cloudProviderIndexChanged = Signal()
    promptIndexChanged = Signal()
    promptTextChanged = Signal()
    promptStatusChanged = Signal()

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
    cloudConsentGranted = Property(
        bool, _get_cloud_consent_granted, notify=cloudConsentChanged
    )
    cloudConsentText = Property(str, _get_cloud_consent_text, notify=cloudConsentChanged)
    cloudProviderLabels = Property("QVariantList", _get_cloud_provider_labels, constant=True)
    cloudProviderIndex = Property(
        int, _get_cloud_provider_index, _set_cloud_provider_index, notify=cloudProviderIndexChanged
    )
    promptNames = Property("QVariantList", _get_prompt_names, constant=True)
    promptPlaceholders = Property(
        "QVariantList", _get_prompt_placeholders, notify=promptIndexChanged
    )
    promptIndex = Property(
        int, _get_prompt_index, _set_prompt_index, notify=promptIndexChanged
    )
    promptText = Property(str, _get_prompt_text, _set_prompt_text, notify=promptTextChanged)
    promptStatusText = Property(
        str, _get_prompt_status_text, notify=promptStatusChanged
    )
    promptStatusOk = Property(bool, _get_prompt_status_ok, notify=promptStatusChanged)

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
        try:
            self.key_store.set(self._provider_spec().key_name, key)
        except SecretStoreUnavailableError as error:
            self._set_key_status(str(error), ok=False)
            return
        self._key_input = ""
        self.keyInputChanged.emit()
        self._refresh_key_status()

    @Slot()
    def deleteKey(self) -> None:
        try:
            self.key_store.delete(self._provider_spec().key_name)
        except SecretStoreUnavailableError as error:
            self._set_key_status(str(error), ok=False)
            return
        self._refresh_key_status()

    def has_cloud_consent(self, provider: str) -> bool:
        return has_consent(self.store, provider)

    def grant_cloud_consent(self, provider: str) -> None:
        grant_consent(self.store, provider, datetime.now().isoformat(timespec="seconds"))
        self.cloudConsentChanged.emit()

    def revoke_cloud_consent(self, provider: str) -> None:
        revoke_consent(self.store, provider)
        self.cloudConsentChanged.emit()

    @Slot()
    def grantConsent(self) -> None:
        self.grant_cloud_consent(self._provider_id())

    @Slot()
    def revokeConsent(self) -> None:
        self.revoke_cloud_consent(self._provider_id())

    @Slot()
    def grantGeminiConsent(self) -> None:
        self.grant_cloud_consent("gemini")

    @Slot()
    def revokeGeminiConsent(self) -> None:
        self.revoke_cloud_consent("gemini")

    @Slot()
    def loadModels(self) -> None:
        spec = self._provider_spec()
        key = self.key_store.get(spec.key_name)
        if not key:
            self._set_key_status(f"Save a {spec.label} API key first.", ok=False)
            return
        try:
            if spec.kind == KIND_GEMINI:
                models = GeminiClient(key_getter=lambda: key).list_models()
            else:
                models = OpenAICompatClient(
                    model="", base_url=spec.base_url, provider=spec.id, key_getter=lambda: key
                ).list_models()
        except Exception as error:
            self._set_key_status(f"Could not load models: {error}", ok=False)
            return
        if models:
            if spec.kind == KIND_GEMINI and not self._gemini_model:
                self._gemini_model = models[0]
                self.geminiModelChanged.emit()
            self._model_options = list(models)
            self.modelOptionsChanged.emit()
            self._set_key_status(f"Loaded {len(models)} models from {spec.label}.", ok=True)

    def _refresh_key_status(self) -> None:
        spec = self._provider_spec()
        available = getattr(self.key_store, "available", lambda: True)()
        if not available:
            self._key_stored = False
            self._set_key_status(
                "No OS credential manager is available; API keys cannot be stored "
                "on this system.",
                ok=False,
            )
            return
        self._key_stored = bool(self.key_store.get(spec.key_name))
        if self._key_stored:
            self._set_key_status(
                f"A {spec.label} API key is stored in the OS credential manager.", ok=True
            )
        else:
            self._set_key_status(
                f"No {spec.label} API key stored. Cloud analysis is unavailable "
                "until one is saved.",
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

    def sanitizer_config(self) -> SanitizerConfig:
        """Hallucination filter config from settings (defaults when unset)."""
        return SanitizerConfig.from_dict(self.store.get(SANITIZER_SETTINGS_KEY) or {})

    def prompt_set(self):
        """Resolved prompt templates used for the next job (Phase 4 WS-B)."""
        return self.prompt_store.load()

    def save_prompt_set(self, prompt_set) -> None:
        self.prompt_store.save(prompt_set)

    def _prompt_name(self) -> str:
        return TEMPLATE_NAMES[self._prompt_index]

    def _load_prompt_editor(self) -> None:
        prompt_set = self.prompt_store.load()
        self._prompt_text = prompt_set.template(self._prompt_name())
        self.promptTextChanged.emit()

    def _set_prompt_status(self, text: str, ok: bool) -> None:
        self._prompt_status_text = text
        self._prompt_status_ok = ok
        self.promptStatusChanged.emit()

    @Slot(int)
    def selectPrompt(self, index: int) -> None:
        if 0 <= index < len(TEMPLATE_NAMES):
            self._prompt_index = index
            self.promptIndexChanged.emit()
            self._load_prompt_editor()
            self._set_prompt_status("", True)

    @Slot()
    def savePrompt(self) -> None:
        name = self._prompt_name()
        problems = validate_template(name, self._prompt_text)
        if problems:
            self._set_prompt_status("; ".join(problems), ok=False)
            return
        current = self.prompt_store.load()
        self.prompt_store.save(current.with_overrides({name: self._prompt_text}))
        self._set_prompt_status(f"Saved '{name}'.", ok=True)

    @Slot()
    def resetPrompt(self) -> None:
        self._prompt_text = PromptSet().template(self._prompt_name())
        self.promptTextChanged.emit()
        self._set_prompt_status("Loaded the built-in default; press Save to apply.", ok=True)

    @Slot()
    def reloadPrompts(self) -> None:
        self._load_prompt_editor()
        self._set_prompt_status("", True)
