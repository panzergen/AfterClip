"""Controller tests for the QML UI layer (replace the old widget tests)."""

import json
import sys
import types
from pathlib import Path

import pytest

from app.domain.prompts import PromptSet, build_prompt_set
from app.infrastructure.model_catalog import ModelEntry, ModelSection
from app.infrastructure.presets import InMemoryPresetStore
from app.infrastructure.prompts import InMemoryPromptStore
from app.infrastructure.settings import InMemorySettingsStore
from app.ui.app import build_controllers
from app.ui.controllers.batch_controller import BatchController
from app.ui.controllers.formatting import next_playback_speed
from app.ui.controllers.history_controller import HistoryController
from app.ui.controllers.job_form_controller import JobFormController
from app.ui.controllers.record_controller import RecordController
from app.ui.controllers.settings_controller import (
    DEFAULT_SEGMENT_SECONDS,
    GEMINI_MODEL_SETTINGS_KEY,
    SEGMENT_SETTINGS_KEY,
    SettingsController,
)

pytestmark = pytest.mark.ui

GEMINI_KEY_NAME = "gemini_api_key"


class NoKeyStore:
    def get(self, name):
        return None

    def set(self, name, value):
        pass

    def delete(self, name):
        pass


class FakeExtractor:
    def __init__(self, cache_root):
        self.last_metadata = {"duration": 0}

    def extract(self, path):
        return []


@pytest.fixture
def controllers(qapp, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.ui.controllers.environment_controller.check_ollama_service",
        lambda *args, **kwargs: False,
    )
    monkeypatch.setattr("app.ui.controllers.session_controller.KeyringSecretStore", NoKeyStore)
    monkeypatch.setattr(
        "app.ui.controllers.job_form_controller.JsonSettingsStore", lambda: InMemorySettingsStore()
    )
    monkeypatch.setattr("app.ui.controllers.media_controller.VideoPreviewExtractor", FakeExtractor)
    return build_controllers(
        project_dir=tmp_path,
        output_dir=tmp_path / "out",
        batch_store_path=tmp_path / "out" / "batch_queue.json",
        history_output_dir=tmp_path / "out",
        log_path=tmp_path / "out" / "app.log",
        settings_store=InMemorySettingsStore(),
        key_store=NoKeyStore(),
        prompt_store=InMemoryPromptStore(),
        preset_store=InMemoryPresetStore(),
    )


def test_next_playback_speed_cycles():
    assert next_playback_speed(1.0) == 1.2
    assert next_playback_speed(1.2) == 1.5
    assert next_playback_speed(1.5) == 1.0


def test_advanced_panel_defaults(controllers):
    form = controllers.job_form
    assert form.embedFrames is False
    assert form.frameResolutionIndex == 0
    assert form.sceneMode is True
    assert form.intervalMode is False


def test_settings_persists_segment_length(qapp):
    store = InMemorySettingsStore()
    controller = SettingsController(store=store, key_store=NoKeyStore())
    assert controller.segment_seconds() == DEFAULT_SEGMENT_SECONDS
    controller.segmentIndex = 1  # 15 seconds
    controller.save()
    assert store.get(SEGMENT_SETTINGS_KEY) == 15.0
    assert controller.segment_seconds() == 15.0
    controller.segmentIndex = 0  # Whisper default
    assert controller.segment_seconds() is None
    controller.reportLanguage = "tr"
    controller.save()
    assert store.get("report_language") == "tr"
    assert controller.report_language() == "tr"


def test_job_form_defaults_report_language_from_settings(monkeypatch, qapp):
    store = InMemorySettingsStore({"report_language": "tr"})
    monkeypatch.setattr("app.ui.controllers.job_form_controller.JsonSettingsStore", lambda: store)
    form = JobFormController(Path("out"), Path("in"))
    assert form.reportLanguage == "tr"


def test_job_form_report_language_empty_without_setting(monkeypatch, qapp):
    monkeypatch.setattr(
        "app.ui.controllers.job_form_controller.JsonSettingsStore", lambda: InMemorySettingsStore()
    )
    form = JobFormController(Path("out"), Path("in"))
    assert form.reportLanguage == ""


def test_ollama_offline_keeps_checkbox_intent(controllers):
    form = controllers.job_form
    form.visionEnabled = True
    form.analysisEnabled = True
    form.set_ollama_enabled(False)
    assert form.visionEnabled
    assert form.analysisEnabled
    assert not form.visionAllowed
    assert not form.visionModelEnabled
    form.set_ollama_enabled(True)
    assert form.visionAllowed
    assert form.visionModelEnabled


def test_gemini_provider_enables_controls_even_when_ollama_offline(controllers):
    form = controllers.job_form
    form.set_ollama_enabled(False)
    assert not form.analysisAllowed
    form.cloudSelected = True  # Gemini
    assert form.analysisAllowed
    assert form.visionAllowed
    assert "Google Gemini" in form.aiStatus


def test_ai_provider_defaults_to_local(controllers):
    assert not controllers.job_form.cloudSelected  # T18: nothing cloud by default


def test_model_catalog_groups_by_provider_and_filters_by_capability(controllers):
    sections = (
        ModelSection(
            "Ollama (local)",
            "ollama",
            (
                ModelEntry("ollama", "llama3.1:8b", text_capable=True, vision_capable=False),
                ModelEntry("ollama", "llava:7b", text_capable=True, vision_capable=True),
            ),
        ),
        ModelSection(
            "Gemini (cloud API)",
            "gemini",
            (ModelEntry("gemini", "gemini-flash-latest", text_capable=True, vision_capable=True),),
        ),
    )
    controllers.job_form.populate_models(sections)
    analysis = [
        entry["name"] for entry in controllers.job_form.analysisEntries if not entry["header"]
    ]
    vision = [entry["name"] for entry in controllers.job_form.visionEntries if not entry["header"]]
    assert "llama3.1:8b" in analysis
    assert "gemini-flash-latest" in analysis
    assert "llava:7b" in vision and "gemini-flash-latest" in vision
    assert "llama3.1:8b" not in vision


def test_selecting_catalog_model_switches_provider(controllers):
    sections = (
        ModelSection(
            "Gemini (cloud API)",
            "gemini",
            (ModelEntry("gemini", "gemini-flash-latest", text_capable=True, vision_capable=True),),
        ),
    )
    controllers.job_form.populate_models(sections)
    entries = controllers.job_form.analysisEntries
    index = next(i for i, entry in enumerate(entries) if entry["name"] == "gemini-flash-latest")
    controllers.job_form.selectAnalysisModel(index)
    assert controllers.job_form.cloudSelected  # switched to Gemini
    assert controllers.job_form.analysisModelText == "gemini-flash-latest"
    assert controllers.job_form.selected_ai_model() == ("gemini", "gemini-flash-latest")


def test_typed_model_falls_back_to_provider_combo(controllers):
    sections = (
        ModelSection(
            "Ollama (local)",
            "ollama",
            (ModelEntry("ollama", "llama3.1:8b", text_capable=True, vision_capable=False),),
        ),
    )
    controllers.job_form.populate_models(sections)
    controllers.job_form.analysisModelText = "my-custom-model"
    assert controllers.job_form.selected_ai_model() == ("ollama", "my-custom-model")
    controllers.job_form.cloudSelected = True
    assert controllers.job_form.selected_ai_model() == ("gemini", "my-custom-model")


def test_batch_enqueue_and_statuses(qapp, tmp_path):
    from app.application.batch import BatchStore

    controller = BatchController(BatchStore(tmp_path / "batch_queue.json"))
    assert controller.model.rowCount() == 0
    controller.enqueue_from_form(
        [Path("a.mp4"), Path("b.wav")],
        {"output_dir": str(tmp_path / "out"), "model": "tiny"},
    )
    assert controller.model.rowCount() == 2
    assert controller.model.data(controller.model.index(0), controller.model.NameRole) == "a.mp4"
    assert (
        controller.model.data(controller.model.index(0), controller.model.StatusRole) == "pending"
    )
    # T26b: a stale running job recovers to pending in the display
    controller.store.update(controller.model.job_id(0), status="running")
    controller.refresh()
    assert (
        controller.model.data(controller.model.index(0), controller.model.StatusRole) == "pending"
    )


def test_history_lists_jobs_and_details(qapp, tmp_path):
    job_dir = tmp_path / "myjob"
    job_dir.mkdir()
    (job_dir / "job_state.json").write_text(
        json.dumps({"status": "Succeeded", "input_path": "x/myjob.mp4"}), encoding="utf-8"
    )
    (job_dir / "Summary_Report.md").write_text(
        "# AfterClip Processing Report\n\nAll good", encoding="utf-8"
    )
    controller = HistoryController(tmp_path, tmp_path / "app.log")
    controller.refresh()
    assert controller.model.rowCount() == 1
    assert controller.model.data(controller.model.index(0), controller.model.NameRole) == "myjob"
    assert "All good" in controller.detailsText
    assert "(log file not found)" in controller.logText


def test_batch_enqueue_captures_form_settings(controllers, tmp_path):
    """Regression: batch jobs must capture the job-form settings (VTT, AI, frames)."""
    form = controllers.job_form
    form.add_support_files([str(Path("talk.vtt"))])
    form.embedFrames = True
    form.analysisEnabled = True
    form.visionEnabled = True
    controllers.media.toggleBookmarkAt(5.0)
    controllers.batch.add_files([str(tmp_path / "a.mp4")])
    job = controllers.batch.store.load()[-1]
    assert job.speaker_vtt_path == str(Path("talk.vtt"))
    assert job.embed_frames is True
    assert job.analyze_text is True
    assert job.analyze_vision is True
    assert job.frame_modes == ("scene",)
    assert job.highlight_times == (5.0,)
    assert job.output_dir == form.output_text()


def test_batch_start_refreshes_pending_settings(controllers, tmp_path):
    """Regression: configuring the form after adding must apply on Start."""
    controllers.job_form.embedFrames = False
    controllers.batch.add_files([str(tmp_path / "a.mp4")])
    assert controllers.batch.store.load()[-1].embed_frames is False
    controllers.job_form.embedFrames = True
    controllers.batch._refresh_pending_settings()
    assert controllers.batch.store.load()[-1].embed_frames is True


def test_support_files_cleared_when_input_changes(controllers, tmp_path):
    """Support files belong to one media; changing the input clears them."""
    form = controllers.job_form
    session = controllers.session
    first = tmp_path / "first.mp4"
    first.write_bytes(b"x")
    second = tmp_path / "second.mp4"
    second.write_bytes(b"x")
    session.select_input_path(str(first))
    form.add_support_files([str(tmp_path / "talk.vtt")])
    assert form.support_files()
    session.select_input_path(str(first))  # same file: kept
    assert form.support_files()
    session.select_input_path(str(second))  # different file: cleared
    assert form.support_files() == ()


def test_reuse_transcription_resolves_cached_job(controllers, tmp_path):
    """The reuse option targets the job folder matching the selected input."""
    source = tmp_path / "meeting.mp4"
    source.write_bytes(b"x")
    job = tmp_path / "out" / "meeting"
    (job / "Transcripts").mkdir(parents=True)
    (job / "Transcripts" / "converted_audio.srt").write_text("1\n", encoding="utf-8")
    (job / "job_state.json").write_text(
        json.dumps(
            {
                "input_path": str(source),
                "status": "Succeeded",
                "steps": {"transcription": {"status": "completed"}},
            }
        ),
        encoding="utf-8",
    )
    form = controllers.job_form
    form.outputDir = str(tmp_path / "out")
    assert form.reuseTranscription is False
    form.reuseTranscription = True
    assert controllers.session._resolve_resume_dir(source) == job
    form.reuseTranscription = False
    assert controllers.session._resolve_resume_dir(source) is None


def test_settings_saves_and_deletes_gemini_key(qapp, monkeypatch):
    from app.infrastructure.secrets import KeyringSecretStore

    store = {}
    fake_keyring = types.ModuleType("keyring")
    fake_keyring.set_password = lambda service, name, value: store.__setitem__(
        (service, name), value
    )
    fake_keyring.get_password = lambda service, name: store.get((service, name))
    fake_keyring.delete_password = lambda service, name: store.pop((service, name), None)
    fake_keyring.errors = types.SimpleNamespace(
        PasswordDeleteError=type("PasswordDeleteError", (Exception,), {})
    )
    monkeypatch.setitem(sys.modules, "keyring", fake_keyring)
    key_store = KeyringSecretStore(service="afterclip-test")

    settings_store = InMemorySettingsStore()
    controller = SettingsController(store=settings_store, key_store=key_store)
    assert "No Gemini (cloud) API key stored" in controller.keyStatusText
    controller.keyInput = "sk-ui-gemini-key"
    controller.saveKey()
    assert store[("afterclip-test", GEMINI_KEY_NAME)] == "sk-ui-gemini-key"
    assert "stored in the OS credential manager" in controller.keyStatusText
    controller.deleteKey()
    assert ("afterclip-test", GEMINI_KEY_NAME) not in store
    controller.geminiModel = "gemini-2.5-flash"
    controller.save()
    assert settings_store.get(GEMINI_MODEL_SETTINGS_KEY) == "gemini-2.5-flash"


def test_clip_validity_drives_start_enabled(controllers):
    session, media = controllers.session, controllers.media
    media.apply_metadata({"duration": 30, "streams": []})
    assert media.clip_is_valid()
    assert session.startEnabled
    media.clipStartText = "00:00:20"
    media.clipEndText = "00:00:10"
    assert not media.clip_is_valid()
    assert not session.startEnabled
    media.clipStartText = "00:00:05"
    assert media.clip_is_valid()
    assert session.startEnabled


def test_start_preview_ignores_missing_files(controllers, tmp_path):
    session, media = controllers.session, controllers.media
    session.select_input_path(str(tmp_path / "ghost.wav"))
    assert not media.has_source()


def test_audio_selection_disables_media_but_never_record(controllers, tmp_path):
    """Regression: audio files must disable only the Media tab, never Record."""
    wav = tmp_path / "voice.wav"
    wav.write_bytes(b"fixture")
    mp4 = tmp_path / "video.mp4"
    mp4.write_bytes(b"fixture")
    controllers.media.set_source(mp4)  # seed a source
    session = controllers.session
    session.select_input_path(str(wav))
    assert not session.mediaTabEnabled  # audio: media disabled
    assert controllers.record.micSelected  # record state untouched and usable
    session.select_input_path(str(mp4))
    assert session.mediaTabEnabled  # video: media back on


def test_recording_buttons_toggle_on_start(qapp, monkeypatch, tmp_path):
    started = []

    class FakeRecorder:
        def start(self, path, microphone, system_audio, device="default"):
            started.append(path)
            return path

    monkeypatch.setattr("app.ui.controllers.record_controller.AudioRecorder", FakeRecorder)
    monkeypatch.setattr("app.ui.controllers.record_controller.list_microphone_devices", lambda: [])
    monkeypatch.setattr("app.ui.controllers.record_controller.supports_system_audio", lambda: False)
    controller = RecordController()
    controller.set_output_dir("")
    controller.startRecording()
    assert controller.statusText == "Select an output directory first."
    assert controller.recording is False
    controller.set_output_dir(str(tmp_path))
    controller.startRecording()
    assert started and started[0].parent == tmp_path
    assert controller.recording


def test_support_files_first_vtt_is_diarization(controllers):
    form = controllers.job_form
    form.add_support_files([str(Path("a.vtt")), str(Path("b.png")), str(Path("c.vtt"))])
    assert form.speaker_vtt_from_support() == str(Path("a.vtt"))
    assert len(form.supportFiles) == 3
    assert form.supportFiles[0]["note"] == "speaker diarization"
    form.removeSupportFile(0)
    assert form.speaker_vtt_from_support() == str(Path("c.vtt"))


def test_batch_and_single_job_are_mutually_exclusive(controllers, tmp_path):
    session, batch = controllers.session, controllers.batch
    batch.enqueue_from_form([Path("a.mp4")], {"output_dir": str(tmp_path / "out")})
    session.on_batch_running(True)
    assert not session.startEnabled  # single Start blocked by running batch
    session.on_batch_running(False)
    assert session.startEnabled
    session.batch.set_external_job_running(True)
    assert not batch.startEnabled  # batch Start blocked by running single job
    session.batch.set_external_job_running(False)
    assert batch.startEnabled


def test_batch_snapshot_captures_form_settings(controllers):
    form = controllers.job_form
    form.whisperModel = "small"
    form.language = "en"
    form.task = " Summarize "
    form.analysisEnabled = True
    snapshot = form.snapshot()
    assert snapshot["model"] == "small"
    assert snapshot["language"] == "en"
    assert snapshot["task"] == "Summarize"
    # Default model text resolves to a selection, so analysis runs
    assert snapshot["analyze_text"] is True and snapshot["text_model"]
    form.analysisModelText = ""  # cleared text -> no selection -> analysis disabled
    snapshot = form.snapshot()
    assert snapshot["analyze_text"] is False


def test_settings_consent_grant_and_revoke(controllers):
    settings = controllers.settings
    assert settings.cloudConsentGranted is False
    assert settings.has_cloud_consent("gemini") is False

    settings.grantGeminiConsent()
    assert settings.cloudConsentGranted is True
    assert settings.has_cloud_consent("gemini") is True

    settings.revokeGeminiConsent()
    assert settings.cloudConsentGranted is False
    assert settings.has_cloud_consent("gemini") is False


def test_local_provider_needs_no_consent(controllers):
    assert controllers.settings.has_cloud_consent("ollama") is True


def test_start_gates_cloud_job_behind_consent(controllers, monkeypatch, tmp_path):
    session = controllers.session
    form = controllers.job_form
    form.cloudSelected = True
    form.analysisEnabled = True

    requests = []
    session.cloudConsentRequested.connect(
        lambda provider, model, summary: requests.append((provider, summary))
    )
    monkeypatch.setattr(
        session,
        "_validate_start_conditions",
        lambda: (tmp_path / "in.mp4", tmp_path / "out", None, None),
    )

    session.startJob()
    assert requests and requests[0][0] == "gemini"
    assert "transcript text" in requests[0][1]
    assert session.worker is None  # gated before a worker was created

    session.grantCloudConsentAndStart()
    assert session._pending_consent_provider is None
    assert controllers.settings.has_cloud_consent("gemini") is True


def test_settings_prompt_set_roundtrip(controllers):
    settings = controllers.settings
    assert settings.prompt_set().summary  # built-in defaults
    settings.save_prompt_set(build_prompt_set({"summary": "CUSTOM {lang} {transcript}"}))
    assert settings.prompt_set().summary == "CUSTOM {lang} {transcript}"


def test_session_provider_prompts_uses_store(controllers):
    controllers.settings.save_prompt_set(
        build_prompt_set({"summary": "FROM STORE {lang} {transcript}"})
    )
    assert controllers.session._provider_prompts().summary == "FROM STORE {lang} {transcript}"


def test_session_provider_prompts_none_without_store(controllers):
    controllers.session.prompt_store = None
    assert controllers.session._provider_prompts() is None


def test_prompt_editor_select_save_validate(controllers):
    settings = controllers.settings
    assert settings.promptText == PromptSet().summary
    assert settings.promptPlaceholders

    settings.promptText = "no placeholders here"
    settings.savePrompt()
    assert settings.promptStatusOk is False
    assert "missing" in settings.promptStatusText

    settings.promptText = "CUSTOM {lang} {transcript}"
    settings.savePrompt()
    assert settings.promptStatusOk is True
    assert settings.prompt_set().summary == "CUSTOM {lang} {transcript}"


def test_prompt_editor_select_changes_template(controllers):
    settings = controllers.settings
    settings.selectPrompt(2)  # summary, summary_combine, highlights, ...
    assert settings.promptIndex == 2
    assert settings.promptText == PromptSet().highlights
    assert "srt_content" in settings.promptPlaceholders


def test_prompt_editor_reset_loads_default(controllers):
    settings = controllers.settings
    settings.promptText = "changed"
    settings.resetPrompt()
    assert settings.promptText == PromptSet().summary


def test_presets_save_apply_delete(controllers):
    presets = controllers.presets
    form = controllers.job_form
    settings = controllers.settings

    assert presets.names == []
    assert presets.hasPresets is False

    form.whisperModel = "small"
    form.frameInterval = 25
    settings.save_prompt_set(build_prompt_set({"summary": "PRESET {lang} {transcript}"}))
    presets.newName = "meeting"
    presets.saveCurrent()
    assert presets.names == ["meeting"]
    assert presets.hasPresets is True

    # Change the form and reset prompts, then apply the preset.
    form.whisperModel = "large"
    form.frameInterval = 5
    settings.save_prompt_set(build_prompt_set({}))
    presets.selectedIndex = 0
    presets.applySelected()
    assert form.whisperModel == "small"
    assert form.frameInterval == 25
    assert settings.prompt_set().summary == "PRESET {lang} {transcript}"

    presets.deleteSelected()
    assert presets.names == []
    assert presets.hasPresets is False


def test_validate_corrects_output_dir_that_is_a_job_folder(controllers, monkeypatch, tmp_path):
    session = controllers.session
    form = controllers.job_form

    source = tmp_path / "in.mp4"
    source.write_bytes(b"x")
    session._current_input = str(source)

    job_folder = tmp_path / "out" / "somejob"
    job_folder.mkdir(parents=True)
    (job_folder / "job_state.json").write_text("{}", encoding="utf-8")
    form.outputDir = str(job_folder)

    monkeypatch.setattr(
        "app.ui.controllers.session_controller.check_environment",
        lambda: types.SimpleNamespace(ffmpeg=True, ffprobe=True, whisper=True),
    )
    alerts = []
    session.alert.connect(lambda title, text: alerts.append((title, text)))

    conditions = session._validate_start_conditions()
    assert conditions is not None
    assert conditions[1] == tmp_path / "out"
    assert form.outputDir == str(tmp_path / "out")
    assert any("corrected" in title.lower() for title, _ in alerts)


class RecordingKeyStore:
    def __init__(self):
        self.values = {}

    def get(self, name):
        return self.values.get(name)

    def set(self, name, value):
        self.values[name] = value

    def delete(self, name):
        self.values.pop(name, None)

    def available(self):
        return True


def test_settings_key_uses_selected_provider(qapp):
    settings = SettingsController(
        store=InMemorySettingsStore(),
        key_store=RecordingKeyStore(),
        prompt_store=InMemoryPromptStore(),
    )
    keys = settings.key_store.values
    settings.keyInput = "sk-gemini"
    settings.saveKey()
    assert keys.get("gemini_api_key") == "sk-gemini"

    settings.cloudProviderIndex = 1  # openrouter
    settings.keyInput = "sk-openrouter"
    settings.saveKey()
    assert keys.get("openrouter_api_key") == "sk-openrouter"


def test_settings_consent_is_per_provider(controllers):
    settings = controllers.settings
    settings.cloudProviderIndex = 1  # openrouter
    assert settings.cloudConsentGranted is False
    settings.grantConsent()
    assert settings.cloudConsentGranted is True
    assert settings.has_cloud_consent("openrouter") is True
    assert settings.has_cloud_consent("gemini") is False
    settings.revokeConsent()
    assert settings.cloudConsentGranted is False


def test_settings_provider_switch_updates_key_status(controllers):
    settings = controllers.settings
    assert "Gemini" in settings.keyStatusText
    settings.cloudProviderIndex = 2  # opencode_go
    assert "OpenCode Go" in settings.keyStatusText


def test_populate_models_header_labels_are_plain_titles(controllers):
    sections = (
        ModelSection(
            "Ollama (local)",
            "ollama",
            (ModelEntry("ollama", "llama3.1:8b", text_capable=True),),
        ),
    )
    controllers.job_form.populate_models(sections)
    headers = [entry for entry in controllers.job_form.analysisEntries if entry["header"]]
    assert headers and headers[0]["label"] == "Ollama (local)"


def test_populate_models_restores_last_choice(controllers, monkeypatch):
    form = controllers.job_form
    monkeypatch.setattr(
        form,
        "_load_model_choice",
        lambda analysis: {"provider": "gemini", "name": "gemini-2.5-flash"}
        if not analysis
        else None,
    )
    sections = (
        ModelSection(
            "Gemini (cloud API)",
            "gemini",
            (ModelEntry("gemini", "gemini-2.5-flash", text_capable=True, vision_capable=True),),
        ),
    )
    form.populate_models(sections)
    assert form.analysisModelText == "gemini-2.5-flash"
    assert form.cloudSelected is True


def test_settings_provider_switch_clears_models(controllers):
    settings = controllers.settings
    settings._model_options = ["leftover/model"]
    settings.cloudProviderIndex = 1  # openrouter; no key stored -> blank
    assert settings.modelOptions == []


def test_settings_load_models_without_key_blanks_list(controllers):
    settings = controllers.settings
    settings._model_options = ["leftover/model"]
    settings.loadModels()
    assert settings.modelOptions == []
    assert "API key first" in settings.keyStatusText


def test_lookup_model_is_strict(controllers):
    form = controllers.job_form
    form._analysis_entries = [
        {"label": "Ollama", "header": True, "provider": "ollama", "name": ""},
        {"label": "llama3", "header": False, "provider": "ollama", "name": "llama3"},
    ]
    form.analysisModelText = "llama3"
    assert form.lookup_ai_model() == ("ollama", "llama3")
    form.analysisModelText = "deepseek-v4-flash:cloud"
    assert form.lookup_ai_model() is None


def test_resolve_providers_rejects_unknown_model(controllers):
    session = controllers.session
    form = controllers.job_form
    form.analysisEnabled = True
    form._analysis_entries = []
    form.analysisModelText = "deepseek-v4-flash:cloud"
    alerts = []
    session.alert.connect(lambda title, message: alerts.append((title, message)))
    text_provider, vision_provider = session._resolve_providers()
    assert text_provider is False and vision_provider is False
    assert alerts and "unavailable" in alerts[-1][0].lower()


def test_model_choice_keys_are_not_swapped(qapp, monkeypatch, tmp_path):
    from app.infrastructure.settings import InMemorySettingsStore
    from app.ui.controllers.job_form_controller import JobFormController

    store = InMemorySettingsStore()
    monkeypatch.setattr(
        "app.ui.controllers.job_form_controller.JsonSettingsStore", lambda: store
    )
    form = JobFormController(tmp_path, tmp_path)
    form._analysis_entries = [
        {"label": "OpenRouter", "header": True, "provider": "openrouter", "name": ""},
        {"label": "text-model", "header": False, "provider": "openrouter", "name": "text-model"},
    ]
    form._vision_entries = [
        {"label": "OpenCode Go", "header": True, "provider": "opencode_go", "name": ""},
        {
            "label": "vision-model",
            "header": False,
            "provider": "opencode_go",
            "name": "vision-model",
        },
    ]
    form.selectAnalysisModel(1)
    form.selectVisionModel(1)
    assert store.get("analysis_model_choice") == {"provider": "openrouter", "name": "text-model"}
    assert store.get("vision_model_choice") == {"provider": "opencode_go", "name": "vision-model"}
    assert form.analysisModelText == "text-model"
    assert form.visionModelText == "vision-model"


def test_media_type_suggestion_from_metadata(controllers):
    session = controllers.session
    session.media.last_metadata = {
        "duration": 2400,
        "streams": [{"type": "video"}, {"type": "audio"}],
    }
    session._current_input = "F:/media/Falcon Weekly - Meeting Recording.mp4"
    session.refreshMediaType()
    assert "meeting" in session.mediaTypeText


def test_sanitizer_config_respects_per_job_toggle(controllers):
    session = controllers.session
    assert session._sanitizer_config().enabled is True
    session.job_form.transcriptFilter = False
    assert session._sanitizer_config().enabled is False


def test_forecast_heuristic_without_history(controllers):
    session = controllers.session
    assert session.forecastText == ""
    session.media.duration_seconds = 600.0
    session.refreshForecast()
    assert session.forecastText.startswith("Rough estimate")


def test_forecast_uses_similar_history(controllers, tmp_path):
    out = tmp_path / "out"
    for index in range(3):
        folder = out / f"history{index}"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "job_state.json").write_text(
            json.dumps(
                {
                    "media": {"duration": 300},
                    "run_settings": {
                        "model": "turbo",
                        "frame_modes": ["interval"],
                        "frame_resolution": "full",
                        "analyze_text": False,
                        "analyze_vision": False,
                    },
                    "steps": {"transcription": {"duration_seconds": 90}},
                }
            ),
            encoding="utf-8",
        )
    session = controllers.session
    session.media.duration_seconds = 300.0
    session.job_form.whisperModel = "turbo"
    session.job_form.intervalMode = True
    session.job_form.sceneMode = False
    session.refreshForecast()
    assert session.forecastText.startswith("Estimated")
    assert "similar job" in session.forecastText

