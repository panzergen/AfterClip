import json
import logging
from pathlib import Path
from typing import Any

from app.app_paths import app_data_dir

LOGGER = logging.getLogger(__name__)


class InMemorySettingsStore:
    """Simple dict-backed store for tests and default fallbacks."""

    def __init__(self, values: dict[str, Any] | None = None):
        self._values = dict(values or {})

    def get(self, key: str) -> Any:
        return self._values.get(key)

    def set(self, key: str, value: Any) -> None:
        self._values[key] = value


class JsonSettingsStore:
    """JSON-file settings persistence; defaults to %LOCALAPPDATA%/AfterClip/settings.json."""

    def __init__(self, path: Path | None = None):
        if path is None:
            path = app_data_dir() / "settings.json"
        self.path = path

    def get(self, key: str) -> Any:
        return self._read().get(key)

    def set(self, key: str, value: Any) -> None:
        data = self._read()
        data[key] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _read(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            LOGGER.debug("Settings file not readable (%s): %s", self.path, error)
            return {}
