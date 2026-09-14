"""Composition root: builds and wires every UI controller.

Used by ``app.main`` (QML entry point) and by the controller tests.
"""

from dataclasses import dataclass
from pathlib import Path

import app.app_paths as app_paths
from app.application.batch import BatchStore
from app.infrastructure.prompts import JsonPromptStore
from app.ui.controllers.batch_controller import BatchController
from app.ui.controllers.environment_controller import EnvironmentController
from app.ui.controllers.history_controller import HistoryController
from app.ui.controllers.job_form_controller import JobFormController
from app.ui.controllers.media_controller import MediaController
from app.ui.controllers.record_controller import RecordController
from app.ui.controllers.session_controller import SessionController
from app.ui.controllers.settings_controller import SettingsController


@dataclass
class AppControllers:
    environment: EnvironmentController
    job_form: JobFormController
    media: MediaController
    record: RecordController
    batch: BatchController
    history: HistoryController
    settings: SettingsController
    session: SessionController

    def connect(self) -> None:
        """Wire controller signals (idempotent; safe to call once per instance)."""
        self.environment.ollamaAvailabilityChanged.connect(self.session.on_ollama_availability)
        self.media.framesReady.connect(self.session.on_frames_ready)
        self.media.metadataReady.connect(lambda metadata: self.media.apply_metadata(metadata))
        self.media.failed.connect(self.session.on_preview_failed)
        self.media.clipValidityChanged.connect(self.session.on_clip_validity)
        self.media.applyRequested.connect(self.session.apply_media_name)
        self.record.recordingStarted.connect(
            lambda name: self.session._update_title(name, "recording...")
        )
        self.record.recordingReady.connect(lambda path: self.session.select_input_path(str(path)))
        self.record.recordingFailed.connect(
            lambda _message: self.session._update_title(status="recording error")
        )
        self.batch.batchRunningChanged.connect(self.session.on_batch_running)
        self.batch.set_enqueue_settings_provider(self.session.batch_enqueue_settings)
        self.job_form.outputChanged.connect(self.record.set_output_dir)
        self.job_form.analysisEnabledChanged.connect(self.session.on_analysis_toggled)
        self.session._update_title()
        self.record.set_output_dir(self.job_form.outputDir)


def build_controllers(
    project_dir: Path | None = None,
    output_dir: Path | None = None,
    preview_cache_root: Path | None = None,
    batch_store_path: Path | None = None,
    history_output_dir: Path | None = None,
    log_path: Path | None = None,
    settings_store=None,
    key_store=None,
    prompt_store=None,
) -> AppControllers:
    """Create all controllers with default (or injected) paths and wire them."""
    project_dir = project_dir or app_paths.project_dir()
    output_dir = output_dir or app_paths.default_output_dir()
    log_path = log_path or app_paths.log_file()
    prompt_store = prompt_store or JsonPromptStore()

    environment = EnvironmentController()
    job_form = JobFormController(output_dir, app_paths.default_input_dir())
    media = MediaController(preview_cache_root or project_dir / ".cache" / "previews")
    record = RecordController()
    batch = BatchController(BatchStore(batch_store_path or output_dir / "batch_queue.json"))
    history = HistoryController(history_output_dir or output_dir, log_path)
    settings = SettingsController(
        store=settings_store, key_store=key_store, prompt_store=prompt_store
    )
    session = SessionController(
        media, job_form, batch, history, environment, record, settings, prompt_store
    )
    controllers = AppControllers(
        environment=environment,
        job_form=job_form,
        media=media,
        record=record,
        batch=batch,
        history=history,
        settings=settings,
        session=session,
    )
    controllers.connect()
    return controllers
