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
    assert get_provider("gemini").kind == "gemini"
    assert get_provider("ollama").kind == "ollama"
    assert get_provider("nope") is None
    assert get_provider(None) is None


def test_cloud_classification():
    assert is_cloud("openrouter") is True
    assert is_cloud("opencode_go") is True
    assert is_cloud("gemini") is True
    assert is_cloud("ollama") is False
    assert is_cloud(None) is False
    assert set(cloud_provider_ids()) == {"gemini", "openrouter", "opencode_go"}
