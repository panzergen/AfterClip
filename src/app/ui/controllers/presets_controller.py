import logging

from PySide6.QtCore import Property, QObject, Signal, Slot

from app.domain.presets import Preset
from app.domain.prompts import DEFAULT_PROMPTS

LOGGER = logging.getLogger(__name__)


class PresetsController(QObject):
    """Named job presets: capture the current form, apply, and delete them."""

    changed = Signal()
    selectedIndexChanged = Signal()
    statusChanged = Signal()
    newNameChanged = Signal()

    def __init__(self, job_form, prompt_store, preset_store, parent=None):
        super().__init__(parent)
        self.job_form = job_form
        self.prompt_store = prompt_store
        self.preset_store = preset_store
        self._presets = self.preset_store.load()
        self._selected_index = 0 if self._presets else -1
        self._new_name = ""
        self._status_text = ""

    def _get_names(self) -> list:
        return [preset.name for preset in self._presets]

    def _get_has_presets(self) -> bool:
        return bool(self._presets)

    def _get_selected_index(self) -> int:
        return self._selected_index

    def _set_selected_index(self, value: int) -> None:
        self._selected_index = int(value)
        self.selectedIndexChanged.emit()

    def _get_new_name(self) -> str:
        return self._new_name

    def _set_new_name(self, value: str) -> None:
        self._new_name = str(value)
        self.newNameChanged.emit()

    def _get_status_text(self) -> str:
        return self._status_text

    names = Property("QVariantList", _get_names, notify=changed)
    hasPresets = Property(bool, _get_has_presets, notify=changed)
    selectedIndex = Property(
        int, _get_selected_index, _set_selected_index, notify=selectedIndexChanged
    )
    newName = Property(str, _get_new_name, _set_new_name, notify=newNameChanged)
    statusText = Property(str, _get_status_text, notify=statusChanged)

    def _set_status(self, text: str) -> None:
        self._status_text = text
        self.statusChanged.emit()

    def _emit_changed(self) -> None:
        if self._presets:
            self._selected_index = max(0, min(self._selected_index, len(self._presets) - 1))
        else:
            self._selected_index = -1
        self.changed.emit()
        self.selectedIndexChanged.emit()

    def _selected_preset(self) -> Preset | None:
        if 0 <= self._selected_index < len(self._presets):
            return self._presets[self._selected_index]
        return None

    def _current_prompt_overrides(self) -> dict[str, str]:
        current = self.prompt_store.load().to_dict()
        return {key: value for key, value in current.items() if value != DEFAULT_PROMPTS.get(key)}

    @Slot()
    def refresh(self) -> None:
        self._presets = self.preset_store.load()
        self._emit_changed()

    @Slot()
    def saveCurrent(self) -> None:
        """Capture the current form (and customized prompts) as a named preset."""
        name = self._new_name.strip() or f"Preset {len(self._presets) + 1}"
        preset = Preset.capture(name, self.job_form, self._current_prompt_overrides())
        updated = [entry for entry in self._presets if entry.name != name]
        updated.append(preset)
        updated.sort(key=lambda entry: entry.name.lower())
        self._presets = updated
        self.preset_store.save(self._presets)
        self._new_name = ""
        self.newNameChanged.emit()
        self._selected_index = next(
            index for index, entry in enumerate(self._presets) if entry.name == name
        )
        self._emit_changed()
        self._set_status(f"Saved preset '{name}'.")

    @Slot()
    def applySelected(self) -> None:
        preset = self._selected_preset()
        if preset is None:
            self._set_status("No preset selected.")
            return
        preset.apply_to(self.job_form)
        if preset.prompt_overrides:
            base = self.prompt_store.load()
            self.prompt_store.save(base.with_overrides(preset.prompt_overrides))
        self._set_status(f"Applied preset '{preset.name}'.")

    @Slot()
    def deleteSelected(self) -> None:
        preset = self._selected_preset()
        if preset is None:
            self._set_status("No preset selected.")
            return
        self._presets = [entry for entry in self._presets if entry.name != preset.name]
        self.preset_store.save(self._presets)
        self._emit_changed()
        self._set_status(f"Deleted preset '{preset.name}'.")
