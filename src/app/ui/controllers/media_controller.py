from pathlib import Path

from PySide6.QtCore import Property, QObject, QThread, QUrl, Signal, Slot

from app.infrastructure.preview import VideoPreviewExtractor
from app.ui.controllers.formatting import format_duration, next_playback_speed, parse_time_text
from app.workers.preview_worker import PreviewWorker


def metadata_stats_text(metadata: dict) -> str:
    parts = [
        f"{metadata.get('file_size_mb', '?')} MB",
        metadata.get("format", ""),
        f"{metadata.get('duration', '?')}s",
    ]
    for stream in metadata.get("streams", []):
        if stream.get("type") == "video" and stream.get("width"):
            parts.append(f"{stream.get('codec')} {stream.get('width')}x{stream.get('height')}")
        elif stream.get("type") == "audio" and stream.get("sample_rate"):
            parts.append(f"{stream.get('codec')} {stream.get('sample_rate')}Hz")
    return " | ".join(part for part in parts if part)


class MediaController(QObject):
    """Unified media workspace state: player, filmstrip, clip tools, metadata."""

    framesReady = Signal(tuple)
    metadataReady = Signal(dict)
    failed = Signal(str)
    clipValidityChanged = Signal(bool)
    applyRequested = Signal(str)
    sourceChanged = Signal(QUrl)

    def __init__(self, cache_root: Path, parent=None):
        super().__init__(parent)
        self.cache_root = cache_root
        self._preview_thread = None
        self._preview_worker = None
        self.frame_paths: tuple[Path, ...] = ()
        self.duration_seconds = 0.0
        self.clip_duration_seconds = 0.0
        self.last_metadata: dict = {}
        self.playback_speed = 1.0
        self.highlight_times: list[float] = []
        self._clip_mode = False
        self._clip_start_sec = 0.0
        self._clip_end_sec = 0.0
        self._clip_warning = ""
        self._aspect = 16.0 / 9.0
        self._name = ""
        self._metadata_text = ""
        self._frame_entries: list[dict] = []
        self._bookmark_active = False
        self._source_url = QUrl()
        self._source_path = ""

    # -- Qt properties -----------------------------------------------------

    def _get_speed_label(self) -> str:
        return f"x{self.playback_speed:g}"

    def _get_speed_value(self) -> float:
        return self.playback_speed

    def _get_bookmark_count_text(self) -> str:
        return f"\U0001f516{len(self.highlight_times)}" if self.highlight_times else ""

    def _get_bookmark_active(self) -> bool:
        return self._bookmark_active

    def _get_clip_mode(self) -> bool:
        return self._clip_mode

    def _set_clip_mode(self, enabled: bool) -> None:
        self._clip_mode = bool(enabled)
        self.clipModeChanged.emit()

    def _get_range_ms(self) -> int:
        return int(self.clip_duration_seconds * 1000)

    def _get_clip_start_sec(self) -> float:
        return self._clip_start_sec

    def _get_clip_end_sec(self) -> float:
        return self._clip_end_sec

    def _get_clip_warning(self) -> str:
        return self._clip_warning

    def _get_aspect(self) -> float:
        return self._aspect

    def _get_name(self) -> str:
        return self._name

    def _set_name(self, name: str) -> None:
        if self._name != name:
            self._name = name
            self.nameChanged.emit()

    def _get_metadata_text(self) -> str:
        return self._metadata_text

    def _get_frames(self) -> list:
        return self._frame_entries

    def _get_highlight_times(self) -> list:
        return list(self.highlight_times)

    def _get_source_url(self) -> QUrl:
        return self._source_url

    speedChanged = Signal()
    bookmarksChanged = Signal()
    clipModeChanged = Signal()
    clipChanged = Signal()
    aspectChanged = Signal()
    nameChanged = Signal()
    metadataTextChanged = Signal()
    framesChanged = Signal()

    speedLabel = Property(str, _get_speed_label, notify=speedChanged)
    speedValue = Property(float, _get_speed_value, notify=speedChanged)
    bookmarkCountText = Property(str, _get_bookmark_count_text, notify=bookmarksChanged)
    bookmarkActive = Property(bool, _get_bookmark_active, notify=bookmarksChanged)
    clipMode = Property(bool, _get_clip_mode, _set_clip_mode, notify=clipModeChanged)
    rangeMs = Property(int, _get_range_ms, notify=clipChanged)
    clipStartSec = Property(float, _get_clip_start_sec, notify=clipChanged)
    clipEndSec = Property(float, _get_clip_end_sec, notify=clipChanged)
    clipWarning = Property(str, _get_clip_warning, notify=clipChanged)
    aspect = Property(float, _get_aspect, notify=aspectChanged)
    name = Property(str, _get_name, _set_name, notify=nameChanged)
    metadataText = Property(str, _get_metadata_text, notify=metadataTextChanged)
    frames = Property("QVariantList", _get_frames, notify=framesChanged)
    highlightTimes = Property("QVariantList", _get_highlight_times, notify=bookmarksChanged)
    sourceUrl = Property(QUrl, _get_source_url, notify=sourceChanged)

    # -- preview / filmstrip -------------------------------------------------

    @Slot("QVariant")
    def start_preview(self, path) -> None:
        if self._preview_thread or not path:
            return
        self.frame_paths = ()
        self._frame_entries = []
        self.duration_seconds = 0.0
        self.framesChanged.emit()
        self._preview_thread = QThread(self)
        self._preview_worker = PreviewWorker(VideoPreviewExtractor(self.cache_root), Path(path))
        self._preview_worker.moveToThread(self._preview_thread)
        self._preview_thread.started.connect(self._preview_worker.run)
        self._preview_worker.succeeded.connect(self._on_preview_ready)
        self._preview_worker.failed.connect(self._on_preview_failed)
        self._preview_worker.succeeded.connect(self._preview_thread.quit)
        self._preview_worker.failed.connect(lambda _message: self._preview_thread.quit())
        self._preview_thread.finished.connect(self._preview_finished)
        self._preview_thread.start()

    def _on_preview_ready(self, payload: dict) -> None:
        metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}
        frames = payload.get("frames", ()) if isinstance(payload, dict) else payload
        self.metadataReady.emit(metadata)
        self._show_metadata(metadata)
        try:
            self.duration_seconds = float(metadata.get("duration"))
        except (TypeError, ValueError):
            self.duration_seconds = 0.0
        self.frame_paths = tuple(frames)
        self._fill_filmstrip()
        self.framesReady.emit(self.frame_paths)

    def _fill_filmstrip(self) -> None:
        self._frame_entries = []
        for index, frame in enumerate(self.frame_paths):
            timestamp = self.duration_seconds * index / max(1, len(self.frame_paths) - 1)
            self._frame_entries.append(
                {
                    "path": QUrl.fromLocalFile(str(frame)),
                    "label": format_duration(timestamp),
                    "timestamp": timestamp,
                }
            )
        self.framesChanged.emit()

    def _on_preview_failed(self, message: str) -> None:
        self.failed.emit(message)

    def _preview_finished(self) -> None:
        self._preview_worker = None
        self._preview_thread.deleteLater()
        self._preview_thread = None

    # -- source / playback ---------------------------------------------------
    #
    # Playback runs entirely on the QML MediaPlayer: the UI invokes it from
    # QML (buttons, timeline, filmstrip) and only reports state back into
    # this controller through the notify_* slots. No transport commands
    # cross the Python->QML boundary, which crashes the media backend.

    @Slot("QVariant")
    def set_source(self, path) -> None:
        # Never issue synchronous pause()/play() right after the source
        # changes: the Windows media backend deadlocks while loading.
        local = str(path)
        url = QUrl.fromLocalFile(local)
        if self._source_url != url:
            self._source_url = url
            self._source_path = local
            self.sourceChanged.emit(url)

    @Slot()
    def cycleSpeed(self) -> None:
        self.playback_speed = next_playback_speed(self.playback_speed)
        self.speedChanged.emit()

    @Slot(float)
    def toggleBookmarkAt(self, position_seconds: float) -> None:
        """Add a bookmark at the position, or remove the nearby one.

        Float argument only: QML->Python slots with str/bool/QVariant
        arguments crash in this PySide6 build.
        """
        position = float(position_seconds)
        nearby = [value for value in self.highlight_times if abs(value - position) < 0.5]
        if nearby:
            self.highlight_times = [
                value for value in self.highlight_times if abs(value - position) >= 0.5
            ]
        else:
            self.highlight_times = [*self.highlight_times, position]
        self._bookmark_active = bool(nearby) is False
        self.bookmarksChanged.emit()

    def _get_clip_start_text(self) -> str:
        return format_duration(self._clip_start_sec)

    def _set_clip_start_text(self, text: str) -> None:
        seconds = parse_time_text(text)
        if seconds >= 0:
            self._set_clip_range(seconds, self._clip_end_sec)

    def _get_clip_end_text(self) -> str:
        return format_duration(self._clip_end_sec)

    def _set_clip_end_text(self, text: str) -> None:
        seconds = parse_time_text(text)
        if seconds >= 0:
            self._set_clip_range(self._clip_start_sec, seconds)

    def _get_apply_name(self) -> str:
        return ""

    def _set_apply_name(self, name: str) -> None:
        self.applyRequested.emit(str(name).strip())

    clipStartText = Property(str, _get_clip_start_text, _set_clip_start_text, notify=clipChanged)
    clipEndText = Property(str, _get_clip_end_text, _set_clip_end_text, notify=clipChanged)
    applyName = Property(str, _get_apply_name, _set_apply_name)

    def has_source(self) -> bool:
        return bool(self._source_path)

    def highlight_count(self) -> int:
        return len(self.highlight_times)

    # -- metadata / clip range -------------------------------------------------

    @Slot("QVariant")
    def apply_metadata(self, metadata: dict) -> None:
        self.last_metadata = dict(metadata or {})
        video_stream = next(
            (
                stream
                for stream in metadata.get("streams", [])
                if stream.get("type") == "video" and stream.get("width") and stream.get("height")
            ),
            None,
        )
        new_aspect = (
            int(video_stream["width"]) / int(video_stream["height"]) if video_stream else 16.0 / 9.0
        )
        if new_aspect != self._aspect:
            self._aspect = new_aspect
            self.aspectChanged.emit()
        try:
            self.clip_duration_seconds = float(metadata.get("duration"))
            self._set_clip_range(0.0, self.clip_duration_seconds, emit_validity=False)
            self.clipChanged.emit()
        except (TypeError, ValueError):
            self.clip_duration_seconds = 0
            self._update_clip_warning()

    @Slot()
    def reset_clip_controls(self) -> None:
        self.clip_duration_seconds = 0.0
        self._clip_warning = ""
        self.clipChanged.emit()

    @Slot(float, float)
    def setClipRange(self, start: float, end: float) -> None:
        self._set_clip_range(float(start), float(end))

    @Slot(int)
    def nudgeClipStart(self, delta_seconds: int) -> None:
        self._set_clip_range(
            max(0.0, self._clip_start_sec + int(delta_seconds)), self._clip_end_sec
        )

    @Slot(int)
    def nudgeClipEnd(self, delta_seconds: int) -> None:
        self._set_clip_range(
            self._clip_start_sec, max(0.0, self._clip_end_sec + int(delta_seconds))
        )

    def clip_seconds(self) -> tuple[float, float]:
        return self._clip_start_sec, self._clip_end_sec

    def clip_is_valid(self) -> bool:
        return not self._compute_clip_warning()

    def clip_warning_text(self) -> str:
        return self._clip_warning

    def _set_clip_range(self, start: float, end: float, emit_validity: bool = True) -> None:
        self._clip_start_sec = max(0.0, start)
        self._clip_end_sec = max(self._clip_start_sec, end)
        self._update_clip_warning(emit_validity=emit_validity)
        self.clipChanged.emit()

    def _compute_clip_warning(self) -> str:
        duration = self.clip_duration_seconds
        if not duration:
            return ""
        if self._clip_start_sec > duration or self._clip_end_sec > duration:
            return "Clip times must be within the actual media duration."
        if self._clip_start_sec >= self._clip_end_sec:
            return "Clip start must be earlier than clip end."
        return ""

    def _update_clip_warning(self, emit_validity: bool = True) -> None:
        message = self._compute_clip_warning()
        valid_changed = bool(message) != bool(self._clip_warning)
        self._clip_warning = message
        self.clipChanged.emit()
        if emit_validity and valid_changed:
            self.clipValidityChanged.emit(not message)

    # -- metadata bar -------------------------------------------------------------

    def _show_metadata(self, metadata: dict) -> None:
        self._metadata_text = metadata_stats_text(metadata)
        self.metadataTextChanged.emit()

    def set_metadata_text(self, text: str) -> None:
        if self._metadata_text != text:
            self._metadata_text = text
            self.metadataTextChanged.emit()
