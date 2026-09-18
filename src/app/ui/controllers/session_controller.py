import logging
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Property, QObject, QThread, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

import app.app_paths as app_paths
from app.application.cloud_consent import payload_summary
from app.application.forecast import forecast, load_history
from app.application.headless import resolve_topics
from app.application.media_type import classify_tier1, signals_from_metadata
from app.application.provider_registry import (
    KIND_GEMINI,
    KIND_OPENAI_COMPAT,
    cloud_provider_ids,
    get_provider,
    is_cloud,
)
from app.application.service_io import find_reusable_job_dir
from app.application.transcript_sanitizer import SanitizerConfig
from app.domain.constants import VIDEO_SUFFIXES
from app.domain.models import ProgressEvent, TranscriptionRequest
from app.infrastructure.diagnostics import check_environment, check_output_dir
from app.infrastructure.gemini import GeminiTextProvider, GeminiVisionProvider
from app.infrastructure.model_catalog import collect_catalog
from app.infrastructure.ollama import OllamaTextProvider, OllamaVisionProvider, check_ollama_service
from app.infrastructure.openai_compat import (
    OpenAICompatTextProvider,
    OpenAICompatVisionProvider,
)
from app.infrastructure.process import FfmpegMediaTool, WhisperCliProvider
from app.infrastructure.secrets import KeyringSecretStore
from app.ui.controllers.formatting import local_path
from app.workers.transcription_worker import TranscriptionWorker

LOGGER = logging.getLogger(__name__)


class SessionController(QObject):
    """App-level session state: input selection, single-job lifecycle, exclusivity."""

    alert = Signal(str, str)
    cloudConsentRequested = Signal(str, str, str)

    def __init__(
        self,
        media,
        job_form,
        batch,
        history,
        env,
        record,
        settings=None,
        prompt_store=None,
        parent=None,
    ):
        super().__init__(parent)
        self.media = media
        self.job_form = job_form
        self.batch = batch
        self.history = history
        self.env = env
        self.record = record
        self.settings = settings
        self.prompt_store = prompt_store
        self.thread = None
        self.worker = None
        self.output_name = ""
        self._input_basename = None
        self.input_dir = app_paths.default_input_dir()
        self._status_text = "Ready"
        self._title = "AfterClip"
        self._progress_value = 0
        self._cancel_enabled = False
        self._media_tab_enabled = True
        self._start_ready = True
        self._clip_valid = True
        self._batch_running = False
        self._job_running = False
        self._output_folder = ""
        self._input_paths: list[dict] = []
        self._current_input = ""
        self._pending_consent_provider = None
        self._forecast_text = ""
        self._media_type_text = ""

    # -- Qt properties --------------------------------------------------------

    def _get_title(self) -> str:
        return self._title

    def _get_status_text(self) -> str:
        return self._status_text

    def _get_progress_value(self) -> int:
        return self._progress_value

    def _get_start_enabled(self) -> bool:
        return (
            self.worker is None
            and not self._batch_running
            and self._start_ready
            and self._clip_valid
        )

    def _get_cancel_enabled(self) -> bool:
        return self._cancel_enabled

    def _get_media_tab_enabled(self) -> bool:
        return self._media_tab_enabled

    def _get_input_paths(self) -> list:
        return self._input_paths

    def _get_current_input(self) -> str:
        return self._current_input

    def _get_job_running(self) -> bool:
        return self._job_running

    def _get_output_folder(self) -> str:
        return self._output_folder

    def _get_has_output_folder(self) -> bool:
        return bool(self._output_folder)

    def _get_forecast_text(self) -> str:
        return self._forecast_text

    def _get_media_type_text(self) -> str:
        return self._media_type_text

    def _set_output_folder(self, folder: str) -> None:
        if self._output_folder != folder:
            self._output_folder = folder
            self.outputFolderChanged.emit()

    def batch_enqueue_settings(self) -> dict:
        """Settings captured when a media file is added to the batch queue."""
        settings = dict(self.job_form.snapshot())
        settings["output_dir"] = self.job_form.output_text()
        settings["highlight_times"] = tuple(self.media.highlight_times)
        settings["output_name"] = self.output_name
        return settings

    titleChanged = Signal()
    statusTextChanged = Signal()
    progressValueChanged = Signal()
    startEnabledChanged = Signal()
    cancelEnabledChanged = Signal()
    mediaTabEnabledChanged = Signal()
    inputPathsChanged = Signal()
    currentInputChanged = Signal()
    jobRunningChanged = Signal()
    outputFolderChanged = Signal()
    forecastTextChanged = Signal()
    mediaTypeTextChanged = Signal()

    title = Property(str, _get_title, notify=titleChanged)
    statusText = Property(str, _get_status_text, notify=statusTextChanged)
    progressValue = Property(int, _get_progress_value, notify=progressValueChanged)
    startEnabled = Property(bool, _get_start_enabled, notify=startEnabledChanged)
    cancelEnabled = Property(bool, _get_cancel_enabled, notify=cancelEnabledChanged)
    mediaTabEnabled = Property(bool, _get_media_tab_enabled, notify=mediaTabEnabledChanged)
    inputPaths = Property("QVariantList", _get_input_paths, notify=inputPathsChanged)
    currentInput = Property(str, _get_current_input, notify=currentInputChanged)
    jobRunning = Property(bool, _get_job_running, notify=jobRunningChanged)
    outputFolder = Property(str, _get_output_folder, notify=outputFolderChanged)
    hasOutputFolder = Property(bool, _get_has_output_folder, notify=outputFolderChanged)
    forecastText = Property(str, _get_forecast_text, notify=forecastTextChanged)
    mediaTypeText = Property(str, _get_media_type_text, notify=mediaTypeTextChanged)

    # -- input selection ---------------------------------------------------------

    def _get_pending_input(self) -> str:
        return ""

    def _set_pending_input(self, value) -> None:
        """Queue an input path from QML and apply it off the JS call stack.

        QML must not invoke Python slots with string/url arguments (crashes in
        this PySide6 build), so the dialogs assign this property instead and
        the heavy work runs on the next event-loop tick.
        """
        path = local_path(value)
        QTimer.singleShot(0, lambda: self.select_input_path(path))

    pendingInput = Property(str, _get_pending_input, _set_pending_input)

    def select_input_path(self, path) -> None:
        # QVariant, not str: converting a QML `url` argument into a Python str
        # crashes in this PySide6 build (faults in Shiboken::String::toCString).
        path = Path(local_path(path)).resolve()
        if str(path) != self._current_input:
            # Support files (speaker VTT, references) belong to the previous
            # media; start clean for the newly selected file.
            self.job_form.clear_support_files()
        self.media.name = path.stem
        self.output_name = ""
        self._input_basename = path.name
        self._update_title(path.name, "Ready")
        for entry in self._input_paths:
            if entry["path"] == str(path):
                self._set_current_input(str(path))
                break
        else:
            new_entry = {"name": path.name, "path": str(path)}
            self._input_paths = [*self._input_paths, new_entry]
            self.inputPathsChanged.emit()
            self._set_current_input(str(path))
        self._on_input_changed()

    def _set_current_input(self, path: str) -> None:
        if self._current_input != path:
            self._current_input = path
            self.currentInputChanged.emit()

    def current_input_path(self) -> Path | None:
        return Path(self._current_input) if self._current_input else None

    def _on_input_changed(self) -> None:
        self.media.reset_clip_controls()
        path = self.current_input_path()
        if path and path.is_file():
            self.media.set_metadata_text("Loading media metadata...")
        self._start_preview()

    @Slot()
    def _start_preview(self) -> None:
        path = self.current_input_path()
        if not path or not path.is_file():
            return
        is_video = path.suffix.lower() in VIDEO_SUFFIXES
        # Enable/disable by controller reference: audio disables the Media tab
        # only, never Record (regression: old index-based code broke Record).
        self._media_tab_enabled = is_video
        self.mediaTabEnabledChanged.emit()
        if not is_video:
            self._set_status("Audio selected; video preview is unavailable.")
        else:
            self.media.set_source(path)
            self._set_status("Preparing 10 preview frames...")
        self._start_ready = False
        self.startEnabledChanged.emit()
        self.media.start_preview(path)

    # -- media callbacks -------------------------------------------------------------

    @Slot(tuple)
    def on_frames_ready(self, frames: tuple) -> None:
        self._set_status(
            "Preview ready. Click a frame to jump there."
            if frames
            else "Audio selected; video preview is unavailable."
        )
        self._start_ready = True
        self.startEnabledChanged.emit()
        self.refreshForecast()
        self.refreshMediaType()

    @Slot()
    def refreshMediaType(self) -> None:
        """Tier-1 media-type suggestion (instant, never blocks; WS-D)."""
        metadata = getattr(self.media, "last_metadata", {}) or {}
        text = ""
        if metadata:
            input_path = self.current_input_path()
            guess = classify_tier1(
                signals_from_metadata(
                    str(input_path) if input_path else str(metadata.get("file_name", "")),
                    metadata,
                    bool(self.job_form.speaker_vtt_from_support()),
                )
            )
            if guess.media_type != "other":
                text = f"Media type: {guess.media_type} ({round(guess.confidence * 100)}%)"
        if text != self._media_type_text:
            self._media_type_text = text
            self.mediaTypeTextChanged.emit()

    @Slot()
    def refreshForecast(self) -> None:
        """Update the pre-start time estimate from history + current settings."""
        form = self.job_form
        duration = float(getattr(self.media, "duration_seconds", 0.0) or 0.0)
        clip_start, clip_end = self.media.clip_seconds()
        if clip_end and clip_end > clip_start:
            duration = clip_end - clip_start
        history = load_history(self.history.output_dir) if self.history is not None else []
        result = forecast(
            duration,
            form.whisperModel,
            form.selected_frame_modes(),
            form.analysisEnabled,
            form.visionEnabled,
            form.selected_frame_resolution(),
            history,
        )
        text = result.text()
        if text != self._forecast_text:
            self._forecast_text = text
            self.forecastTextChanged.emit()

    @Slot(str)
    def on_preview_failed(self, message: str) -> None:
        self._set_status(f"Preview failed: {message}")
        self._start_ready = True
        self.startEnabledChanged.emit()

    @Slot(bool)
    def on_clip_validity(self, valid: bool) -> None:
        self._clip_valid = valid
        self.startEnabledChanged.emit()

    @Slot()
    def on_media_metadata_ready(self) -> None:
        self.media.apply_metadata(self.media.last_metadata)

    @Slot(str)
    def apply_media_name(self, name: str) -> None:
        selected = self.current_input_path()
        if not name or not selected:
            return
        path = selected
        output_root = Path(self.job_form.output_text()).resolve()
        if path.parent.resolve() == output_root and path.stem.startswith("recording_"):
            renamed = path.with_name(f"{Path(name).stem}{path.suffix}")
            if renamed.exists() and renamed.resolve() != path.resolve():
                self._set_status("A recording with that name already exists.")
                return
            path.rename(renamed)
            self.select_input_path(renamed)
            self.media.name = renamed.stem
        else:
            self.output_name = Path(name).stem
        self._update_title()

    def _update_title(self, filename: str | None = None, status: str | None = None) -> None:
        if filename is None:
            selected = self.current_input_path()
            filename = selected.name if selected else None
        title = f"AfterClip - {filename} - {status or 'Ready'}" if filename else "AfterClip"
        if self._title != title:
            self._title = title
            self.titleChanged.emit()

    # -- tabs -----------------------------------------------------------------------

    @Slot(int)
    def onTabChanged(self, index: int) -> None:
        # Int index only: QML->Python slots with string arguments crash.
        names = ("media", "record", "batch", "history")
        tab = names[index] if 0 <= index < len(names) else "media"
        # Pausing playback is handled in QML (the player lives there).
        if tab == "history":
            self.history.refresh()

    # -- single job ------------------------------------------------------------------

    @Slot()
    def startJob(self) -> None:
        conditions = self._validate_start_conditions()
        if conditions is None:
            return
        cloud_provider = self._cloud_provider_in_use()
        if cloud_provider and not self._has_cloud_consent(cloud_provider):
            self._pending_consent_provider = cloud_provider
            self.cloudConsentRequested.emit(
                cloud_provider,
                self._cloud_model_in_use(cloud_provider),
                payload_summary(self.job_form.analysisEnabled, self.job_form.visionEnabled),
            )
            return
        text_provider, vision_provider = self._resolve_providers()
        if text_provider is False or vision_provider is False:
            return
        request = self._build_request(text_provider, vision_provider, conditions)
        LOGGER.info(
            "Job start | model=%s extract_frames=%s frame_modes=%s analyze_text=%s "
            "analyze_vision=%s embed_frames=%s speaker_vtt=%r clip=%s->%s",
            request.model,
            request.extract_frames,
            request.frame_modes,
            request.analyze_text,
            request.analyze_vision,
            request.embed_frames,
            request.speaker_vtt_path,
            request.clip_start,
            request.clip_end,
        )
        self.thread = QThread(self)
        resume_dir = self._resolve_resume_dir(conditions[0])
        self.worker = self._make_worker(text_provider, vision_provider, request, resume_dir)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.on_progress)
        self.worker.succeeded.connect(self.on_success)
        self.worker.failed.connect(self.on_failure)
        self.worker.cancelled.connect(self.on_cancelled)
        self.worker.succeeded.connect(self.thread.quit)
        self.worker.failed.connect(lambda _message: self.thread.quit())
        self.worker.cancelled.connect(self.thread.quit)
        self.thread.finished.connect(self.on_job_finished)
        self.startEnabledChanged.emit()
        self._cancel_enabled = True
        self.cancelEnabledChanged.emit()
        self.batch.set_external_job_running(True)
        self._progress_value = 0
        self.progressValueChanged.emit()
        self._set_status("Starting...")
        self._set_output_folder("")
        self._job_running = True
        self.jobRunningChanged.emit()
        self.thread.start()

    @Slot()
    def grantCloudConsentAndStart(self) -> None:
        """QML consent dialog accepted: persist consent and retry the start."""
        provider = self._pending_consent_provider
        if not provider:
            return
        self._pending_consent_provider = None
        if self.settings is not None:
            self.settings.grant_cloud_consent(provider)
        self.startJob()

    def _cloud_provider_in_use(self) -> str | None:
        """Cloud provider selected for this job, or None when fully local."""
        form = self.job_form
        if not (form.analysisEnabled or form.visionEnabled):
            return None
        for enabled, selection in (
            (form.analysisEnabled, form.selected_ai_model()),
            (form.visionEnabled, form.selected_vision_model()),
        ):
            if enabled and selection and is_cloud(selection[0]):
                return selection[0]
        if form.is_gemini_selected():
            return "gemini"
        return None

    def _cloud_model_in_use(self, provider: str) -> str:
        form = self.job_form
        for enabled, selection in (
            (form.analysisEnabled, form.selected_ai_model()),
            (form.visionEnabled, form.selected_vision_model()),
        ):
            if enabled and selection and selection[0] == provider:
                return selection[1]
        return ""

    def _has_cloud_consent(self, provider: str) -> bool:
        return self.settings is not None and self.settings.has_cloud_consent(provider)

    def _resolve_resume_dir(self, input_path: Path) -> Path | None:
        """Job folder to reuse when "reuse existing transcription" is enabled.

        Matched by the exact input path recorded in each ``job_state.json``
        under the output directory, so another file's transcript is never used.
        """
        if not self.job_form.reuseTranscription:
            return None
        output_dir = Path(self.job_form.output_text())
        resume_dir = find_reusable_job_dir(output_dir, input_path)
        if resume_dir is None:
            LOGGER.info("Reuse requested but no cached transcription for %s", input_path)
            self.alert.emit(
                "Transcription cache not found",
                "No previous transcription was found for the selected file in the output "
                "directory. The full job (including Whisper) will run.",
            )
            return None
        LOGGER.info("Reusing cached transcription from %s", resume_dir)
        return resume_dir

    def _make_worker(
        self,
        text_provider,
        vision_provider,
        request: TranscriptionRequest,
        resume_dir: Path | None = None,
    ) -> TranscriptionWorker:
        from app.application.service import TranscriptionService

        config = self._sanitizer_config()
        return TranscriptionWorker(
            TranscriptionService(
                WhisperCliProvider(condition_on_previous_text=not config.enabled),
                FfmpegMediaTool(),
                text_provider,
                vision_provider,
                sanitizer_config=config,
            ),
            request,
            resume_dir=resume_dir,
        )

    def _sanitizer_config(self) -> SanitizerConfig:
        """Filter config: settings thresholds, enabled by the per-job toggle."""
        base = self.settings.sanitizer_config() if self.settings is not None else SanitizerConfig()
        return replace(base, enabled=base.enabled and self.job_form.transcriptFilter)

    def _validate_start_conditions(self):
        """Shared preflight checks; returns (input_path, output_dir, clip_start, clip_end) or None."""  # noqa: E501
        input_path = self.current_input_path()
        output_dir = Path(self.job_form.output_text())
        if not input_path or not input_path.is_file() or not self.job_form.output_text():
            self.alert.emit(
                "Invalid input", "Select an existing media file and an output directory."
            )
            return None
        if (output_dir / "job_state.json").is_file():
            # The output directory is itself a job folder; reuse/resume scans
            # for job folders *under* the output dir, so nesting a job inside an
            # older one is always wrong. Use the parent instead.
            corrected = output_dir.parent
            LOGGER.info("Output directory is a job folder; using parent %s", corrected)
            self.job_form.outputDir = str(corrected)
            output_dir = corrected
            self.alert.emit(
                "Output directory corrected",
                "The selected output directory is an existing job folder. AfterClip "
                f"will use its parent instead:\n\n{corrected}\n\n"
                "Choose the folder that contains job folders so reuse/resume can "
                "find them.",
            )
        problem = check_output_dir(output_dir)
        if problem:
            self.alert.emit("Output directory problem", problem)
            return None
        status = check_environment()
        if not status.whisper:
            self.alert.emit(
                "Whisper is missing", "Install openai-whisper and ensure whisper.exe is available."
            )
            return None
        if input_path.suffix.lower() != ".wav" and not status.ffmpeg:
            self.alert.emit("FFmpeg is missing", "Install FFmpeg and add it to PATH.")
            return None
        if not self.media.clip_is_valid():
            self.alert.emit("Invalid clip range", self.media.clip_warning_text())
            return None
        clip_start, clip_end = self.media.clip_seconds()
        return input_path, output_dir, clip_start, clip_end

    def _provider_prompts(self):
        """Resolved prompt set for this job, or None to use built-in defaults."""
        if self.prompt_store is None:
            return None
        try:
            return self.prompt_store.load()
        except Exception as error:  # a broken prompt file must not block a job
            LOGGER.warning("Could not load prompts; using defaults: %s", error)
            return None

    def _resolve_providers(self):
        """Resolve (text_provider, vision_provider); False means the user aborted."""
        text_provider = None
        vision_provider = None
        prompts = self._provider_prompts()
        form = self.job_form
        if form.analysisEnabled:
            selection = form.lookup_ai_model()
            if selection is None:
                self.alert.emit(
                    "AI text model unavailable",
                    f"The selected text model '{form.analysisModelText}' is not available for any "
                    "configured provider. Pick a model from the list, or disable AI text analysis.",
                )
                return False, False
            provider_name, model = selection
            if not self._cloud_key_ready(provider_name, "AI analysis"):
                return False, False
            text_provider = self._build_text_provider(provider_name, model, prompts)
        if form.visionEnabled:
            selection = form.lookup_vision_model()
            if selection is None:
                self.alert.emit(
                    "AI vision model unavailable",
                    f"The selected vision model '{form.visionModelText}' is not available for any "
                    "configured provider. Pick a model from the list, or disable "
                    "AI vision analysis.",
                )
                return False, False
            provider_name, model = selection
            if not self._cloud_key_ready(provider_name, "AI vision"):
                return text_provider, False
            vision_provider = self._build_vision_provider(provider_name, model, prompts)
        return text_provider, vision_provider

    def _cloud_key_ready(self, provider_name: str, label: str) -> bool:
        """Cloud providers need a stored key; clear error and no request otherwise (T16/T20)."""
        spec = get_provider(provider_name)
        if spec is None or not spec.is_cloud:
            return True
        if KeyringSecretStore().get(spec.key_name):
            return True
        self.alert.emit(
            f"{spec.label} key missing",
            f"Store a {spec.label} API key in Settings (Credential Manager) for cloud {label}.",
        )
        return False

    def _build_text_provider(self, provider_name: str, model: str, prompts):
        spec = get_provider(provider_name)
        if spec is None:
            return None
        if spec.kind == KIND_GEMINI:
            return GeminiTextProvider(model, prompts=prompts)
        if spec.kind == KIND_OPENAI_COMPAT:
            return OpenAICompatTextProvider(
                model,
                prompts=prompts,
                base_url=spec.base_url,
                provider=spec.id,
                key_getter=lambda: KeyringSecretStore().get(spec.key_name),
            )
        if check_ollama_service():
            return OllamaTextProvider(model, prompts=prompts)
        self.alert.emit(
            "Ollama unavailable",
            "Ollama is not reachable. The job will run without AI analysis.",
        )
        return None

    def _build_vision_provider(self, provider_name: str, model: str, prompts):
        spec = get_provider(provider_name)
        if spec is None:
            return None
        if spec.kind == KIND_GEMINI:
            return GeminiVisionProvider(model, prompts=prompts)
        if spec.kind == KIND_OPENAI_COMPAT:
            return OpenAICompatVisionProvider(
                model,
                prompts=prompts,
                base_url=spec.base_url,
                provider=spec.id,
                key_getter=lambda: KeyringSecretStore().get(spec.key_name),
            )
        if check_ollama_service():
            return OllamaVisionProvider(model, prompts=prompts)
        self.alert.emit(
            "Ollama unavailable",
            "Ollama is not reachable. The job will run without vision analysis.",
        )
        return None

    def _build_request(self, text_provider, vision_provider, conditions) -> TranscriptionRequest:
        input_path, output_dir, clip_start, clip_end = conditions
        form = self.job_form
        frame_modes = form.selected_frame_modes()
        analysis_model = form.selected_ai_model()
        vision_model = form.selected_vision_model()
        topic_method, topic_min, topic_max = resolve_topics()
        return TranscriptionRequest(
            input_path,
            output_dir,
            form.whisperModel,
            form.language,
            form.task.strip(),
            clip_start,
            clip_end,
            bool(frame_modes),
            form.frameInterval,
            tuple(self.media.highlight_times),
            self.output_name,
            frame_modes[0] if frame_modes else "interval",
            form.sceneSensitivity,
            frame_modes,
            form.speaker_vtt_from_support(),
            text_provider is not None,
            analysis_model[1] if analysis_model else "",
            vision_provider is not None,
            vision_model[1] if vision_model else "",
            form.embedFrames,
            form.selected_frame_resolution(),
            form.segment_override(),
            form.reportLanguage,
            form.support_files(),
            topic_method,
            topic_min,
            topic_max,
        )

    @Slot()
    def cancelJob(self) -> None:
        if self.worker:
            self.worker.cancel()
            self._set_status("Cancelling...")

    # -- worker callbacks -------------------------------------------------------------

    @Slot(object)
    def on_progress(self, event: ProgressEvent) -> None:
        self._set_status(event.message)
        if not self._input_basename:
            selected = self.current_input_path()
            self._input_basename = selected.name if selected else None
        progress = f" {event.percent}%" if event.percent is not None else ""
        self._update_title(self._input_basename, f"{event.message.lower()}{progress}")
        if event.percent is not None:
            self._progress_value = event.percent
            self.progressValueChanged.emit()

    @Slot(object)
    def on_success(self, result) -> None:
        self._set_status(f"Completed: {len(result.transcript_files)} transcript file(s)")
        self._update_title(status="completed")
        self._progress_value = 100
        self.progressValueChanged.emit()
        output_dir = Path(result.output_dir)
        # The service reports the Transcripts folder; the job folder holding
        # every output (reports, frames, transcripts) is its parent.
        folder = output_dir.parent if output_dir.name == "Transcripts" else output_dir
        self._set_output_folder(str(folder))

    @Slot()
    def openOutputFolder(self) -> None:
        if self._output_folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._output_folder))

    @Slot(str)
    def on_failure(self, message: str) -> None:
        self._set_status("Failed")
        self._update_title(status="failed")
        self.alert.emit("Processing error", message)

    @Slot()
    def on_cancelled(self) -> None:
        self._set_status("Cancelled")

    @Slot()
    def on_job_finished(self) -> None:
        self.worker = None
        if self.thread:
            self.thread.deleteLater()
            self.thread = None
        self.startEnabledChanged.emit()
        self._cancel_enabled = False
        self.cancelEnabledChanged.emit()
        self._job_running = False
        self.jobRunningChanged.emit()
        self.batch.set_external_job_running(False)
        self.history.refresh()
        self.refreshForecast()

    # -- batch exclusivity -------------------------------------------------------------

    @Slot(bool)
    def on_batch_running(self, running: bool) -> None:
        self._batch_running = running
        self.startEnabledChanged.emit()
        self.batch.set_external_job_running(self.worker is not None)

    # -- settings ----------------------------------------------------------------------

    @Slot()
    def onSettingsSaved(self) -> None:
        self._set_status("Settings saved")
        self.refresh_model_catalog()

    @Slot()
    def on_analysis_toggled(self) -> None:
        if self.job_form.analysisEnabled and not check_ollama_service():
            self.env.refresh()
            return
        self.job_form.refresh_provider_state()

    @Slot()
    def on_ollama_availability(self) -> None:
        self.job_form.set_ollama_enabled(self.env.ollamaAvailable)
        self.refresh_model_catalog()

    @Slot()
    def refresh_model_catalog(self) -> None:
        key_store = KeyringSecretStore()
        cloud_keys = {
            provider_id: key_store.get(get_provider(provider_id).key_name)
            for provider_id in cloud_provider_ids()
        }
        sections = collect_catalog(self.env.ollamaAvailable, cloud_keys)
        self.job_form.populate_models(sections)

    # -- helpers ---------------------------------------------------------------------

    def _set_status(self, text: str) -> None:
        if self._status_text != text:
            self._status_text = text
            self.statusTextChanged.emit()
