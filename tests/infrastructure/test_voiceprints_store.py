import json

from app.infrastructure.voiceprints import (
    InMemoryVoiceprintStore,
    JsonVoiceprintStore,
)


def test_in_memory_store_round_trip():
    store = InMemoryVoiceprintStore()
    store.save("Alice", [0.1, 0.2, 0.3])
    assert store.load() == {"Alice": [0.1, 0.2, 0.3]}
    store.remove("Alice")
    assert store.load() == {}


def test_json_store_round_trip(tmp_path):
    path = tmp_path / "voiceprints.json"
    store = JsonVoiceprintStore(path)
    store.save("Alice", [0.1, 0.2, 0.3])
    store.save("Bob", [0.4, 0.5, 0.6])
    reloaded = JsonVoiceprintStore(path).load()
    assert reloaded == {"Alice": [0.1, 0.2, 0.3], "Bob": [0.4, 0.5, 0.6]}


def test_json_store_remove(tmp_path):
    path = tmp_path / "voiceprints.json"
    store = JsonVoiceprintStore(path)
    store.save("Alice", [0.1, 0.2])
    store.remove("Alice")
    assert store.load() == {}


def test_json_store_rejects_invalid_entries(tmp_path):
    path = tmp_path / "voiceprints.json"
    store = JsonVoiceprintStore(path)
    store.save("ok", [0.1, 0.2])
    path.write_text(
        json.dumps({"version": 1, "voiceprints": {"bad": "not-a-list", "empty": []}}),
        encoding="utf-8",
    )
    assert store.load() == {}


def test_json_store_missing_file_loads_empty(tmp_path):
    assert JsonVoiceprintStore(tmp_path / "nope.json").load() == {}


def test_json_store_rejects_save_without_valid_embedding(tmp_path):
    store = JsonVoiceprintStore(tmp_path / "voiceprints.json")
    try:
        store.save("bad", [])
    except ValueError:
        pass
    else:
        raise AssertionError("empty embedding must be rejected")
