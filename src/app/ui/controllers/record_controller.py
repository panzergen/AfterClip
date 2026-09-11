from pathlib import Path

from PySide6.QtCore import Property, QObject, QThread, QTime, Signal, Slot

from app.infrastructure.recorder import (
    AudioRecorder,
    list_microphone_devices,
    supports_system_audio,
)
from app.workers.recorder_worker import RecorderStopWorker


class RecordController(QObject):
    """Microphone/system-audio recording into the selected output folder."""

    recordingStarted = Signal(str)
    recordingReady = Signal(Path)
    recordingFailed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.output_dir: Path | None = None
        self.recorder = AudioRecorder()
        self._recorder_thread = None
        self._recorder_worker = None
        self._mic_selected = True
        self._system_selected = False
        self._system_supported = supports_system_audio()
        self._status_text = "Ready"
        self._recording = False
        self._device = "default"

    def _get_mic_selected(self) -> bool:
        return self._mic_selected

    def _set_mic_selected(self, value: bool) -> None:
        self._mic_selected = bool(value)
        self.micSelectedChanged.emit()

    def _get_system_selected(self) -> bool:
        return self._system_selected

    def _set_system_selected(self, value: bool) -> None:
        self._system_selected = bool(value)
        self.systemSelectedChanged.emit()

    def _get_system_supported(self) -> bool:
        return self._system_supported

    def _get_devices(self) -> list:
        return ["default", *list_microphone_devices()]

    def _get_status_text(self) -> str:
        return self._status_text

    def _get_recording(self) -> bool:
        return self._recording

    def _get_device(self) -> str:
        return self._device

    def _set_device(self, value: str) -> None:
        self._device = str(value)
        self.deviceChanged.emit()

    micSelectedChanged = Signal()
    systemSelectedChanged = Signal()
    deviceChanged = Signal()
    statusTextChanged = Signal()
    recordingChanged = Signal()

    micSelected = Property(bool, _get_mic_selected, _set_mic_selected, notify=micSelectedChanged)
    systemSelected = Property(
        bool, _get_system_selected, _set_system_selected, notify=systemSelectedChanged
    )
    systemSupported = Property(bool, _get_system_supported, constant=True)
    devices = Property("QVariantList", _get_devices, constant=True)
    device = Property(str, _get_device, _set_device, notify=deviceChanged)
    statusText = Property(str, _get_status_text, notify=statusTextChanged)
    recording = Property(bool, _get_recording, notify=recordingChanged)

    @Slot(str)
    def set_output_dir(self, path: str) -> None:
        self.output_dir = Path(path.strip()) if path.strip() else None

    @Slot()
    def startRecording(self) -> None:
        if not self.output_dir:
            self._set_status("Select an output directory first.")
            return
        self.output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"recording_{QTime.currentTime().toString('HHmmss')}.wav"
        try:
            self.recorder.start(
                self.output_dir / filename,
                self._mic_selected,
                self._system_selected,
                self._device,
            )
        except Exception as error:
            self._set_status(f"Recording failed: {error}")
            return
        self._set_status(f"Recording: {filename}")
        self._recording = True
        self.recordingChanged.emit()
        self.recordingStarted.emit(filename)

    @Slot()
    def stopRecording(self) -> None:
        self._set_status("Stopping recording...")
        self._recording = False
        self.recordingChanged.emit()
        self._recorder_thread = QThread(self)
        self._recorder_worker = RecorderStopWorker(self.recorder)
        self._recorder_worker.moveToThread(self._recorder_thread)
        self._recorder_thread.started.connect(self._recorder_worker.run)
        self._recorder_worker.succeeded.connect(self._recording_saved)
        self._recorder_worker.failed.connect(self._recording_failed)
        self._recorder_worker.succeeded.connect(self._recorder_thread.quit)
        self._recorder_worker.failed.connect(lambda _message: self._recorder_thread.quit())
        self._recorder_thread.finished.connect(self._recording_finished)
        self._recorder_thread.start()

    def _set_status(self, text: str) -> None:
        self._status_text = text
        self.statusTextChanged.emit()

    def _recording_saved(self, recording_path: Path) -> None:
        self._set_status(f"Recording saved: {recording_path.name}")
        self.recordingReady.emit(recording_path)

    def _recording_failed(self, message: str) -> None:
        self._set_status(f"Could not stop recording: {message}")
        self.recordingFailed.emit(message)

    def _recording_finished(self) -> None:
        self._recorder_worker = None
        self._recorder_thread.deleteLater()
        self._recorder_thread = None
