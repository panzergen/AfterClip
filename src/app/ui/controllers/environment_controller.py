from PySide6.QtCore import Property, QObject, Signal, Slot

from app.infrastructure.diagnostics import check_environment
from app.infrastructure.ollama import check_ollama_service


class EnvironmentController(QObject):
    """Environment checks behind the status LED; green only when all pass."""

    ollamaAvailabilityChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ok = False
        self._checks_text = ""
        self._ollama_available = False

    def _get_ok(self) -> bool:
        return self._ok

    def _get_checks_text(self) -> str:
        return self._checks_text

    def _get_ollama_available(self) -> bool:
        return self._ollama_available

    ok = Property(bool, _get_ok, notify=ollamaAvailabilityChanged)
    checksText = Property(str, _get_checks_text, constant=True)
    ollamaAvailable = Property(bool, _get_ollama_available, notify=ollamaAvailabilityChanged)

    @Slot()
    def refresh(self) -> None:
        status = check_environment()
        self._ollama_available = check_ollama_service(timeout=1.0)
        checks = [
            ("FFmpeg", status.ffmpeg, "MISSING"),
            ("FFprobe", status.ffprobe, "MISSING"),
            ("Whisper", status.whisper, "MISSING"),
            ("Ollama", self._ollama_available, "OFFLINE"),
        ]
        self._checks_text = "\n".join(
            f"{name}: {'OK' if ok else fallback}" for name, ok, fallback in checks
        )
        self._ok = all(ok for _, ok, _ in checks)
        self.ollamaAvailabilityChanged.emit(self._ollama_available)
