import logging

from PySide6.QtCore import Property, QObject, Signal, Slot

from app.application.prompt_scope import apply_preset_to_prompts, preset_badge
from app.domain.presets import Preset

LOGGER = logging.getLogger(__name__)


class PresetsController(QObject):
    """Named job presets: capture the current form, apply, and delete them.

    Phase 1: presets carry a full prompt snapshot (replace), no snapshot
    (inherit), or legacy partial overrides (legacy-partial). Unsaved prompt
    edits are never silently discarded: applying a preset while the editor is
    dirty keeps the edits as session-custom and marks the badge Custom.
    """

    changed = Signal()
    selectedIndexChanged = Signal()
    statusChanged = Signal()
    newNameChanged = Signal()
    includePromptsChanged = Signal()
    promptBadgeChanged = Signal()

    def __init__(self, job_form, prompt_store, preset_store, settings=None, parent=None):
        super().__init__(parent)
        self.job_form = job_form
        self.prompt_store = prompt_store
        self.preset_store = preset_store
        self.settings = settings
        self._presets = self.preset_store.load()
        self._selected_index = 0 if self._presets else -1
        self._new_name = ""
        self._status_text = ""
        self._include_prompts = True
        self._badge = "Default"
        self._applied_preset = ""

    def _get_names(self) -> list:
        return [preset.name for preset in self._presets]

    def _get_has_presets(self) -> bool:
        return bool(self._presets)

    def _get_selected_index(self) -> int:
        return self._selected_index

    def _set_selected_index(self, value: int) -> None:
        self._selected_index = int(value)
        self.selectedIndexChanged.emit()
        self.changed.emit()

    def _get_new_name(self) -> str:
        return self._new_name

    def _set_new_name(self, value: str) -> None:
        self._new_name = str(value)
        self.newNameChanged.emit()

    def _get_selected_name(self) -> str:
        preset = self._selected_preset()
        return preset.name if preset is not None else ""

    def _get_status_text(self) -> str:
        return self._status_text

    def _get_include_prompts(self) -> bool:
        return self._include_prompts

    def _set_include_prompts(self, value: bool) -> None:
        include = bool(value)
        if include != self._include_prompts:
            self._include_prompts = include
            self.includePromptsChanged.emit()

    def _get_prompt_badge(self) -> str:
        return self._badge

    names = Property("QVariantList", _get_names, notify=changed)
    hasPresets = Property(bool, _get_has_presets, notify=changed)
    selectedIndex = Property(
        int, _get_selected_index, _set_selected_index, notify=selectedIndexChanged
    )
    newName = Property(str, _get_new_name, _set_new_name, notify=newNameChanged)
    selectedName = Property(str, _get_selected_name, notify=changed)
    statusText = Property(str, _get_status_text, notify=statusChanged)
    includePrompts = Property(
        bool, _get_include_prompts, _set_include_prompts, notify=includePromptsChanged
    )
    promptBadge = Property(str, _get_prompt_badge, notify=promptBadgeChanged)

    def _set_status(self, text: str) -> None:
        self._status_text = text
        self.statusChanged.emit()

    def _set_badge(self, badge: str) -> None:
        if badge != self._badge:
            self._badge = badge
            self.promptBadgeChanged.emit()

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

    def _has_unsaved_prompts(self) -> bool:
        if self.settings is not None:
            try:
                return bool(self.settings.has_unsaved_prompts())
            except Exception:
                return False
        return False

    def _effective_prompt_set(self):
        if self.settings is not None:
            try:
                return self.settings.effective_prompt_set()
            except Exception:
                pass
        return self.prompt_store.load()

    def _update_badge(self, preset: Preset | None) -> str:
        badge = preset_badge(preset, self._has_unsaved_prompts())
        self._set_badge(badge)
        return badge

    @Slot()
    def refresh(self) -> None:
        self._presets = self.preset_store.load()
        self._emit_changed()

    @Slot()
    def refreshBadge(self) -> None:
        """Recompute the badge after the prompt editor changed."""
        self._update_badge(self._selected_preset())

    @Slot()
    def saveCurrent(self) -> None:
        """Capture the current form as a named preset.

        With Include prompts checked (default), store a full nine-template
        snapshot and write it to the global prompt store so the preset is
        active right away. Unchecked stores job settings only (inherit).
        """
        name = self._new_name.strip() or f"Preset {len(self._presets) + 1}"
        include = bool(self._include_prompts)
        effective = self._effective_prompt_set()
        if include:
            snapshot = dict(effective.to_dict())
            preset = Preset.capture(name, self.job_form, prompts=snapshot, include_prompts=True)
            # Saving with prompts also activates them globally.
            self.prompt_store.save(effective)
            if self.settings is not None:
                try:
                    self.settings.clear_session_prompts()
                except Exception:
                    LOGGER.debug("Could not clear session prompts after preset save")
        else:
            preset = Preset.capture(name, self.job_form, include_prompts=False)
        updated = [entry for entry in self._presets if entry.name != name]
        updated.append(preset)
        updated.sort(key=lambda entry: entry.name.lower())
        self._presets = updated
        self.preset_store.save(self._presets)
        self._new_name = ""
        self.newNameChanged.emit()
        self._applied_preset = name
        self._selected_index = next(
            index for index, entry in enumerate(self._presets) if entry.name == name
        )
        self._emit_changed()
        self._update_badge(preset)
        if include:
            self._set_status(f"Saved preset '{name}' with prompts (Applied).")
        else:
            self._set_status(f"Saved preset '{name}' without prompts (Inherited).")

    @Slot()
    def applySelected(self) -> None:
        preset = self._selected_preset()
        if preset is None:
            self._set_status("No preset selected.")
            return
        preset.apply_to(self.job_form)
        self._applied_preset = preset.name
        has_unsaved = self._has_unsaved_prompts()
        if preset.prompt_mode == "inherit":
            self._update_badge(preset)
            if has_unsaved:
                self._set_status(
                    f"Applied job settings from '{preset.name}'; kept your unsaved "
                    "prompt edits (Custom)."
                )
            else:
                self._set_status(f"Applied preset '{preset.name}' (Inherited; prompts unchanged).")
            return
        if preset.prompt_mode == "legacy-partial":
            if has_unsaved:
                self._update_badge(preset)
                self._set_status(
                    f"Applied job settings from '{preset.name}'; kept your unsaved "
                    "prompt edits (Custom). Use 'Use preset prompts' to apply the "
                    "legacy prompts."
                )
                return
            base = self.prompt_store.load()
            self.prompt_store.save(apply_preset_to_prompts(preset, base))
            if self.settings is not None:
                try:
                    self.settings.clear_session_prompts()
                except Exception:
                    pass
            self._update_badge(preset)
            self._set_status(
                f"Applied preset '{preset.name}' (Legacy prompts merged). "
                "Re-save it to convert to a full snapshot."
            )
            return
        # Replace mode.
        if has_unsaved:
            self._update_badge(preset)
            self._set_status(
                f"Applied job settings from '{preset.name}'; kept your unsaved "
                "prompt edits (Custom). Use 'Use preset prompts' to discard them."
            )
            return
        from app.domain.prompts import prompt_set_from_snapshot

        self.prompt_store.save(prompt_set_from_snapshot(preset.prompts))
        if self.settings is not None:
            try:
                self.settings.clear_session_prompts()
            except Exception:
                pass
        self._update_badge(preset)
        self._set_status(f"Applied preset '{preset.name}' (Applied).")

    @Slot()
    def usePresetPrompts(self) -> None:
        """Discard unsaved prompt edits and apply the selected preset's prompts."""
        preset = self._selected_preset()
        if preset is None:
            self._set_status("No preset selected.")
            return
        if preset.prompt_mode == "inherit":
            self._set_status(f"Preset '{preset.name}' has no prompts to apply (Inherited).")
            return
        base = self.prompt_store.load()
        self.prompt_store.save(apply_preset_to_prompts(preset, base))
        if self.settings is not None:
            try:
                self.settings.clear_session_prompts()
            except Exception:
                pass
        self._update_badge(preset)
        self._set_status(f"Applied prompts from '{preset.name}'.")

    @Slot()
    def loadSelectedPrompts(self) -> None:
        """Load the selected preset's prompts into the prompt editor.

        Used by the prompt dialog's preset dropdown: switching presets shows
        that preset's prompts immediately (job-form settings are untouched).
        Unsaved edits are discarded — the status line says so — because keeping
        them would leave the editor showing the previous text and the switch
        would look like a no-op. The main screen's Apply keeps the safe
        keep-edits behaviour.
        """
        preset = self._selected_preset()
        if preset is None:
            self._set_status("No preset selected.")
            return
        had_unsaved = self._has_unsaved_prompts()
        if preset.prompt_mode == "inherit" or (
            preset.prompt_mode == "replace" and not preset.prompts
        ):
            if self.settings is not None:
                try:
                    self.settings.clear_session_prompts()
                except Exception:
                    pass
            self._update_badge(preset)
            self._set_status(
                f"Preset '{preset.name}' stores no prompts; showing the global "
                "prompts (Inherited)."
            )
            return
        base = self.prompt_store.load()
        self.prompt_store.save(apply_preset_to_prompts(preset, base))
        if self.settings is not None:
            try:
                self.settings.clear_session_prompts()
            except Exception:
                pass
        self._update_badge(preset)
        if had_unsaved:
            self._set_status(
                f"Loaded prompts from '{preset.name}'. Your unsaved edits were discarded."
            )
        else:
            self._set_status(f"Loaded prompts from '{preset.name}'.")

    @Slot()
    def updateSelectedPrompts(self) -> None:
        """Save the current effective prompts into the selected preset.

        This is the per-preset save users expect from the prompt editor:
        the selected preset becomes a `replace` preset with a full snapshot
        of what the editor shows (saved store + unsaved edits), the global
        store is updated too, and the session-custom flag is cleared.
        """
        preset = self._selected_preset()
        if preset is None:
            self._set_status("No preset selected.")
            return
        effective = self._effective_prompt_set()
        snapshot = dict(effective.to_dict())
        updated = Preset.capture(preset.name, self.job_form, prompts=snapshot, include_prompts=True)
        self._presets = [entry for entry in self._presets if entry.name != preset.name]
        self._presets.append(updated)
        self._presets.sort(key=lambda entry: entry.name.lower())
        self.preset_store.save(self._presets)
        self.prompt_store.save(effective)
        if self.settings is not None:
            try:
                self.settings.clear_session_prompts()
            except Exception:
                pass
        self._selected_index = next(
            index for index, entry in enumerate(self._presets) if entry.name == preset.name
        )
        self._emit_changed()
        self._update_badge(updated)
        self._set_status(f"Saved prompts into preset '{preset.name}' (Applied).")

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
