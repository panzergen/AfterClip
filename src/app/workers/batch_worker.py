import logging

from PySide6.QtCore import QObject, Signal, Slot

from app.application.batch import BatchJob, BatchStore, run_batch
from app.application.cancellation import CancellationToken
from app.application.providers import build_text_provider, build_vision_provider
from app.application.service import TranscriptionService
from app.application.transcript_sanitizer import SanitizerConfig
from app.application.voiceprints import DEFAULT_CLUSTER_THRESHOLD, DEFAULT_IDENTIFY_THRESHOLD
from app.infrastructure.process import FfmpegMediaTool, WhisperCliProvider

LOGGER = logging.getLogger(__name__)


class BatchWorker(QObject):
    """Runs the persisted queue sequentially on a worker thread."""

    progress = Signal(str)
    finished = Signal()

    def __init__(
        self,
        store: BatchStore,
        voiceprint_store=None,
        voiceprint_embedder=None,
        voiceprint_identify_threshold: float = DEFAULT_IDENTIFY_THRESHOLD,
        voiceprint_cluster_threshold: float = DEFAULT_CLUSTER_THRESHOLD,
    ):
        super().__init__()
        self.store = store
        self.token = CancellationToken()
        self.voiceprint_store = voiceprint_store
        self.voiceprint_embedder = voiceprint_embedder
        self.voiceprint_identify_threshold = voiceprint_identify_threshold
        self.voiceprint_cluster_threshold = voiceprint_cluster_threshold

    @Slot()
    def run(self):
        jobs = self.store.load()
        run_batch(jobs, self.store, self._run_job, self.progress.emit, self.token)
        self.finished.emit()

    def _run_job(self, job: BatchJob, on_event, token) -> None:
        # A missing Gemini key surfaces as a per-job failure with a clear
        # error; the batch continues with the remaining jobs.
        config = SanitizerConfig()
        service = TranscriptionService(
            WhisperCliProvider(condition_on_previous_text=not config.enabled),
            FfmpegMediaTool(),
            build_text_provider(job.text_spec()),
            build_vision_provider(job.vision_spec()),
            sanitizer_config=config,
            voiceprint_store=self.voiceprint_store,
            voiceprint_embedder=self.voiceprint_embedder,
            voiceprint_identify_threshold=self.voiceprint_identify_threshold,
            voiceprint_cluster_threshold=self.voiceprint_cluster_threshold,
        )
        service.run(job.to_request(), lambda event: on_event(event.message), token)

    def cancel(self):
        self.token.cancel()
