import logging
from pathlib import Path

from PySide6.QtCore import Property, QObject, QThread, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

import app.app_paths as app_paths
from app.application.service_io import find_reusable_job_dir
from app.domain.constants import VIDEO_SUFFIXES
from app.domain.models import ProgressEvent, TranscriptionRequest
from app.infrastructure.diagnostics import check_environment
from app.infrastructure.gemini import GEMINI_KEY_NAME, GeminiTextProvider, GeminiVisionProvider
from app.infrastructure.model_catalog import collect_catalog
from app.infrastructure.ollama import OllamaTextProvider, OllamaVisionProvider, check_ollama_service
from app.infrastructure.process import FfmpegMediaTool, WhisperCliProvider
from app.infrastructure.secrets import KeyringSecretStore
from app.ui.controllers.formatting import local_path
from app.workers.transcription_worker import TranscriptionWorker

LOGGER = logging.getLogger(__name__)


class SessionController(QObject):
    """App-level session state: input selection, single-job lifecycle, exclusivity."""

    alert = Signal(str, str)

    def __init__(self, media, job_form, batch, history, env, record, parent=None):
        super().__init__(parent)
        self.media = media
        self.job_form = job_form
        self.batch = batch
        self.history = history
        self.env = env
        self.record = record
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

        return TranscriptionWorker(
            TranscriptionService(
                WhisperCliProvider(), FfmpegMediaTool(), text_provider, vision_provider
            ),
            request,
            resume_dir=resume_dir,
        )

    def _validate_start_conditions(self):
        """Shared preflight checks; returns (input_path, output_dir, clip_start, clip_end) or None."""  # noqa: E501
        input_path = self.current_input_path()
        output_dir = Path(self.job_form.output_text())
        if not input_path or not input_path.is_file() or not self.job_form.output_text():
            self.alert.emit(
                "Invalid input", "Select an existing media file and an output directory."
            )
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

    def _resolve_providers(self):
        """Resolve (text_provider, vision_provider); False means the user aborted."""
        text_provider = None
        vision_provider = None
        form = self.job_form
        if form.analysisEnabled:
            selection = form.selected_ai_model()
            if selection is None:
                self.alert.emit("AI model missing", "Select a model or disable AI analysis.")
                return False, False
            analysis_provider, analysis_model = selection
            if analysis_provider == "gemini":
                if not self._gemini_key_stored():
                    self.alert.emit(
                        "Gemini key missing",
                        "Store a Gemini API key in Settings (Credential Manager) for cloud AI.",
                    )
                    return False, False
                text_provider = GeminiTextProvider(analysis_model)
            elif check_ollama_service():
                text_provider = OllamaTextProvider(analysis_model)
            else:
                self.alert.emit(
                    "Ollama unavailable",
                    "Ollama is not reachable. The job will run without AI analysis.",
                )
        if form.visionEnabled:
            vision_selection = form.selected_vision_model()
            if vision_selection is None:
                self.alert.emit(
                    "AI vision model missing", "Select a vision model or disable vision analysis."
                )
                return False, False
            vision_provider_name, vision_model = vision_selection
            if vision_provider_name == "gemini":
                if not self._gemini_key_stored():
                    self.alert.emit(
                        "Gemini key missing",
                        "Store a Gemini API key in Settings (Credential Manager) for cloud vision.",
                    )
                    return text_provider, False
                vision_provider = GeminiVisionProvider(vision_model)
            elif check_ollama_service():
                vision_provider = OllamaVisionProvider(vision_model)
            else:
                self.alert.emit(
                    "Ollama unavailable",
                    "Ollama is not reachable. The job will run without vision analysis.",
                )
        return text_provider, vision_provider

    def _build_request(self, text_provider, vision_provider, conditions) -> TranscriptionRequest:
        input_path, output_dir, clip_start, clip_end = conditions
        form = self.job_form
        frame_modes = form.selected_frame_modes()
        analysis_model = form.selected_ai_model()
        vision_model = form.selected_vision_model()
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
        )

    @Slot()
    def cancelJob(self) -> None:
        if self.worker:
            self.worker.cancel()
            self._set_status("Cancelling...")

    def _gemini_key_stored(self) -> bool:
        return bool(KeyringSecretStore().get(GEMINI_KEY_NAME))

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
        gemini_key = KeyringSecretStore().get(GEMINI_KEY_NAME)
        sections = collect_catalog(self.env.ollamaAvailable, gemini_key)
        self.job_form.populate_models(sections)

    # -- helpers ---------------------------------------------------------------------

    def _set_status(self, text: str) -> None:
        if self._status_text != text:
            self._status_text = text
            self.statusTextChanged.emit()
