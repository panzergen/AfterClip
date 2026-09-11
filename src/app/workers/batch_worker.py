import logging

from PySide6.QtCore import QObject, Signal, Slot

from app.application.batch import BatchJob, BatchStore, run_batch
from app.application.cancellation import CancellationToken
from app.application.providers import build_text_provider, build_vision_provider
from app.application.service import TranscriptionService
from app.infrastructure.process import FfmpegMediaTool, WhisperCliProvider

LOGGER = logging.getLogger(__name__)


class BatchWorker(QObject):
    """Runs the persisted queue sequentially on a worker thread."""

    progress = Signal(str)
    finished = Signal()

    def __init__(self, store: BatchStore):
        super().__init__()
        self.store = store
        self.token = CancellationToken()

    @Slot()
    def run(self):
        jobs = self.store.load()
        run_batch(jobs, self.store, self._run_job, self.progress.emit, self.token)
        self.finished.emit()

    def _run_job(self, job: BatchJob, on_event, token) -> None:
        # A missing Gemini key surfaces as a per-job failure with a clear
        # error; the batch continues with the remaining jobs.
        service = TranscriptionService(
            WhisperCliProvider(),
            FfmpegMediaTool(),
            build_text_provider(job.text_spec()),
            build_vision_provider(job.vision_spec()),
        )
        service.run(job.to_request(), lambda event: on_event(event.message), token)

    def cancel(self):
        self.token.cancel()
