import json
import logging
from pathlib import Path

from app.app_paths import app_data_dir
from app.domain.presets import Preset
from app.infrastructure.atomic_file import atomic_write_text as _atomic_write_text

LOGGER = logging.getLogger(__name__)

PRESETS_SCHEMA_VERSION = 1


class InMemoryPresetStore:
    def __init__(self, presets: list[Preset] | None = None):
        self._presets = list(presets or [])

    def load(self) -> list[Preset]:
        return list(self._presets)

    def save(self, presets: list[Preset]) -> None:
        self._presets = list(presets)


class JsonPresetStore:
    """JSON preset persistence; defaults to %LOCALAPPDATA%/AfterClip/presets.json."""

    def __init__(self, path: Path | None = None):
        self.path = path or (app_data_dir() / "presets.json")

    def load(self) -> list[Preset]:
        raw = self._read()
        items = raw.get("presets", []) if isinstance(raw, dict) else []
        presets: list[Preset] = []
        for item in items:
            if isinstance(item, dict) and item.get("name"):
                try:
                    presets.append(Preset.from_dict(item))
                except (TypeError, ValueError) as error:
                    LOGGER.debug("Skipping malformed preset: %s", error)
        return presets

    def save(self, presets: list[Preset]) -> None:
        payload = {
            "version": PRESETS_SCHEMA_VERSION,
            "presets": [preset.to_dict() for preset in presets],
        }
        _atomic_write_text(self.path, json.dumps(payload, ensure_ascii=False, indent=2))

    def _read(self) -> dict:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            LOGGER.debug("Preset file not readable (%s): %s", self.path, error)
            return {}
        return payload if isinstance(payload, dict) else {}
