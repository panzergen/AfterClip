from app.application.provider_registry import (
    cloud_provider_ids,
    get_provider,
    is_cloud,
)


def test_registry_entries():
    assert get_provider("openrouter").base_url == "https://openrouter.ai/api/v1"
    assert get_provider("openrouter").key_name == "openrouter_api_key"
    assert get_provider("opencode_go").base_url == "https://opencode.ai/zen/go/v1"
    assert get_provider("opencode_go").key_name == "opencode_go_api_key"
    assert get_provider("opencode_zen").base_url == "https://opencode.ai/zen/v1"
    assert get_provider("opencode_zen").key_name == "opencode_go_api_key"
    assert get_provider("opencode_zen").kind == "openai_compat"
    assert get_provider("gemini").kind == "gemini"
    assert get_provider("ollama").kind == "ollama"
    assert get_provider("nope") is None
    assert get_provider(None) is None


def test_cloud_classification():
    assert is_cloud("openrouter") is True
    assert is_cloud("opencode_go") is True
    assert is_cloud("opencode_zen") is True
    assert is_cloud("gemini") is True
    assert is_cloud("ollama") is False
    assert is_cloud(None) is False
    assert set(cloud_provider_ids()) == {"gemini", "openrouter", "opencode_go", "opencode_zen"}


def test_zen_excludes_non_chat_transports():
    prefixes = get_provider("opencode_zen").exclude_name_prefixes
    for blocked in (
        "gpt-5.5",
        "claude-haiku-5-5",
        "gemini-3.8-flash",
        "grok-4.6",
        "muse-spark-1.3-contributor-free",
        "jev-1.13-free",
        "qwen3.8-flash",
        "qwen3.7-plus",
    ):
        assert blocked.lower().startswith(prefixes), blocked
    for allowed in (
        "deepseek-v4.1-flash-free",
        "space-bunny-free",
        "big-pickle",
        "qwen3.8-max",
        "glm-5.3",
        "kimi-k3",
        "minimax-m3",
    ):
        assert not allowed.lower().startswith(prefixes), allowed
