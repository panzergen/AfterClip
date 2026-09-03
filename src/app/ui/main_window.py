from pathlib import Path

from PySide6.QtCore import QThread, QTime, Qt, Signal, QUrl
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QCheckBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QProgressBar, QComboBox, QSlider, QSpinBox, QStyle, QTabWidget, QTimeEdit, QToolButton, QVBoxLayout, QWidget

from app.application.service import TranscriptionService, parse_clip_time
from app.domain.models import ProgressEvent, TranscriptionRequest
from app.infrastructure.process import FfmpegMediaTool, WhisperCliProvider
from app.infrastructure.diagnostics import check_environment
from app.infrastructure.process import get_media_metadata
from app.infrastructure.preview import VideoPreviewExtractor
from app.infrastructure.recorder import AudioRecorder, list_microphone_devices, supports_system_audio
from app.workers.transcription_worker import TranscriptionWorker
from app.workers.preview_worker import PreviewWorker
from app.workers.recorder_worker import RecorderStopWorker


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


class PlaybackTimeline(QWidget):
    positionChanged = Signal(int)
    sliderMoved = Signal(int)
    clipChanged = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.maximum = 0
        self.position = 0
        self.clip_start = 0.0
        self.clip_end = 0.0
        self.clip_mode = False
        self.handle = None
        self.setMinimumHeight(28)

    def setRange(self, minimum, maximum):
        self.maximum = max(0, int(maximum))
        self.clip_end = self.maximum / 1000
        self.update()

    def setValue(self, value):
        self.position = max(0, min(int(value), self.maximum))
        self.update()

    def isSliderDown(self):
        return self.handle is not None

    def set_clip_mode(self, enabled):
        self.clip_mode = enabled
        self.update()

    def set_clip_values(self, start, end):
        self.clip_start = max(0, min(float(start), self.maximum / 1000))
        self.clip_end = max(self.clip_start, min(float(end), self.maximum / 1000))
        self.update()

    def _position(self, seconds):
        if self.maximum <= 0:
            return 10
        return 10 + int((self.width() - 20) * seconds / (self.maximum / 1000))

    def _seconds(self, x):
        return max(0, min(self.maximum / 1000, (x - 10) * (self.maximum / 1000) / max(1, self.width() - 20)))

    def paintEvent(self, _event):
        painter = QPainter(self)
        y = self.height() // 2
        painter.setPen(QPen(QColor("#c4c9d1"), 5))
        painter.drawLine(10, y, self.width() - 10, y)
        if self.clip_mode:
            painter.setPen(QPen(QColor("#2589d8"), 5))
            painter.drawLine(self._position(self.clip_start), y, self._position(self.clip_end), y)
            painter.setBrush(QColor("#087dcc"))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(self._position(self.clip_start) - 7, y - 7, 14, 14)
            painter.drawEllipse(self._position(self.clip_end) - 7, y - 7, 14, 14)
        painter.setPen(QPen(QColor("#20242b"), 2))
        painter.drawLine(self._position(self.position / 1000), y - 10, self._position(self.position / 1000), y + 10)

    def mousePressEvent(self, event):
        seconds = self._seconds(event.position().x())
        if self.clip_mode:
            start_distance = abs(event.position().x() - self._position(self.clip_start))
            end_distance = abs(event.position().x() - self._position(self.clip_end))
            if min(start_distance, end_distance) < 14:
                self.handle = "start" if start_distance <= end_distance else "end"
                self._move_clip(seconds)
                return
        self.handle = "position"
        self._move_position(seconds)

    def mouseMoveEvent(self, event):
        if self.handle == "start" or self.handle == "end":
            self._move_clip(self._seconds(event.position().x()))
        elif self.handle == "position":
            self._move_position(self._seconds(event.position().x()))

    def mouseReleaseEvent(self, _event):
        self.handle = None

    def _move_position(self, seconds):
        self.position = int(seconds * 1000)
        self.sliderMoved.emit(self.position)
        self.positionChanged.emit(self.position)
        self.update()

    def _move_clip(self, seconds):
        if self.handle == "start":
            self.clip_start = min(seconds, self.clip_end)
        else:
            self.clip_end = max(seconds, self.clip_start)
        self.clipChanged.emit(self.clip_start, self.clip_end)
        self.update()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AfterClip")
        self.resize(680, 360)
        self.thread = None
        self.worker = None
        self.preview_thread = None
        self.preview_worker = None
        self.preview_frames = ()
        self.preview_index = 0
        self.highlight_times = []
        self.recorder = AudioRecorder()
        self.recorder_thread = None
        self.recorder_worker = None
        self.playback_speed = 1.0
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
        self.input_edit.setPlaceholderText("Select or drop a media file")
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
        left = QVBoxLayout()
        left.addWidget(self._path_row(self.input_edit, self._choose_input))
        self._build_preview_panel()
        left.addWidget(self.tabs, 1)
        left.addWidget(self._build_metadata_panel())

        form = QFormLayout()
        form.addRow("Output directory", self._path_row(self.output_edit, self._choose_output))
        form.addRow("Whisper model", self.model_combo)
        form.addRow("Language", self.language_edit)
        form.addRow("Requested task", self.task_edit)
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
        right = QVBoxLayout()
        right.addLayout(form)
        right.addWidget(self.progress)
        right.addWidget(self.environment)
        right.addWidget(self.status)
        right.addLayout(buttons)
        layout = QHBoxLayout()
        layout.addLayout(left, 1)
        layout.addLayout(right, 2)
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)
        self.input_edit.currentIndexChanged.connect(self._refresh_clip_controls)
        self.input_edit.currentIndexChanged.connect(self._start_preview)
        self.input_edit.lineEdit().editingFinished.connect(self._start_preview)
        self._refresh_clip_controls()

    def _build_metadata_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 4, 0, 0)
        toggle = QToolButton()
        toggle.setText("Video metadata")
        toggle.setCheckable(True)
        toggle.setChecked(False)
        layout.addWidget(toggle)
        self.metadata_text = "Select a media file to load metadata."
        toggle.clicked.connect(self._show_metadata_popup)
        return panel

    def _show_metadata_popup(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Video metadata")
        details = QLabel(self.metadata_text)
        details.setWordWrap(True)
        layout = QVBoxLayout(dialog)
        layout.addWidget(details)
        dialog.resize(420, 280)
        dialog.show()
        self.metadata_dialog = dialog

    def _build_clip_section(self):
        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        self.clip_toggle = QToolButton()
        self.clip_toggle.setIcon(QIcon.fromTheme("edit-cut", self.style().standardIcon(QStyle.SP_DialogResetButton)))
        self.clip_toggle.setToolTip("Set clip video range")
        self.clip_toggle.setFixedSize(36, 36)
        self.clip_toggle.setCheckable(True)
        self.clip_toggle.setChecked(False)
        self.clip_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.clip_toggle.clicked.connect(self._toggle_clip_section)
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
            editor.setFixedWidth(105)
        range_row = QHBoxLayout()
        range_row.addWidget(self.clip_start_edit)
        range_row.addWidget(QLabel("-"))
        range_row.addWidget(self.clip_end_edit)
        range_row.addStretch(1)
        body.addLayout(range_row)
        self.clip_body.setVisible(False)
        layout.addWidget(self.clip_body)
        self.clip_start_edit.editingFinished.connect(self._edit_values_changed)
        self.clip_end_edit.editingFinished.connect(self._edit_values_changed)
        self.clip_start_edit.timeChanged.connect(self._edit_values_changed)
        self.clip_end_edit.timeChanged.connect(self._edit_values_changed)
        return section

    def _toggle_clip_section(self, expanded):
        self.clip_body.setVisible(expanded)
        self.clip_toggle.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.play_position_slider.set_clip_mode(expanded)

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

    def _timeline_clip_changed(self, start, end):
        self.clip_start_edit.setTime(self._seconds_to_time(start))
        self.clip_end_edit.setTime(self._seconds_to_time(end))
        self._update_clip_label()

    def _edit_values_changed(self):
        self.play_position_slider.set_clip_values(self._time_to_seconds(self.clip_start_edit), self._time_to_seconds(self.clip_end_edit))
        self._update_clip_label()

    def _update_clip_label(self):
        duration = getattr(self, "clip_duration_seconds", 0)
        if not duration:
            self.clip_warning.setVisible(False)
            return
        start = self._time_to_seconds(self.clip_start_edit)
        end = self._time_to_seconds(self.clip_end_edit)
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

    def _build_preview_panel(self):
        self.tabs = QTabWidget()
        preview_tab = QWidget()
        layout = QVBoxLayout(preview_tab)
        layout.setContentsMargins(0, 4, 0, 4)
        self.preview_status = QLabel("Select a video to preview frames")
        self.preview_image = QLabel()
        self.preview_image.setAlignment(Qt.AlignCenter)
        self.preview_image.setMinimumHeight(180)
        self.preview_image.setStyleSheet("background: #20242b; color: #d5d9df;")
        self.preview_image.setText("No video preview")
        controls = QHBoxLayout()
        self.preview_previous = QPushButton("<")
        self.preview_next = QPushButton(">")
        self.preview_counter = QLabel("00:00:00")
        play_button = QPushButton("Play video")
        self.preview_previous.clicked.connect(lambda: self._show_preview(-1))
        self.preview_next.clicked.connect(lambda: self._show_preview(1))
        play_button.clicked.connect(self._open_play_tab)
        controls.addWidget(self.preview_previous)
        controls.addWidget(self.preview_counter, alignment=Qt.AlignCenter)
        controls.addWidget(self.preview_next)
        controls.addWidget(play_button)
        layout.addWidget(self.preview_status)
        layout.addWidget(self.preview_image)
        layout.addLayout(controls)
        self.tabs.addTab(preview_tab, "Preview")

        play_tab = QWidget()
        play_layout = QVBoxLayout(play_tab)
        self.video_widget = QVideoWidget()
        self.play_toggle = QPushButton()
        self.play_toggle.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.play_toggle.setToolTip("Play or pause video")
        self.play_toggle.setFixedSize(36, 36)
        self.play_toggle.clicked.connect(self._toggle_playback)
        play_layout.addWidget(self.video_widget, 1)
        self.audio_output = QAudioOutput()
        self.media_player = QMediaPlayer()
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)
        self.play_position_slider = PlaybackTimeline()
        self.play_position_slider.clipChanged.connect(self._timeline_clip_changed)
        self.play_time = QLabel("00:00:00 / 00:00:00")
        self.play_position_slider.sliderMoved.connect(self.media_player.setPosition)
        self.media_player.positionChanged.connect(self._play_position_changed)
        self.media_player.durationChanged.connect(self._play_duration_changed)
        self.media_player.playbackStateChanged.connect(self._playback_state_changed)
        toolbar = QHBoxLayout()
        toolbar.addWidget(self.play_toggle)
        self.speed_button = QPushButton("x1")
        self.speed_button.setFixedSize(36, 36)
        self.speed_button.setToolTip("Playback speed")
        self.speed_button.clicked.connect(self._cycle_playback_speed)
        toolbar.addWidget(self.speed_button)
        self.highlight_button = QPushButton()
        self.highlight_button.setIcon(QIcon.fromTheme("bookmark-new", self.style().standardIcon(QStyle.SP_DialogSaveButton)))
        self.highlight_button.setFixedSize(36, 36)
        self.highlight_button.setCheckable(True)
        self.highlight_button.setToolTip("Mark this timestamp for later frame extraction and vision analysis")
        self.highlight_button.clicked.connect(self._toggle_highlight)
        toolbar.addWidget(self.highlight_button)
        info_row = QHBoxLayout()
        info_row.addLayout(toolbar)
        info_row.addWidget(self.play_time)
        info_row.addStretch(1)
        info_row.addWidget(self.clip_toggle)
        play_layout.addLayout(info_row)
        play_layout.addWidget(self.play_position_slider)
        play_layout.addWidget(self.clip_section)
        self.tabs.addTab(play_tab, "Play")
        self._build_record_tab()
        self.tabs.currentChanged.connect(self._tab_changed)

    def _build_record_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(QLabel("Record audio to the selected output folder"))
        self.record_mic = QCheckBox("Microphone")
        self.record_system = QCheckBox("System audio")
        if not supports_system_audio():
            self.record_system.setEnabled(False)
            self.record_system.setToolTip("Unavailable: this FFmpeg build does not support Windows WASAPI audio capture.")
        self.record_mic_device = QComboBox()
        self.record_mic_device.addItem("default")
        microphone_devices = list_microphone_devices()
        self.record_mic_device.addItems(microphone_devices)
        if microphone_devices:
            self.record_mic_device.setCurrentIndex(1)
        self.record_mic_device.setPlaceholderText("Windows microphone device name")
        layout.addWidget(self.record_mic)
        layout.addWidget(self.record_system)
        layout.addWidget(self.record_mic_device)
        buttons = QHBoxLayout()
        self.record_button = QPushButton("Record")
        self.stop_record_button = QPushButton("Stop")
        self.stop_record_button.setEnabled(False)
        self.record_button.clicked.connect(self._start_recording)
        self.stop_record_button.clicked.connect(self._stop_recording)
        buttons.addWidget(self.record_button)
        buttons.addWidget(self.stop_record_button)
        layout.addLayout(buttons)
        self.record_status = QLabel("Ready")
        layout.addWidget(self.record_status)
        self.tabs.addTab(tab, "Record")

    def _start_recording(self):
        output_dir = Path(self.output_edit.text().strip())
        if not output_dir:
            self.record_status.setText("Select an output directory first.")
            return
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"recording_{QTime.currentTime().toString('HHmmss')}.wav"
        try:
            recording_path = self.recorder.start(output_dir / filename, self.record_mic.isChecked(), self.record_system.isChecked(), self.record_mic_device.currentText().strip())
        except Exception as error:
            self.record_status.setText(f"Recording failed: {error}")
            return
        self.record_status.setText(f"Recording: {filename}")
        self.record_button.setEnabled(False)
        self.stop_record_button.setEnabled(True)
        self.tabs.setCurrentIndex(2)

    def _stop_recording(self):
        self.record_status.setText("Stopping recording...")
        self.stop_record_button.setEnabled(False)
        self.recorder_thread = QThread(self)
        self.recorder_worker = RecorderStopWorker(self.recorder)
        self.recorder_worker.moveToThread(self.recorder_thread)
        self.recorder_thread.started.connect(self.recorder_worker.run)
        self.recorder_worker.succeeded.connect(self._recording_saved)
        self.recorder_worker.failed.connect(self._recording_failed)
        self.recorder_worker.succeeded.connect(self.recorder_thread.quit)
        self.recorder_worker.failed.connect(lambda _: self.recorder_thread.quit())
        self.recorder_thread.finished.connect(self._recording_finished)
        self.recorder_thread.start()

    def _recording_saved(self, recording_path):
        self._select_input_path(recording_path)
        self.record_status.setText(f"Recording saved: {recording_path.name}")

    def _recording_failed(self, message):
        self.record_status.setText(f"Could not stop recording: {message}")

    def _recording_finished(self):
        self.record_button.setEnabled(True)
        self.stop_record_button.setEnabled(False)
        self.recorder_worker = None
        self.recorder_thread.deleteLater()
        self.recorder_thread = None

    def _open_play_tab(self):
        if self.media_player.source().isEmpty():
            return
        duration = getattr(self, "preview_duration_seconds", 0)
        timestamp = duration * self.preview_index / max(1, len(self.preview_frames) - 1)
        self.media_player.setPosition(int(timestamp * 1000))
        self.tabs.setCurrentIndex(1)
        self.media_player.play()

    def _toggle_playback(self):
        if self.media_player.playbackState() == QMediaPlayer.PlayingState:
            self.media_player.pause()
        else:
            self.media_player.play()

    def _cycle_playback_speed(self):
        speeds = (1.0, 1.2, 1.5)
        speed = speeds[(speeds.index(self.playback_speed) + 1) % len(speeds)]
        self.playback_speed = speed
        self.speed_button.setText(f"x{speed:g}")
        self.media_player.setPlaybackRate(speed)

    def _toggle_highlight(self):
        position = self.media_player.position() / 1000
        if self.highlight_button.isChecked():
            if not any(abs(value - position) < 0.5 for value in self.highlight_times):
                self.highlight_times.append(position)
            self.highlight_button.setToolTip(f"Highlighted at {self._format_duration(position)}. Click to remove.")
        else:
            self.highlight_times = [value for value in self.highlight_times if abs(value - position) >= 0.5]
            self.highlight_button.setToolTip("Mark this timestamp for later frame extraction and vision analysis")

    def _tab_changed(self, index):
        if index != 1:
            self.media_player.pause()

    def _play_position_changed(self, position):
        if not self.play_position_slider.isSliderDown():
            self.play_position_slider.setValue(position)
        self.play_time.setText(f"{self._format_duration(position / 1000)} / {self._format_duration(self.media_player.duration() / 1000)}")

    def _play_duration_changed(self, duration):
        self.play_position_slider.setRange(0, duration)
        self._play_position_changed(self.media_player.position())

    def _playback_state_changed(self, state):
        if state == QMediaPlayer.PlayingState:
            self.play_toggle.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))
        else:
            self.play_toggle.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))

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

    def _start_preview(self):
        selected_path = self.input_edit.currentData() or self.input_edit.currentText().strip()
        path = Path(selected_path) if selected_path else None
        if not path or not path.is_file():
            return
        if self.preview_thread:
            return
        self.preview_frames = ()
        self.preview_index = 0
        is_video = path.suffix.lower() in {".mp4", ".mkv", ".avi", ".mov"}
        self.tabs.setTabEnabled(0, is_video)
        self.tabs.setTabEnabled(1, is_video)
        if not is_video:
            self.preview_status.setText("Audio selected; video preview is unavailable.")
        else:
            self.media_player.setSource(QUrl.fromLocalFile(str(path)))
            self.media_player.pause()
        if is_video:
            self.preview_status.setText("Preparing 10 preview frames...")
        self.preview_counter.setText("00:00:00")
        self._set_start_enabled(False)
        self.preview_thread = QThread(self)
        cache_root = self.project_dir / ".cache" / "previews"
        self.preview_worker = PreviewWorker(VideoPreviewExtractor(cache_root), path)
        self.preview_worker.moveToThread(self.preview_thread)
        self.preview_thread.started.connect(self.preview_worker.run)
        self.preview_worker.succeeded.connect(self._preview_ready)
        self.preview_worker.failed.connect(self._preview_failed)
        self.preview_worker.succeeded.connect(self.preview_thread.quit)
        self.preview_worker.failed.connect(lambda _: self.preview_thread.quit())
        self.preview_thread.finished.connect(self._preview_finished)
        self.preview_thread.start()

    def _preview_ready(self, frames):
        metadata = frames.get("metadata", {}) if isinstance(frames, dict) else {}
        frames = frames.get("frames", ()) if isinstance(frames, dict) else frames
        self._apply_media_metadata(metadata)
        self.preview_frames = tuple(frames)
        self.preview_index = 0
        self.preview_status.setText("Preview ready. Use the arrows to browse frames." if frames else "Audio selected; video preview is unavailable.")
        if frames:
            self._show_preview(0)
        self._set_start_enabled(True)

    def _preview_failed(self, message):
        self.preview_status.setText(f"Preview failed: {message}")
        self._set_start_enabled(True)

    def _preview_finished(self):
        self.preview_worker = None
        self.preview_thread.deleteLater()
        self.preview_thread = None

    def _show_preview(self, change):
        if not self.preview_frames:
            return
        self.preview_index = (self.preview_index + change) % len(self.preview_frames)
        pixmap = QPixmap(str(self.preview_frames[self.preview_index]))
        self.preview_image.setPixmap(pixmap.scaled(self.preview_image.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        duration = getattr(self, "preview_duration_seconds", 0)
        timestamp = duration * self.preview_index / max(1, len(self.preview_frames) - 1)
        self.preview_counter.setText(self._format_duration(timestamp))

    def _set_start_enabled(self, enabled):
        if hasattr(self, "start_button") and self.worker is None:
            self.start_button.setEnabled(enabled)

    def _refresh_clip_controls(self):
        path = self.input_edit.currentData()
        if not path or not Path(path).is_file():
            self._update_clip_label()
            return
        self.preview_duration_seconds = 0
        self.clip_duration_seconds = 0
        self.clip_toggle.setText("")
        self.clip_warning.setVisible(False)
        self.metadata_text = "Loading media metadata..."

    def _apply_media_metadata(self, metadata):
        duration = metadata.get("duration")
        self.metadata_text = (
            "\n".join(f"{key.replace('_', ' ').title()}: {value}" for key, value in metadata.items() if key != "streams")
            + ("\nStreams:\n" + "\n".join(str(stream) for stream in metadata.get("streams", [])) if metadata.get("streams") else "")
        )
        try:
            self.clip_duration_seconds = float(duration)
            self.preview_duration_seconds = self.clip_duration_seconds
            self.play_position_slider.setRange(0, int(self.clip_duration_seconds * 1000))
            self.clip_start_edit.setTime(QTime(0, 0, 0))
            self.clip_end_edit.setTime(self._seconds_to_time(self.clip_duration_seconds))
            self.play_position_slider.set_clip_values(0, self.clip_duration_seconds)
            self._update_clip_label()
        except (TypeError, ValueError):
            self.clip_duration_seconds = 0
            self.preview_duration_seconds = 0
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
        self.media_player.pause()
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
        request = TranscriptionRequest(input_path, output_dir, self.model_combo.currentText(), self.language_edit.text(), self.task_edit.text().strip(), clip_start, clip_end, self.extract_frames_check.isChecked(), self.frame_interval_spin.value(), tuple(self.highlight_times))
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
