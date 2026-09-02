from pathlib import Path

from PySide6.QtCore import QThread, QTime, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QCheckBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QProgressBar, QComboBox, QSpinBox, QTimeEdit, QToolButton, QVBoxLayout, QWidget

from app.application.service import TranscriptionService, parse_clip_time
from app.domain.models import ProgressEvent, TranscriptionRequest
from app.infrastructure.process import FfmpegMediaTool, WhisperCliProvider
from app.infrastructure.diagnostics import check_environment
from app.infrastructure.process import get_media_metadata
from app.workers.transcription_worker import TranscriptionWorker


class DualRangeSlider(QWidget):
    valuesChanged = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.minimum = 0.0
        self.maximum = 1.0
        self.start = 0.0
        self.end = 1.0
        self.handle = None
        self.setMinimumHeight(32)

    def set_range(self, maximum):
        self.maximum = max(1.0, float(maximum))
        self.start = min(self.start, self.maximum)
        self.end = min(max(self.end, self.start), self.maximum)
        self.update()

    def set_values(self, start, end):
        self.start = max(self.minimum, min(float(start), self.maximum))
        self.end = max(self.start, min(float(end), self.maximum))
        self.update()

    def _position(self, value):
        return 10 + int((self.width() - 20) * value / self.maximum)

    def _value(self, x):
        return max(self.minimum, min(self.maximum, (x - 10) * self.maximum / max(1, self.width() - 20)))

    def paintEvent(self, _event):
        painter = QPainter(self)
        y = self.height() // 2
        painter.setPen(QPen(QColor("#c4c9d1"), 5))
        painter.drawLine(10, y, self.width() - 10, y)
        painter.setPen(QPen(QColor("#2589d8"), 5))
        painter.drawLine(self._position(self.start), y, self._position(self.end), y)
        painter.setBrush(QColor("#087dcc"))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(self._position(self.start) - 7, y - 7, 14, 14)
        painter.drawEllipse(self._position(self.end) - 7, y - 7, 14, 14)

    def mousePressEvent(self, event):
        start_distance = abs(event.position().x() - self._position(self.start))
        end_distance = abs(event.position().x() - self._position(self.end))
        self.handle = "start" if start_distance <= end_distance else "end"
        self._move_handle(event.position().x())

    def mouseMoveEvent(self, event):
        if self.handle:
            self._move_handle(event.position().x())

    def mouseReleaseEvent(self, _event):
        self.handle = None

    def _move_handle(self, x):
        value = self._value(x)
        if self.handle == "start":
            self.start = min(value, self.end)
        else:
            self.end = max(value, self.start)
        self.valuesChanged.emit(self.start, self.end)
        self.update()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AfterClip")
        self.resize(680, 360)
        self.thread = None
        self.worker = None
        repository_dir = Path(__file__).resolve().parents[3]
        workspace_dir = repository_dir.parent
        self.project_dir = workspace_dir if (workspace_dir / "Input-Folder").exists() else repository_dir
        self.input_dir = self.project_dir / "Input-Folder"
        self.output_dir = self.project_dir / "Output-Folder"
        self._build_ui()
        self._update_environment_status()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        extensions = {".mp4", ".mkv", ".avi", ".mov", ".wav", ".mp3", ".m4a"}
        files = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        path = next((file for file in files if file.suffix.lower() in extensions), None)
        if path:
            self._select_input_path(path)
            event.acceptProposedAction()
        else:
            event.ignore()

    def _build_ui(self):
        self.input_edit = QComboBox()
        self.input_edit.setEditable(True)
        self._load_input_files()
        self.output_edit = QLineEdit(str(self.output_dir))
        self.model_combo = QComboBox()
        self.model_combo.addItems(["tiny", "base", "small", "medium", "large", "turbo"])
        self.language_edit = QLineEdit()
        self.language_edit.setPlaceholderText("Optional, e.g. tr")
        self.task_edit = QLineEdit()
        self.task_edit.setPlaceholderText("Optional task or processing request")
        self.clip_duration_seconds = 0.0
        self.clip_section = self._build_clip_section()
        self.extract_frames_check = QCheckBox("Extract screenshots at interval")
        self.frame_interval_spin = QSpinBox()
        self.frame_interval_spin.setRange(1, 3600)
        self.frame_interval_spin.setValue(10)
        form = QFormLayout()
        form.addRow("Input media", self._path_row(self.input_edit, self._choose_input))
        form.addRow("Output directory", self._path_row(self.output_edit, self._choose_output))
        form.addRow("Whisper model", self.model_combo)
        form.addRow("Language", self.language_edit)
        form.addRow("Requested task", self.task_edit)
        form.addRow("", self.clip_section)
        form.addRow("Visual context", self.extract_frames_check)
        form.addRow("Screenshot interval (seconds)", self.frame_interval_spin)
        self.status = QLabel("Ready")
        self.environment = QLabel()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.start_button = QPushButton("Start transcription")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_job)
        self.cancel_button.clicked.connect(self.cancel_job)
        buttons = QHBoxLayout()
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.cancel_button)
        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(self.progress)
        layout.addWidget(self.environment)
        layout.addWidget(self.status)
        layout.addLayout(buttons)
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)
        self.input_edit.currentIndexChanged.connect(self._refresh_clip_controls)
        self._refresh_clip_controls()

    def _build_clip_section(self):
        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        self.clip_toggle = QToolButton()
        self.clip_toggle.setCheckable(True)
        self.clip_toggle.setChecked(False)
        self.clip_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.clip_toggle.clicked.connect(self._toggle_clip_section)
        layout.addWidget(self.clip_toggle)
        self.clip_warning = QLabel()
        self.clip_warning.setStyleSheet("color: #b3261e; font-weight: bold;")
        self.clip_warning.setVisible(False)
        layout.addWidget(self.clip_warning)
        self.clip_body = QWidget()
        body = QVBoxLayout(self.clip_body)
        body.setContentsMargins(8, 2, 0, 0)
        self.clip_start_edit = QTimeEdit()
        self.clip_end_edit = QTimeEdit()
        for editor in (self.clip_start_edit, self.clip_end_edit):
            editor.setDisplayFormat("HH:mm:ss")
            editor.setKeyboardTracking(False)
        self.clip_start_slider = DualRangeSlider()
        self.clip_start_slider.valuesChanged.connect(self._slider_values_changed)
        body.addLayout(self._time_row("Start", self.clip_start_edit))
        body.addLayout(self._time_row("End", self.clip_end_edit))
        body.addWidget(self.clip_start_slider)
        self.clip_body.setVisible(False)
        layout.addWidget(self.clip_body)
        self.clip_start_edit.editingFinished.connect(self._edit_values_changed)
        self.clip_end_edit.editingFinished.connect(self._edit_values_changed)
        self.clip_start_edit.timeChanged.connect(self._edit_values_changed)
        self.clip_end_edit.timeChanged.connect(self._edit_values_changed)
        return section

    def _time_row(self, title, editor):
        row = QHBoxLayout()
        row.addWidget(QLabel(f"{title}:"))
        row.addWidget(editor)
        return row

    def _toggle_clip_section(self, expanded):
        self.clip_body.setVisible(expanded)
        self.clip_toggle.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)

    def _adjust_time(self, editor, amount):
        seconds = self._time_to_seconds(editor)
        seconds = max(0, min(self.clip_duration_seconds, seconds + amount))
        editor.setTime(self._seconds_to_time(seconds))
        self._edit_values_changed()

    def _time_to_seconds(self, editor):
        value = editor.time()
        return value.hour() * 3600 + value.minute() * 60 + value.second()

    def _seconds_to_time(self, seconds):
        seconds = int(max(0, seconds))
        return QTime(seconds // 3600, (seconds % 3600) // 60, seconds % 60)

    def _slider_values_changed(self, start, end):
        self.clip_start_edit.setTime(self._seconds_to_time(start))
        self.clip_end_edit.setTime(self._seconds_to_time(end))
        self._update_clip_label()

    def _edit_values_changed(self):
        self.clip_start_slider.set_values(self._time_to_seconds(self.clip_start_edit), self._time_to_seconds(self.clip_end_edit))
        self._update_clip_label()

    def _update_clip_label(self):
        duration = getattr(self, "clip_duration_seconds", 0)
        if not duration:
            self.clip_toggle.setText("Clip range: unknown duration (click to set range)")
            return
        start = self._time_to_seconds(self.clip_start_edit)
        end = self._time_to_seconds(self.clip_end_edit)
        is_full_clip = start == 0 and abs(end - duration) <= 1
        if is_full_clip:
            self.clip_toggle.setText(f"Total duration: {self._format_duration(duration)} (click to set range)")
        else:
            clipped = max(0, end - start)
            self.clip_toggle.setText(f"Clipped duration: {self._format_duration(clipped)} (click to set range)")
        self._validate_clip_range()

    def _validate_clip_range(self):
        duration = getattr(self, "clip_duration_seconds", 0)
        if not duration:
            self.clip_warning.setVisible(False)
            return True
        start = self._time_to_seconds(self.clip_start_edit)
        end = self._time_to_seconds(self.clip_end_edit)
        if start > duration or end > duration:
            message = "Clip times must be within the actual media duration."
        elif start >= end:
            message = "Clip start must be earlier than clip end."
        else:
            message = ""
        self.clip_warning.setText(message)
        self.clip_warning.setVisible(bool(message))
        if hasattr(self, "start_button"):
            self.start_button.setEnabled(not message and self.worker is None)
        return not message

    def _path_row(self, edit, callback):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        button = QPushButton("Browse")
        button.clicked.connect(callback)
        layout.addWidget(edit)
        layout.addWidget(button)
        return row

    def _load_input_files(self):
        self.input_dir.mkdir(parents=True, exist_ok=True)
        files = sorted(
            path for path in self.input_dir.iterdir()
            if path.is_file() and path.suffix.lower() in {".mp4", ".mkv", ".avi", ".mov", ".wav", ".mp3", ".m4a"}
        )
        for path in files:
            self.input_edit.addItem(path.name, str(path.resolve()))

    def _choose_input(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select media", str(self.input_dir), "Media (*.mp4 *.mkv *.avi *.mov *.wav *.mp3 *.m4a)")
        if path:
            self._select_input_path(Path(path))

    def _select_input_path(self, path: Path):
        path = path.resolve()
        for index in range(self.input_edit.count()):
            if self.input_edit.itemData(index) == str(path):
                self.input_edit.setCurrentIndex(index)
                return
        self.input_edit.addItem(path.name, str(path))
        self.input_edit.setCurrentIndex(self.input_edit.count() - 1)

    def _refresh_clip_controls(self):
        path = self.input_edit.currentData()
        if not path or not Path(path).is_file():
            self._update_clip_label()
            return
        duration = get_media_metadata(Path(path)).get("duration")
        try:
            self.clip_duration_seconds = float(duration)
            self.clip_start_slider.set_range(self.clip_duration_seconds)
            self.clip_start_edit.setTime(QTime(0, 0, 0))
            self.clip_end_edit.setTime(self._seconds_to_time(self.clip_duration_seconds))
            self.clip_start_slider.set_values(0, self.clip_duration_seconds)
            self._update_clip_label()
        except (TypeError, ValueError):
            self.clip_duration_seconds = 0
            self._update_clip_label()

    @staticmethod
    def _format_duration(seconds):
        total = int(seconds)
        return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"

    def _update_environment_status(self):
        status = check_environment()
        values = [
            f"FFmpeg: {'OK' if status.ffmpeg else 'MISSING'}",
            f"FFprobe: {'OK' if status.ffprobe else 'MISSING'}",
            f"Whisper: {'OK' if status.whisper else 'MISSING'}",
        ]
        self.environment.setText(" | ".join(values))
        self.environment.setStyleSheet("color: #287a36" if status.ffmpeg and status.whisper else "color: #a33a2b")

    def _choose_output(self):
        path = QFileDialog.getExistingDirectory(self, "Select output directory", str(self.output_dir))
        if path:
            self.output_edit.setText(path)

    def start_job(self):
        selected_path = self.input_edit.currentData() or self.input_edit.currentText().strip()
        input_path = Path(selected_path)
        output_dir = Path(self.output_edit.text().strip())
        if not input_path.is_file() or not self.output_edit.text().strip():
            QMessageBox.warning(self, "Invalid input", "Select an existing media file and an output directory.")
            return
        status = check_environment()
        if not status.whisper:
            QMessageBox.critical(self, "Whisper is missing", "Install openai-whisper and ensure whisper.exe is available.")
            return
        if input_path.suffix.lower() != ".wav" and not status.ffmpeg:
            QMessageBox.critical(self, "FFmpeg is missing", "Install FFmpeg and add it to PATH.")
            return
        try:
            clip_start = parse_clip_time(self.clip_start_edit.text())
            clip_end = parse_clip_time(self.clip_end_edit.text())
        except ValueError as error:
            QMessageBox.warning(self, "Invalid clip range", str(error))
            return
        if not self._validate_clip_range():
            QMessageBox.warning(self, "Invalid clip range", self.clip_warning.text())
            return
        request = TranscriptionRequest(input_path, output_dir, self.model_combo.currentText(), self.language_edit.text(), self.task_edit.text().strip(), clip_start, clip_end, self.extract_frames_check.isChecked(), self.frame_interval_spin.value())
        self.thread = QThread(self)
        self.worker = TranscriptionWorker(TranscriptionService(WhisperCliProvider(), FfmpegMediaTool()), request)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_progress)
        self.worker.succeeded.connect(self._on_success)
        self.worker.failed.connect(self._on_failure)
        self.worker.cancelled.connect(self._on_cancelled)
        self.worker.succeeded.connect(self.thread.quit)
        self.worker.failed.connect(lambda _: self.thread.quit())
        self.worker.cancelled.connect(self.thread.quit)
        self.thread.finished.connect(self._job_finished)
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress.setValue(0)
        self.status.setText("Starting...")
        self.thread.start()

    def cancel_job(self):
        if self.worker:
            self.worker.cancel()
            self.status.setText("Cancelling...")

    def _on_progress(self, event: ProgressEvent):
        self.status.setText(event.message)
        if event.percent is not None:
            self.progress.setValue(event.percent)

    def _on_success(self, result):
        self.status.setText(f"Completed: {len(result.transcript_files)} transcript file(s)")
        self.progress.setValue(100)

    def _on_failure(self, message):
        self.status.setText("Failed")
        QMessageBox.critical(self, "Processing error", message)

    def _on_cancelled(self):
        self.status.setText("Cancelled")

    def _job_finished(self):
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.worker = None
        self.thread.deleteLater()
        self.thread = None
