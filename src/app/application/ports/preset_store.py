from typing import Protocol

from app.domain.presets import Preset


class PresetStore(Protocol):
    """Persistence for named media-type presets (Phase 4 WS-B)."""

    def load(self) -> list[Preset]: ...
    def save(self, presets: list[Preset]) -> None: ...
