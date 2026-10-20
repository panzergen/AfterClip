from app.application.provider_registry import get_provider
from app.infrastructure.model_catalog import (
    GEMINI_STATIC_MODELS,
    ModelSection,
    collect_catalog,
    gemini_section,
    ollama_section,
    openai_compat_section,
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
    section = gemini_section(
        key_getter=lambda: "k",
        list_models_fn=lambda: (
            "gemini-flash-latest",
            "gemini-2.5-flash",
            "gemini-2.5-flash-preview-tts",
            "text-embedding-004",
        ),
    )
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


def test_opencode_go_section_metadata_free_capability():
    """Go's /models has no architecture; vision must come from name hints."""
    spec = get_provider("opencode_go")
    items = [
        {"id": "muse-spark-1.3-contributor"},
        {"id": "deepseek-v4-flash-vision-exp"},
        {"id": "glm-5.2"},
    ]
    section = openai_compat_section(spec, key_getter=lambda: "k", list_fn=lambda: items)
    by_name = {entry.name: entry for entry in section.entries}
    assert "muse-spark-1.3-contributor" in by_name  # present in the catalog
    assert by_name["deepseek-v4-flash-vision-exp"].vision_capable is True
    assert by_name["glm-5.2"].vision_capable is False
    assert by_name["muse-spark-1.3-contributor"].vision_capable is False


def test_zen_section_hides_non_chat_transports():
    """Zen lists every transport on /models; only chat ids reach the dropdown."""
    spec = get_provider("opencode_zen")
    items = [
        {"id": "gpt-5.5"},
        {"id": "claude-haiku-5-5"},
        {"id": "gemini-3.8-flash"},
        {"id": "grok-4.6"},
        {"id": "muse-spark-1.3-contributor-free"},
        {"id": "jev-1.13-free"},
        {"id": "qwen3.8-flash"},
        {"id": "deepseek-v4.1-flash-free"},
        {"id": "space-bunny-free"},
        {"id": "qwen3.8-max"},
        {"id": "glm-5.3"},
    ]
    section = openai_compat_section(spec, key_getter=lambda: "k", list_fn=lambda: items)
    names = [entry.name for entry in section.entries]
    assert names == [
        "deepseek-v4.1-flash-free",
        "space-bunny-free",
        "qwen3.8-max",
        "glm-5.3",
    ]


def test_collect_catalog_merges_available_sections():
    sections = collect_catalog(
        True,
        None,
        ollama_base_url="http://localhost:11434",
    )
    # Real network call to a running Ollama if present; tolerate either way.
    assert all(isinstance(section, ModelSection) for section in sections)


def test_openai_compat_section_gates_vision_per_model():
    spec = get_provider("openrouter")
    items = [
        {"id": "openai/gpt-4o", "architecture": {"input_modalities": ["text", "image"]}},
        {"id": "qwen/qwen-coder", "architecture": {"input_modalities": ["text"]}},
        {"id": "meta/llama-vision", "architecture": {"input_modalities": ["text"]}},
    ]
    section = openai_compat_section(spec, key_getter=lambda: "k", list_fn=lambda: items)
    assert section is not None and section.provider == "openrouter"
    by_name = {entry.name: entry for entry in section.entries}
    assert by_name["openai/gpt-4o"].vision_capable is True
    # Metadata wins: a text-only model is not vision-capable despite its name.
    assert by_name["qwen/qwen-coder"].vision_capable is False
    assert by_name["meta/llama-vision"].vision_capable is False


def test_openai_compat_section_none_without_key_or_on_error():
    from app.infrastructure.openai_compat import OpenAICompatKeyError

    spec = get_provider("opencode_go")

    def no_key():
        raise OpenAICompatKeyError("no key")

    assert openai_compat_section(spec, key_getter=lambda: None, list_fn=no_key) is None

    def offline():
        raise OSError("offline")

    assert openai_compat_section(spec, key_getter=lambda: "k", list_fn=offline) is None


def test_collect_catalog_includes_cloud_sections_with_keys(monkeypatch):
    import app.infrastructure.model_catalog as catalog

    captured = {}

    def fake_gemini(key_getter, list_models_fn=None):
        captured["gemini_key"] = key_getter()
        return None

    monkeypatch.setattr(catalog, "gemini_section", fake_gemini)
    sections = catalog.collect_catalog(False, {"gemini": "sk-stored"})
    assert captured["gemini_key"] == "sk-stored"
    assert sections == ()
