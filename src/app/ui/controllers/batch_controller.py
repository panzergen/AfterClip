from pathlib import Path

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QModelIndex,
    QObject,
    Qt,
    QThread,
    QUrl,
    Signal,
    Slot,
)

from app.application.batch import BatchJob, BatchStore, new_batch_job
from app.workers.batch_worker import BatchWorker

STATUS_ORDER = {"pending": 0, "running": 1, "completed": 2, "failed": 3, "cancelled": 4}


def to_local_path(value) -> str:
    text = str(value)
    return QUrl(text).toLocalFile() if text.startswith("file:") else text


class BatchJobsModel(QAbstractListModel):
    """Roles: name, status, error."""

    NameRole = Qt.UserRole + 1
    StatusRole = Qt.UserRole + 2
    ErrorRole = Qt.UserRole + 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self._jobs: list[BatchJob] = []

    _empty_index = QModelIndex()

    def rowCount(self, parent=_empty_index):
        return 0 if parent.isValid() else len(self._jobs)

    def data(self, index, role=Qt.DisplayRole):
        if not 0 <= index.row() < len(self._jobs):
            return None
        job = self._jobs[index.row()]
        if role == self.NameRole:
            return job.display_name
        if role == self.StatusRole:
            return job.status
        if role == self.ErrorRole:
            return job.error
        return None

    def roleNames(self):
        return {self.NameRole: b"name", self.StatusRole: b"status", self.ErrorRole: b"error"}

    def replace_jobs(self, jobs: list[BatchJob]) -> None:
        self.beginResetModel()
        self._jobs = jobs
        self.endResetModel()

    def job_id(self, row: int) -> str | None:
        return self._jobs[row].id if 0 <= row < len(self._jobs) else None


class BatchController(QObject):
    """Queue of media files processed sequentially (T08b) with crash-safe resume (T26b)."""

    batchRunningChanged = Signal(bool)

    def __init__(self, store: BatchStore, parent=None):
        super().__init__(parent)
        self.store = store
        self._thread = None
        self._worker = None
        self._external_job_running = False
        self.enqueue_settings_provider = lambda: {}
        self.jobs_model = BatchJobsModel(self)
        self._status_text = "Ready"
        self._running = False
        self._pending_count = 0
        self.refresh()

    def _get_model(self) -> BatchJobsModel:
        return self.jobs_model

    def _get_status_text(self) -> str:
        return self._status_text

    def _get_running(self) -> bool:
        return self._running

    def _get_start_enabled(self) -> bool:
        return not self._running and not self._external_job_running and self._pending_count > 0

    def _get_cancel_enabled(self) -> bool:
        return self._running

    def _get_remove_enabled(self) -> bool:
        return not self._running

    statusTextChanged = Signal()
    runningChanged = Signal()
    stateChanged = Signal()

    model = Property(QObject, _get_model, constant=True)
    statusText = Property(str, _get_status_text, notify=statusTextChanged)
    running = Property(bool, _get_running, notify=runningChanged)
    startEnabled = Property(bool, _get_start_enabled, notify=stateChanged)
    cancelEnabled = Property(bool, _get_cancel_enabled, notify=stateChanged)
    removeEnabled = Property(bool, _get_remove_enabled, notify=stateChanged)

    # -- wiring -------------------------------------------------------------

    def set_enqueue_settings_provider(self, provider) -> None:
        self.enqueue_settings_provider = provider

    @Slot(bool)
    def set_external_job_running(self, running: bool) -> None:
        self._external_job_running = running
        self.stateChanged.emit()

    # -- queue management -----------------------------------------------------

    def _get_files_to_add(self) -> list:
        return []

    def _set_files_to_add(self, paths) -> None:
        """QVariant list property: QML list args to slots crash here."""
        self.add_files(list(paths or []))

    def _get_rows_to_remove(self) -> list:
        return []

    def _set_rows_to_remove(self, rows) -> None:
        self.remove_rows(list(rows or []))

    filesToAdd = Property("QVariantList", _get_files_to_add, _set_files_to_add)
    rowsToRemove = Property("QVariantList", _get_rows_to_remove, _set_rows_to_remove)

    @Slot("QVariantList", "QVariant")
    def enqueue_from_form(self, input_paths: list, settings: dict) -> None:
        jobs = self.store.load()
        for path in input_paths:
            jobs.append(
                new_batch_job(
                    Path(to_local_path(path)),
                    Path(settings.get("output_dir", "")),
                    **{k: v for k, v in settings.items() if k != "output_dir"},
                )
            )
        self.store.save(jobs)
        self.refresh()

    def add_files(self, paths: list) -> None:
        if paths:
            self.enqueue_from_form(
                [to_local_path(path) for path in paths], self.enqueue_settings_provider()
            )

    def remove_rows(self, rows: list) -> None:
        selected_ids = {self.jobs_model.job_id(int(row)) for row in rows}
        jobs = [
            job
            for job in self.store.load()
            if job.id not in selected_ids or job.status == "running"
        ]
        self.store.save(jobs)
        self.refresh()

    @Slot()
    def retryFailed(self) -> None:
        jobs = self.store.load()
        for job in jobs:
            if job.status in ("failed", "cancelled"):
                job.status = "pending"
                job.error = ""
        self.store.save(jobs)
        self.refresh()

    # -- execution ---------------------------------------------------------

    def _refresh_pending_settings(self) -> None:
        """Apply the current job-form settings to every pending job.

        Settings are captured when a file is added, but users often configure
        the form afterwards; re-applying on Start matches that expectation.
        Completed/failed/running jobs keep their settings.
        """
        settings = self.enqueue_settings_provider() or {}
        if not settings:
            return
        jobs = self.store.load()
        for job in jobs:
            if job.status != "pending":
                continue
            for key, value in settings.items():
                if hasattr(job, key):
                    setattr(job, key, value)
        self.store.save(jobs)

    @Slot()
    def startBatch(self) -> None:
        if self._thread:
            self._set_status("Batch already running.")
            return
        self._refresh_pending_settings()
        if not any(job.status == "pending" for job in self.store.load()):
            self._set_status("No pending jobs in the queue.")
            return
        self._thread = QThread(self)
        self._worker = BatchWorker(self.store)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)
        self._running = True
        self.runningChanged.emit()
        self.stateChanged.emit()
        self._set_status("Batch running...")
        self.batchRunningChanged.emit(True)
        self._thread.start()

    @Slot()
    def cancelBatch(self) -> None:
        if self._worker:
            self._worker.cancel()
            self._set_status("Cancelling batch...")

    def _on_progress(self, message: str) -> None:
        self._set_status(message)
        self.refresh()

    def _on_finished(self) -> None:
        self.batchRunningChanged.emit(False)

    def _cleanup_thread(self) -> None:
        self._worker = None
        self._thread.deleteLater()
        self._thread = None
        self._running = False
        self.runningChanged.emit()
        self.stateChanged.emit()
        self.refresh()

    # -- display ------------------------------------------------------------

    @Slot()
    def refresh(self) -> None:
        jobs = self.store.load()
        self._pending_count = sum(job.status == "pending" for job in jobs)
        self.jobs_model.replace_jobs(jobs)
        self.stateChanged.emit()

    def _set_status(self, text: str) -> None:
        self._status_text = text
        self.statusTextChanged.emit()
