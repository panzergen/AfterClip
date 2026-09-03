import logging

from PySide6.QtCore import QObject, Signal, Slot

from app.application.service import JobCancelled, TranscriptionService
from app.domain.models import ProgressEvent, TranscriptionRequest

LOGGER = logging.getLogger(__name__)


class CancellationToken:
    def __init__(self):
        self.cancelled = False

    def is_cancelled(self) -> bool:
        return self.cancelled


class TranscriptionWorker(QObject):
    progress = Signal(object)
    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, service: TranscriptionService, request: TranscriptionRequest):
        super().__init__()
        self.service = service
        self.request = request
        self.token = CancellationToken()

    @Slot()
    def run(self):
        try:
            result = self.service.run(self.request, self.progress.emit, self.token)
            self.succeeded.emit(result)
        except JobCancelled:
            LOGGER.info("Transcription job cancelled: %s", self.request.input_path)
            self.cancelled.emit()
        except Exception as error:
            LOGGER.exception("Transcription job failed: %s", self.request.input_path)
            self.failed.emit(str(error))

    def cancel(self):
        self.token.cancelled = True
