import json

from app.domain.prompts import DEFAULT_PROMPTS, build_prompt_set
from app.infrastructure.prompts import InMemoryPromptStore, JsonPromptStore


def test_in_memory_store_roundtrip():
    store = InMemoryPromptStore()
    assert store.load().summary == DEFAULT_PROMPTS["summary"]
    store.save(build_prompt_set({"summary": "custom {lang} {transcript}"}))
    assert store.load().summary == "custom {lang} {transcript}"


def test_json_prompt_store_roundtrip(tmp_path):
    path = tmp_path / "prompts.json"
    store = JsonPromptStore(path)
    assert store.load().summary == DEFAULT_PROMPTS["summary"]  # missing file -> defaults

    store.save(build_prompt_set({"highlights": "custom highlights {lang} {srt_content}"}))
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert payload["highlights"] == "custom highlights {lang} {srt_content}"

    reloaded = JsonPromptStore(path)
    assert reloaded.load().highlights == "custom highlights {lang} {srt_content}"
    assert reloaded.load().summary == DEFAULT_PROMPTS["summary"]


def test_json_prompt_store_ignores_unknown_keys(tmp_path):
    path = tmp_path / "prompts.json"
    path.write_text(
        json.dumps({"summary": "ok {lang} {transcript}", "bogus": "x", "version": 9}),
        encoding="utf-8",
    )
    loaded = JsonPromptStore(path).load()
    assert loaded.summary == "ok {lang} {transcript}"


def test_json_prompt_store_tolerates_corrupt_file(tmp_path):
    corrupt = tmp_path / "bad.json"
    corrupt.write_text("{not json", encoding="utf-8")
    assert JsonPromptStore(corrupt).load().summary == DEFAULT_PROMPTS["summary"]
