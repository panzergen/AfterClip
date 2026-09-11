import logging
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from app.application.cancellation import CancellationToken
from app.application.service import JobCancelled, TranscriptionService
from app.domain.models import TranscriptionRequest

LOGGER = logging.getLogger(__name__)


class TranscriptionWorker(QObject):
    progress = Signal(object)
    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        service: TranscriptionService,
        request: TranscriptionRequest,
        resume_dir: Path | None = None,
    ):
        super().__init__()
        self.service = service
        self.request = request
        self.resume_dir = resume_dir
        self.token = CancellationToken()

    @Slot()
    def run(self):
        try:
            result = self.service.run(
                self.request, self.progress.emit, self.token, resume_dir=self.resume_dir
            )
            self.succeeded.emit(result)
        except JobCancelled:
            LOGGER.info("Transcription job cancelled: %s", self.request.input_path)
            self.cancelled.emit()
        except Exception as error:
            LOGGER.exception("Transcription job failed: %s", self.request.input_path)
            self.failed.emit(str(error))

    def cancel(self):
        self.token.cancel()
