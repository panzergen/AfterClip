from pathlib import Path

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QModelIndex,
    QObject,
    Qt,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QDesktopServices

from app.application.history import JobHistoryEntry, read_log_tail, scan_job_history


class HistoryJobsModel(QAbstractListModel):
    """Roles: name, status."""

    NameRole = Qt.UserRole + 1
    StatusRole = Qt.UserRole + 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: list[JobHistoryEntry] = []

    _empty_index = QModelIndex()

    def rowCount(self, parent=_empty_index):
        return 0 if parent.isValid() else len(self._entries)

    def data(self, index, role=Qt.DisplayRole):
        if not 0 <= index.row() < len(self._entries):
            return None
        entry = self._entries[index.row()]
        if role == self.NameRole:
            return entry.name
        if role == self.StatusRole:
            return entry.status
        return None

    def roleNames(self):
        return {self.NameRole: b"name", self.StatusRole: b"status"}

    def replace_entries(self, entries: list[JobHistoryEntry]) -> None:
        self.beginResetModel()
        self._entries = entries
        self.endResetModel()

    def entry_at(self, row: int) -> JobHistoryEntry | None:
        return self._entries[row] if 0 <= row < len(self._entries) else None


class HistoryController(QObject):
    """Past jobs (from job_state.json files) with their reports; app log tail below."""

    def __init__(self, output_dir: Path, log_path: Path, parent=None):
        super().__init__(parent)
        self.output_dir = output_dir
        self.log_path = log_path
        self.jobs_model = HistoryJobsModel(self)
        self._details_text = ""
        self._log_text = ""
        self._selected_row = -1

    def _get_model(self) -> HistoryJobsModel:
        return self.jobs_model

    def _get_details_text(self) -> str:
        return self._details_text

    def _get_log_text(self) -> str:
        return self._log_text

    detailsChanged = Signal()
    logChanged = Signal()

    model = Property(QObject, _get_model, constant=True)
    detailsText = Property(str, _get_details_text, notify=detailsChanged)
    logText = Property(str, _get_log_text, notify=logChanged)

    @Slot()
    def refresh(self) -> None:
        entries = scan_job_history(self.output_dir)
        self.jobs_model.replace_entries(entries)
        self._log_text = read_log_tail(self.log_path)
        self.logChanged.emit()
        self.selectRow(0 if entries else -1)

    @Slot(int)
    def selectRow(self, row: int) -> None:
        self._selected_row = row
        entry = self.jobs_model.entry_at(row)
        self._details_text = self._entry_details(entry) if entry is not None else ""
        self.detailsChanged.emit()

    def _selected_entry(self) -> JobHistoryEntry | None:
        return self.jobs_model.entry_at(self._selected_row)

    def _entry_details(self, entry: JobHistoryEntry) -> str:
        report = entry.path / "Summary_Report.md"
        state = entry.path / "job_state.json"
        sections = [
            f"Job: {entry.name}",
            f"Input: {entry.input_path}",
            f"Status: {entry.status}",
            "",
        ]
        for path in (report, state):
            if path.is_file():
                sections.append(f"--- {path.name} ---")
                sections.append(path.read_text(encoding="utf-8", errors="ignore"))
        return "\n".join(sections)

    @Slot()
    def openSelectedFolder(self) -> None:
        entry = self._selected_entry()
        if entry is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(entry.path)))
