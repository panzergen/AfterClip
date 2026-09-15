import json

from app.domain.presets import Preset
from app.infrastructure.presets import InMemoryPresetStore, JsonPresetStore


def test_in_memory_roundtrip():
    store = InMemoryPresetStore()
    assert store.load() == []
    store.save([Preset("a"), Preset("b")])
    assert [preset.name for preset in store.load()] == ["a", "b"]


def test_json_store_roundtrip(tmp_path):
    path = tmp_path / "presets.json"
    store = JsonPresetStore(path)
    assert store.load() == []

    store.save([Preset("meeting", whisper_model="small", prompt_overrides={"summary": "s"})])
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["version"] == 1

    loaded = JsonPresetStore(path).load()
    assert loaded[0].name == "meeting"
    assert loaded[0].whisper_model == "small"
    assert loaded[0].prompt_overrides == {"summary": "s"}


def test_json_store_skips_malformed_and_corrupt(tmp_path):
    path = tmp_path / "presets.json"
    path.write_text(
        json.dumps({"presets": [{"name": "ok"}, {"no_name": 1}, "junk"]}), encoding="utf-8"
    )
    assert [preset.name for preset in JsonPresetStore(path).load()] == ["ok"]

    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert JsonPresetStore(bad).load() == []
