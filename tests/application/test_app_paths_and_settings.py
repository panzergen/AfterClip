import json
import sys
from pathlib import Path

import pytest

from app.app_paths import (
    app_data_dir,
    default_input_dir,
    default_output_dir,
    project_dir,
    repository_dir,
)
from app.infrastructure.settings import (
    SETTINGS_SCHEMA_VERSION,
    InMemorySettingsStore,
    JsonSettingsStore,
    SettingsSchemaError,
    migrate_settings,
)


def test_project_dir_honours_afterclip_home(monkeypatch, tmp_path):
    monkeypatch.setenv("AFTERCLIP_HOME", str(tmp_path))
    assert project_dir() == tmp_path.resolve()
    assert default_input_dir() == tmp_path.resolve() / "Input-Folder"
    assert default_output_dir() == tmp_path.resolve() / "Output-Folder"


def test_project_dir_falls_back_to_workspace_or_repository():
    repository = repository_dir()
    workspace = repository.parent
    expected = workspace if (workspace / "Input-Folder").exists() else repository
    assert project_dir() == expected


def test_app_data_dir_uses_platform_conventions(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)

    monkeypatch.setattr(sys, "platform", "win32")
    assert app_data_dir() == tmp_path / "AppData" / "Local" / "AfterClip"

    monkeypatch.setattr(sys, "platform", "darwin")
    assert app_data_dir() == tmp_path / "Library" / "Application Support" / "AfterClip"

    monkeypatch.setattr(sys, "platform", "linux")
    assert app_data_dir() == tmp_path / ".local" / "share" / "AfterClip"

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert app_data_dir() == tmp_path / "xdg" / "AfterClip"


def test_in_memory_settings_roundtrip():
    store = InMemorySettingsStore()
    assert store.get("missing") is None
    store.set("model", "small")
    assert store.get("model") == "small"
    store.set("model", "tiny")
    assert store.get("model") == "tiny"
    assert store.migrate() is False


def test_json_settings_roundtrip(tmp_path):
    store = JsonSettingsStore(tmp_path / "nested" / "settings.json")
    store.set("language", "tr")
    assert store.get("language") == "tr"
    reloaded = JsonSettingsStore(tmp_path / "nested" / "settings.json")
    assert reloaded.get("language") == "tr"
    payload = json.loads((tmp_path / "nested" / "settings.json").read_text(encoding="utf-8"))
    assert payload["language"] == "tr"
    assert payload["version"] == SETTINGS_SCHEMA_VERSION


def test_json_settings_tolerates_missing_and_corrupt_file(tmp_path):
    corrupt = tmp_path / "settings.json"
    corrupt.write_text("{not json", encoding="utf-8")
    store = JsonSettingsStore(corrupt)
    assert store.get("anything") is None
    store.set("theme", "dark")
    assert store.get("theme") == "dark"


def test_migrate_settings_stamps_current_version():
    migrated, changed = migrate_settings({"language": "tr"})
    assert changed is True
    assert migrated["version"] == SETTINGS_SCHEMA_VERSION
    assert migrated["language"] == "tr"


def test_migrate_settings_is_noop_when_current():
    migrated, changed = migrate_settings(
        {"version": SETTINGS_SCHEMA_VERSION, "language": "tr"}
    )
    assert changed is False
    assert migrated["version"] == SETTINGS_SCHEMA_VERSION


def test_migrate_settings_rejects_newer_schema():
    with pytest.raises(SettingsSchemaError):
        migrate_settings({"version": SETTINGS_SCHEMA_VERSION + 1})


def test_json_settings_persists_migration(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"language": "tr"}), encoding="utf-8")
    store = JsonSettingsStore(path)
    assert store.get("language") == "tr"
    assert store.migrate() is True
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["language"] == "tr"
    assert payload["version"] == SETTINGS_SCHEMA_VERSION
    assert store.migrate() is False


def test_json_settings_set_refuses_newer_schema(tmp_path):
    path = tmp_path / "settings.json"
    original = {"version": SETTINGS_SCHEMA_VERSION + 1, "language": "tr"}
    path.write_text(json.dumps(original), encoding="utf-8")
    store = JsonSettingsStore(path)
    assert store.get("language") is None
    assert store.migrate() is False
    store.set("language", "en")
    assert json.loads(path.read_text(encoding="utf-8")) == original
