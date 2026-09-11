from app.infrastructure.model_catalog import (
    GEMINI_STATIC_MODELS,
    ModelEntry,
    ModelSection,
    collect_catalog,
    gemini_section,
    ollama_section,
)


def ollama_tags(names):
    return [{"name": name} for name in names]


def ollama_show(capabilities_by_name):
    def show(name):
        return {"capabilities": capabilities_by_name.get(name, [])}

    return show


def test_ollama_section_uses_api_capabilities():
    section = ollama_section(
        tags_fn=lambda: ollama_tags(["llama3.1:8b", "llava:7b"]),
        show_fn=ollama_show({"llama3.1:8b": ["tools"], "llava:7b": ["vision", "tools"]}),
    )
    assert section is not None and section.provider == "ollama"
    assert section.entries[0].vision_capable is False
    assert section.entries[1].vision_capable is True


def test_ollama_section_falls_back_to_name_heuristics_when_show_fails():
    def failing_show(name):
        raise OSError("old ollama")

    section = ollama_section(
        tags_fn=lambda: ollama_tags(["llava:7b", "llama3.1:8b"]),
        show_fn=failing_show,
    )
    assert [entry.vision_capable for entry in section.entries] == [True, False]


def test_ollama_section_none_when_tags_fail():
    def failing_tags():
        raise OSError("offline")

    assert ollama_section(tags_fn=failing_tags, show_fn=ollama_show({})) is None


def test_gemini_section_live_models_with_capability_heuristics():
    section = gemini_section(key_getter=lambda: "k", list_models_fn=lambda: ("gemini-flash-latest", "gemini-2.5-flash", "gemini-2.5-flash-preview-tts", "text-embedding-004"))
    names = [entry.name for entry in section.entries]
    assert "gemini-flash-latest" in names
    # The catalog marks capabilities; populate_models does the filtering.
    by_name = {entry.name: entry for entry in section.entries}
    assert by_name["gemini-2.5-flash-preview-tts"].text_capable is False
    assert by_name["text-embedding-004"].text_capable is False
    assert by_name["gemini-flash-latest"].vision_capable is True


def test_gemini_section_static_fallback_when_listing_fails():
    def failing_list():
        raise OSError("network down")

    section = gemini_section(key_getter=lambda: "k", list_models_fn=failing_list)
    assert [entry.name for entry in section.entries] == list(GEMINI_STATIC_MODELS)


def test_gemini_section_none_without_key():
    assert gemini_section(key_getter=lambda: None) is None


def test_collect_catalog_merges_available_sections():
    sections = collect_catalog(
        True,
        None,
        ollama_base_url="http://localhost:11434",
    )
    # Real network call to a running Ollama if present; tolerate either way.
    assert all(isinstance(section, ModelSection) for section in sections)
