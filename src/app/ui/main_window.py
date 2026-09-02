from pathlib import Path

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QProgressBar, QComboBox, QVBoxLayout, QWidget

from app.application.service import TranscriptionService
from app.domain.models import ProgressEvent, TranscriptionRequest
from app.infrastructure.process import FfmpegMediaTool, WhisperCliProvider
from app.infrastructure.diagnostics import check_environment
from app.workers.transcription_worker import TranscriptionWorker


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
        form = QFormLayout()
        form.addRow("Input media", self._path_row(self.input_edit, self._choose_input))
        form.addRow("Output directory", self._path_row(self.output_edit, self._choose_output))
        form.addRow("Whisper model", self.model_combo)
        form.addRow("Language", self.language_edit)
        form.addRow("Requested task", self.task_edit)
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
        request = TranscriptionRequest(input_path, output_dir, self.model_combo.currentText(), self.language_edit.text(), self.task_edit.text().strip())
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
