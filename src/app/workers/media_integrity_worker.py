import logging
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from app.application.media_integrity import check_media_durations

LOGGER = logging.getLogger(__name__)


class MediaIntegrityWorker(QObject):
    """Measure media/audio/VTT lengths off the UI thread before a job starts."""

    finished = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        input_path: Path,
        video_seconds: float | None,
        clip_start: float | None,
        clip_end: float | None,
        vtt_path: str,
    ):
        super().__init__()
        self.input_path = Path(input_path)
        self.video_seconds = video_seconds
        self.clip_start = clip_start
        self.clip_end = clip_end
        self.vtt_path = vtt_path

    @Slot()
    def run(self) -> None:
        try:
            report = check_media_durations(
                self.input_path,
                video_seconds=self.video_seconds,
                clip_start=self.clip_start,
                clip_end=self.clip_end,
                vtt_path=self.vtt_path,
            )
            self.finished.emit(report)
        except Exception as error:
            LOGGER.exception("Media duration check failed for %s", self.input_path)
            self.failed.emit(str(error))
