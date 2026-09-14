from PySide6.QtCore import Property, QObject, Signal, Slot

import app.app_paths as app_paths
from app.infrastructure.diagnostics import check_environment, detect_gpu, disk_space
from app.infrastructure.hardware import detect_memory_profile, recommend_frame_resolution
from app.infrastructure.ollama import check_ollama_service


class EnvironmentController(QObject):
    """Environment checks behind the status LED; green only when all pass."""

    environmentChanged = Signal()
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

    ok = Property(bool, _get_ok, notify=environmentChanged)
    checksText = Property(str, _get_checks_text, notify=environmentChanged)
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
        lines = [f"{name}: {'OK' if ok else fallback}" for name, ok, fallback in checks]
        gpu = detect_gpu()
        lines.append(f"GPU: {gpu.name} ({gpu.memory_mb} MB)" if gpu else "GPU: not detected")
        profile = detect_memory_profile(
            gpu.name if gpu else None, gpu.memory_mb if gpu else None
        )
        memory_kind = "unified" if profile.unified else "system"
        lines.append(
            f"Memory: {profile.total_ram_gb} GB {memory_kind}, "
            f"frames {recommend_frame_resolution(profile)}"
        )
        space = disk_space(app_paths.project_dir())
        if space is not None:
            lines.append(f"Disk free: {space.free_gb} GB")
        self._checks_text = "\n".join(lines)
        self._ok = all(ok for _, ok, _ in checks)
        self.environmentChanged.emit()
        self.ollamaAvailabilityChanged.emit(self._ollama_available)
