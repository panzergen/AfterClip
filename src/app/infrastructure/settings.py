import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.app_paths import app_data_dir

LOGGER = logging.getLogger(__name__)

# Bump when a migration step is added to _MIGRATIONS. Existing files are
# upgraded in memory on read and re-stamped on the next write.
SETTINGS_SCHEMA_VERSION = 1


class SettingsSchemaError(ValueError):
    """Raised when a settings payload cannot be brought to the current schema."""


def _migrate_v0_to_v1(data: dict[str, Any]) -> dict[str, Any]:
    """v0 files had no ``version`` field but the same keys.

    This step only stamps the schema version; future migrations chain here.
    """
    return data


_MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {
    0: _migrate_v0_to_v1,
}


def migrate_settings(data: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Return ``(migrated, changed)`` bringing a settings payload up to date.

    Raises ``SettingsSchemaError`` when the file was written by a newer app
    version: downgrading could silently drop settings we do not understand.
    """
    working = dict(data)
    try:
        version = int(working.get("version", 0))
    except (TypeError, ValueError):
        version = 0
    if version > SETTINGS_SCHEMA_VERSION:
        raise SettingsSchemaError(
            f"settings schema v{version} is newer than supported v{SETTINGS_SCHEMA_VERSION}"
        )
    changed = False
    while version < SETTINGS_SCHEMA_VERSION:
        migration = _MIGRATIONS.get(version)
        if migration is not None:
            working = migration(working)
        version += 1
        changed = True
    if working.get("version") != SETTINGS_SCHEMA_VERSION:
        working["version"] = SETTINGS_SCHEMA_VERSION
        changed = True
    return working, changed


class InMemorySettingsStore:
    """Simple dict-backed store for tests and default fallbacks."""

    def __init__(self, values: dict[str, Any] | None = None):
        self._values = dict(values or {})

    def get(self, key: str) -> Any:
        return self._values.get(key)

    def set(self, key: str, value: Any) -> None:
        self._values[key] = value

    def migrate(self) -> bool:
        return False


class JsonSettingsStore:
    """JSON-file settings persistence; defaults to the per-user data directory."""

    def __init__(self, path: Path | None = None):
        if path is None:
            path = app_data_dir() / "settings.json"
        self.path = path

    def get(self, key: str) -> Any:
        return self._read().get(key)

    def set(self, key: str, value: Any) -> None:
        raw = self._read_raw()
        if raw:
            try:
                data, _ = migrate_settings(raw)
            except SettingsSchemaError as error:
                # Never overwrite a file written by a newer app version.
                LOGGER.error("Refusing to write settings file: %s", error)
                return
        else:
            data = {}
        data[key] = value
        data["version"] = SETTINGS_SCHEMA_VERSION
        self._write(data)

    def migrate(self) -> bool:
        """Persist schema migrations to disk; returns True if the file changed."""
        raw = self._read_raw()
        if not raw:
            return False
        try:
            migrated, changed = migrate_settings(raw)
        except SettingsSchemaError as error:
            LOGGER.error("Refusing to migrate settings file: %s", error)
            return False
        if changed:
            self._write(migrated)
        return changed

    def _read(self) -> dict[str, Any]:
        raw = self._read_raw()
        if not raw:
            return {}
        try:
            migrated, _ = migrate_settings(raw)
        except SettingsSchemaError as error:
            LOGGER.error("Refusing to read settings file: %s", error)
            return {}
        return migrated

    def _read_raw(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            LOGGER.debug("Settings file not readable (%s): %s", self.path, error)
            return {}
        return payload if isinstance(payload, dict) else {}

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
