import json

from app.app_paths import default_input_dir, default_output_dir, project_dir, repository_dir
from app.infrastructure.settings import InMemorySettingsStore, JsonSettingsStore


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


def test_in_memory_settings_roundtrip():
    store = InMemorySettingsStore()
    assert store.get("missing") is None
    store.set("model", "small")
    assert store.get("model") == "small"
    store.set("model", "tiny")
    assert store.get("model") == "tiny"


def test_json_settings_roundtrip(tmp_path):
    store = JsonSettingsStore(tmp_path / "nested" / "settings.json")
    store.set("language", "tr")
    assert store.get("language") == "tr"
    reloaded = JsonSettingsStore(tmp_path / "nested" / "settings.json")
    assert reloaded.get("language") == "tr"
    assert json.loads((tmp_path / "nested" / "settings.json").read_text(encoding="utf-8")) == {"language": "tr"}


def test_json_settings_tolerates_missing_and_corrupt_file(tmp_path):
    corrupt = tmp_path / "settings.json"
    corrupt.write_text("{not json", encoding="utf-8")
    store = JsonSettingsStore(corrupt)
    assert store.get("anything") is None
    store.set("theme", "dark")
    assert store.get("theme") == "dark"
