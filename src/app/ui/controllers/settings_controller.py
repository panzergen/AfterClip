import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Property, QObject, Signal, Slot

import app.app_paths as app_paths
from app.application.cloud_consent import grant_consent, has_consent, revoke_consent
from app.application.provider_registry import KIND_GEMINI, cloud_provider_ids, get_provider
from app.application.transcript_sanitizer import SanitizerConfig
from app.application.voiceprints import (
    DEFAULT_CLUSTER_THRESHOLD,
    DEFAULT_IDENTIFY_THRESHOLD,
)
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
from app.infrastructure.voiceprint_embedder import SpeakerOnnxEmbedder, voiceprints_available
from app.infrastructure.voiceprints import JsonVoiceprintStore
from app.ui.notification_sound import NotificationSound

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
VOICEPRINT_IDENTIFY_THRESHOLD_KEY = "voiceprint_identify_threshold"
VOICEPRINT_CLUSTER_THRESHOLD_KEY = "voiceprint_cluster_threshold"
NOTIFICATION_SOUND_ENABLED_KEY = "notification_sound_enabled"
NOTIFICATION_SOUND_PATH_KEY = "notification_sound_path"
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
        self._model_options: list = []
        self._key_status_text = ""
        self._key_stored = False
        self._key_input = ""
        self._prompt_index = 0
        self._prompt_text = ""
        self._prompt_status_text = ""
        self._prompt_status_ok = True
        self._session_prompt_overrides: dict[str, str] = {}
        self._voiceprint_store = JsonVoiceprintStore()
        self._voiceprint_embedder = SpeakerOnnxEmbedder() if voiceprints_available() else None
        self._voiceprint_identify_threshold = self._load_voiceprint_threshold(
            VOICEPRINT_IDENTIFY_THRESHOLD_KEY, DEFAULT_IDENTIFY_THRESHOLD
        )
        self._voiceprint_cluster_threshold = self._load_voiceprint_threshold(
            VOICEPRINT_CLUSTER_THRESHOLD_KEY, DEFAULT_CLUSTER_THRESHOLD
        )
        self._voiceprint_names: list = []
        self._voiceprint_status_text = ""
        self._voiceprint_enroll_name = ""
        self._voiceprint_enroll_path = ""
        self._notification_enabled = self.store.get(NOTIFICATION_SOUND_ENABLED_KEY) is not False
        self._notification_path = str(self.store.get(NOTIFICATION_SOUND_PATH_KEY) or "")
        self._notification_sound = NotificationSound()
        self._load_prompt_editor()
        self._refresh_key_status()
        self._refresh_voiceprint_names()

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
        return list(getattr(self, "_model_options", []))

    def _get_cloud_provider_index(self) -> int:
        return self._cloud_provider_index

    def _set_cloud_provider_index(self, value: int) -> None:
        index = int(value)
        if 0 <= index < len(CLOUD_PROVIDER_IDS) and index != self._cloud_provider_index:
            self._cloud_provider_index = index
            self.cloudProviderIndexChanged.emit()
            # The previous provider's models must not linger for the new one.
            self._clear_model_options()
            self._refresh_key_status()
            self.cloudConsentChanged.emit()
            self._load_models(show_errors=False)

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
        self.promptDirtyChanged.emit()

    def _get_prompt_dirty(self) -> bool:
        return self.has_unsaved_prompts()

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
    promptDirtyChanged = Signal()

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
    cloudConsentGranted = Property(bool, _get_cloud_consent_granted, notify=cloudConsentChanged)
    cloudConsentText = Property(str, _get_cloud_consent_text, notify=cloudConsentChanged)
    cloudProviderLabels = Property("QVariantList", _get_cloud_provider_labels, constant=True)
    cloudProviderIndex = Property(
        int, _get_cloud_provider_index, _set_cloud_provider_index, notify=cloudProviderIndexChanged
    )
    promptNames = Property("QVariantList", _get_prompt_names, constant=True)
    promptPlaceholders = Property(
        "QVariantList", _get_prompt_placeholders, notify=promptIndexChanged
    )
    promptIndex = Property(int, _get_prompt_index, _set_prompt_index, notify=promptIndexChanged)
    promptText = Property(str, _get_prompt_text, _set_prompt_text, notify=promptTextChanged)
    promptDirty = Property(bool, _get_prompt_dirty, notify=promptDirtyChanged)
    promptStatusText = Property(str, _get_prompt_status_text, notify=promptStatusChanged)
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

    def _clear_model_options(self) -> None:
        if self._model_options:
            self._model_options = []
            self.modelOptionsChanged.emit()

    def _load_models(self, show_errors: bool) -> bool:
        """Fetch models for the selected provider; blank the list on any failure."""
        spec = self._provider_spec()
        key = self.key_store.get(spec.key_name)
        if not key:
            self._clear_model_options()
            if show_errors:
                self._set_key_status(f"Save a {spec.label} API key first.", ok=False)
            return False
        try:
            if spec.kind == KIND_GEMINI:
                models = GeminiClient(key_getter=lambda: key).list_models()
            else:
                models = OpenAICompatClient(
                    model="", base_url=spec.base_url, provider=spec.id, key_getter=lambda: key
                ).list_models()
        except Exception as error:
            self._clear_model_options()
            if show_errors:
                self._set_key_status(f"Could not load models: {error}", ok=False)
            return False
        if not models:
            self._clear_model_options()
            if show_errors:
                self._set_key_status(f"{spec.label} returned no models for this key.", ok=False)
            return False
        if spec.kind == KIND_GEMINI and not self._gemini_model:
            self._gemini_model = models[0]
            self.geminiModelChanged.emit()
        self._model_options = list(models)
        self.modelOptionsChanged.emit()
        self._set_key_status(f"Loaded {len(models)} models from {spec.label}.", ok=True)
        return True

    @Slot()
    def loadModels(self) -> None:
        self._load_models(show_errors=True)

    def _refresh_key_status(self) -> None:
        spec = self._provider_spec()
        available = getattr(self.key_store, "available", lambda: True)()
        if not available:
            self._key_stored = False
            self._set_key_status(
                "No OS credential manager is available; API keys cannot be stored on this system.",
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
        self._save_voiceprint_thresholds()
        self.store.set(NOTIFICATION_SOUND_ENABLED_KEY, self._notification_enabled)
        self.store.set(NOTIFICATION_SOUND_PATH_KEY, self._notification_path.strip())

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
        """Saved prompt templates from the global store (Phase 4 WS-B)."""
        return self.prompt_store.load()

    def save_prompt_set(self, prompt_set) -> None:
        self.prompt_store.save(prompt_set)
        self._session_prompt_overrides = {}
        self._load_prompt_editor()
        try:
            self.promptDirtyChanged.emit()
        except RuntimeError:
            pass

    def has_unsaved_prompts(self) -> bool:
        """True when the editor holds edits not yet saved to prompts.json."""
        try:
            base = self.prompt_store.load()
        except Exception:
            base = PromptSet()
        if self._session_prompt_overrides:
            # Any stored session edit that differs from the saved store counts.
            for key, value in self._session_prompt_overrides.items():
                try:
                    if value != base.template(key):
                        return True
                except KeyError:
                    continue
        try:
            return self._prompt_text != base.template(self._prompt_name())
        except KeyError:
            return False

    def effective_prompt_set(self):
        """PromptSet used for the next job: saved store + unsaved session edits."""
        try:
            base = self.prompt_store.load()
        except Exception:
            base = PromptSet()
        overrides = dict(self._session_prompt_overrides)
        name = self._prompt_name()
        try:
            saved_text = base.template(name)
        except KeyError:
            saved_text = ""
        if self._prompt_text and self._prompt_text != saved_text:
            overrides[name] = self._prompt_text
        # Drop edits that match the saved store (e.g. user reverted manually).
        cleaned = {}
        for key, value in overrides.items():
            try:
                if value != base.template(key):
                    cleaned[key] = value
            except KeyError:
                continue
        return base.with_overrides(cleaned) if cleaned else base

    def session_prompt_overrides(self) -> dict[str, str]:
        """Unsaved edits as a dict (empty when the editor matches the store)."""
        effective = self.effective_prompt_set()
        try:
            base = self.prompt_store.load()
        except Exception:
            base = PromptSet()
        current = effective.to_dict()
        saved = base.to_dict()
        return {key: value for key, value in current.items() if value != saved.get(key)}

    def clear_session_prompts(self) -> None:
        self._session_prompt_overrides = {}
        self._load_prompt_editor()
        try:
            self.promptDirtyChanged.emit()
        except RuntimeError:
            pass

    def _prompt_name(self) -> str:
        return TEMPLATE_NAMES[self._prompt_index]

    def _load_prompt_editor(self) -> None:
        try:
            prompt_set = self.prompt_store.load()
        except Exception:
            prompt_set = PromptSet()
        name = self._prompt_name()
        if name in self._session_prompt_overrides:
            self._prompt_text = self._session_prompt_overrides[name]
        else:
            try:
                self._prompt_text = prompt_set.template(name)
            except KeyError:
                self._prompt_text = ""
        self.promptTextChanged.emit()

    def _stash_current_editor_text(self) -> None:
        """Preserve the current editor text as a session edit before switching."""
        name = self._prompt_name()
        try:
            saved = self.prompt_store.load().template(name)
        except Exception:
            saved = None
        if self._prompt_text and self._prompt_text != saved:
            self._session_prompt_overrides[name] = self._prompt_text
        else:
            self._session_prompt_overrides.pop(name, None)

    def _set_prompt_status(self, text: str, ok: bool) -> None:
        self._prompt_status_text = text
        self._prompt_status_ok = ok
        self.promptStatusChanged.emit()

    @Slot(int)
    def selectPrompt(self, index: int) -> None:
        if 0 <= index < len(TEMPLATE_NAMES):
            self._stash_current_editor_text()
            self._prompt_index = index
            self.promptIndexChanged.emit()
            self._load_prompt_editor()
            self._set_prompt_status("", True)
            try:
                self.promptDirtyChanged.emit()
            except RuntimeError:
                pass

    @Slot()
    def savePrompt(self) -> None:
        name = self._prompt_name()
        problems = validate_template(name, self._prompt_text)
        if problems:
            self._set_prompt_status("; ".join(problems), ok=False)
            return
        current = self.prompt_store.load()
        self.prompt_store.save(current.with_overrides({name: self._prompt_text}))
        self._session_prompt_overrides.pop(name, None)
        self._set_prompt_status(f"Saved '{name}'.", ok=True)
        try:
            self.promptDirtyChanged.emit()
        except RuntimeError:
            pass

    @Slot()
    def resetPrompt(self) -> None:
        self._prompt_text = PromptSet().template(self._prompt_name())
        self.promptTextChanged.emit()
        try:
            self.promptDirtyChanged.emit()
        except RuntimeError:
            pass
        self._set_prompt_status("Loaded the built-in default; press Save to apply.", ok=True)

    @Slot()
    def reloadPrompts(self) -> None:
        self._session_prompt_overrides = {}
        self._load_prompt_editor()
        self._set_prompt_status("", True)
        try:
            self.promptDirtyChanged.emit()
        except RuntimeError:
            pass

    # -- voiceprints -----------------------------------------------------------

    @staticmethod
    def _load_voiceprint_threshold(key: str, default: float) -> float:
        try:
            value = float(JsonSettingsStore().get(key) or default)
        except (TypeError, ValueError):
            value = default
        return min(1.0, max(0.0, value))

    def _get_voiceprint_identify_threshold(self) -> float:
        return self._voiceprint_identify_threshold

    def _set_voiceprint_identify_threshold(self, value) -> None:
        self._voiceprint_identify_threshold = min(1.0, max(0.0, float(value)))
        self.voiceprintIdentifyThresholdChanged.emit()

    def _get_voiceprint_cluster_threshold(self) -> float:
        return self._voiceprint_cluster_threshold

    def _set_voiceprint_cluster_threshold(self, value) -> None:
        self._voiceprint_cluster_threshold = min(1.0, max(0.0, float(value)))
        self.voiceprintClusterThresholdChanged.emit()

    def _get_voiceprint_names(self) -> list:
        return list(self._voiceprint_names)

    def _get_voiceprint_status_text(self) -> str:
        return self._voiceprint_status_text

    def _get_voiceprint_available(self) -> bool:
        return self._voiceprint_embedder is not None

    def _get_voiceprint_enroll_name(self) -> str:
        return self._voiceprint_enroll_name

    def _set_voiceprint_enroll_name(self, value) -> None:
        self._voiceprint_enroll_name = str(value)

    def _get_voiceprint_enroll_path(self) -> str:
        return self._voiceprint_enroll_path

    def _set_voiceprint_enroll_path(self, value) -> None:
        self._voiceprint_enroll_path = str(value)

    voiceprintIdentifyThresholdChanged = Signal()
    voiceprintClusterThresholdChanged = Signal()
    voiceprintNamesChanged = Signal()
    voiceprintStatusChanged = Signal()
    voiceprintEnrollNameChanged = Signal()
    voiceprintEnrollPathChanged = Signal()

    voiceprintIdentifyThreshold = Property(
        float,
        _get_voiceprint_identify_threshold,
        _set_voiceprint_identify_threshold,
        notify=voiceprintIdentifyThresholdChanged,
    )
    voiceprintClusterThreshold = Property(
        float,
        _get_voiceprint_cluster_threshold,
        _set_voiceprint_cluster_threshold,
        notify=voiceprintClusterThresholdChanged,
    )
    voiceprintNames = Property("QVariantList", _get_voiceprint_names, notify=voiceprintNamesChanged)
    voiceprintStatusText = Property(
        str, _get_voiceprint_status_text, notify=voiceprintStatusChanged
    )
    voiceprintAvailable = Property(bool, _get_voiceprint_available, constant=True)
    voiceprintEnrollName = Property(
        str,
        _get_voiceprint_enroll_name,
        _set_voiceprint_enroll_name,
        notify=voiceprintEnrollNameChanged,
    )
    voiceprintEnrollPath = Property(
        str,
        _get_voiceprint_enroll_path,
        _set_voiceprint_enroll_path,
        notify=voiceprintEnrollPathChanged,
    )

    def voiceprint_identify_threshold(self) -> float:
        return self._voiceprint_identify_threshold

    def voiceprint_cluster_threshold(self) -> float:
        return self._voiceprint_cluster_threshold

    def _refresh_voiceprint_names(self) -> None:
        self._voiceprint_names = sorted(self._voiceprint_store.load())
        self.voiceprintNamesChanged.emit()

    @Slot()
    def refreshVoiceprints(self) -> None:
        self._refresh_voiceprint_names()

    @Slot()
    def enrollVoiceprint(self) -> None:
        name = self._voiceprint_enroll_name.strip()
        path = self._voiceprint_enroll_path.strip()
        if not name:
            self._set_voiceprint_status("Enter a name for this speaker.", ok=False)
            return
        if not path:
            self._set_voiceprint_status("Choose an audio sample for this speaker.", ok=False)
            return
        if self._voiceprint_embedder is None:
            self._set_voiceprint_status(
                "Voiceprints are unavailable: install the 'voiceprint' extra.", ok=False
            )
            return
        from pathlib import Path

        sample = Path(path)
        if not sample.is_file():
            self._set_voiceprint_status("The chosen sample was not found.", ok=False)
            return
        try:
            embedding = self._voiceprint_embedder.embed(sample)
        except Exception as error:
            logging.getLogger(__name__).warning("Voiceprint enrollment failed: %s", error)
            self._set_voiceprint_status(f"Enrollment failed: {error}", ok=False)
            return
        self._voiceprint_store.save(name, embedding)
        self._voiceprint_enroll_name = ""
        self._voiceprint_enroll_path = ""
        self.voiceprintEnrollNameChanged.emit()
        self.voiceprintEnrollPathChanged.emit()
        self._refresh_voiceprint_names()
        self._set_voiceprint_status(f"Enrolled '{name}'.", ok=True)

    @Slot(int)
    def removeVoiceprint(self, index: int) -> None:
        if 0 <= index < len(self._voiceprint_names):
            name = self._voiceprint_names[index]
            self._voiceprint_store.remove(name)
            self._refresh_voiceprint_names()
            self._set_voiceprint_status(f"Removed '{name}'.", ok=True)

    @Slot(int, str)
    def reenrollVoiceprint(self, index: int, path: str) -> None:
        """Re-embed a new sample for an existing name (overwrites its voiceprint)."""
        if not (0 <= index < len(self._voiceprint_names)):
            return
        name = self._voiceprint_names[index]
        if self._voiceprint_embedder is None:
            self._set_voiceprint_status(
                "Voiceprints are unavailable: install the 'voiceprint' extra.", ok=False
            )
            return
        from pathlib import Path

        sample = Path(path)
        if not sample.is_file():
            self._set_voiceprint_status("The chosen sample was not found.", ok=False)
            return
        try:
            embedding = self._voiceprint_embedder.embed(sample)
        except Exception as error:
            logging.getLogger(__name__).warning("Voiceprint re-enrollment failed: %s", error)
            self._set_voiceprint_status(f"Re-enrollment failed: {error}", ok=False)
            return
        self._voiceprint_store.save(name, embedding)
        self._set_voiceprint_status(f"Re-enrolled '{name}'.", ok=True)

    def _set_voiceprint_status(self, text: str, ok: bool) -> None:
        self._voiceprint_status_text = text
        self.voiceprintStatusChanged.emit()

    def _save_voiceprint_thresholds(self) -> None:
        self.store.set(VOICEPRINT_IDENTIFY_THRESHOLD_KEY, self._voiceprint_identify_threshold)
        self.store.set(VOICEPRINT_CLUSTER_THRESHOLD_KEY, self._voiceprint_cluster_threshold)

    # -- notifications ---------------------------------------------------------

    def _get_notification_enabled(self) -> bool:
        return self._notification_enabled

    def _set_notification_enabled(self, value: bool) -> None:
        self._notification_enabled = bool(value)
        self.notificationEnabledChanged.emit()

    def _get_notification_path(self) -> str:
        return self._notification_path

    def _set_notification_path(self, value) -> None:
        self._notification_path = str(value)
        self.notificationPathChanged.emit()

    def _get_notification_default(self) -> str:
        return str(app_paths.notification_sound_default())

    notificationEnabledChanged = Signal()
    notificationPathChanged = Signal()

    notificationSoundEnabled = Property(
        bool,
        _get_notification_enabled,
        _set_notification_enabled,
        notify=notificationEnabledChanged,
    )
    notificationSoundPath = Property(
        str, _get_notification_path, _set_notification_path, notify=notificationPathChanged
    )
    notificationSoundDefault = Property(str, _get_notification_default, constant=True)

    def play_notification_sound(self) -> None:
        if not self._notification_enabled:
            return
        self._notification_sound.play(self._resolve_notification_path())

    @Slot()
    def testNotificationSound(self) -> None:
        self._notification_sound.play(self._resolve_notification_path())

    def _resolve_notification_path(self) -> str:
        path = Path(self._notification_path.strip()) if self._notification_path.strip() else None
        if path is not None and path.is_file():
            return str(path)
        return str(app_paths.notification_sound_default())
