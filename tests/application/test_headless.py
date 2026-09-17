import pytest

from app.application.headless import (
    ProviderUnavailableError,
    build_providers,
    resolve_segment_seconds,
)


class NoKeyStore:
    def get(self, name):
        return None

    def set(self, name, value):
        pass

    def delete(self, name):
        pass


def test_build_providers_unknown_provider():
    with pytest.raises(ProviderUnavailableError, match="Unknown provider"):
        build_providers("nope", "m", "m", False, False)


def test_build_providers_cloud_without_key(monkeypatch):
    monkeypatch.setattr("app.application.headless.KeyringSecretStore", NoKeyStore)
    with pytest.raises(ProviderUnavailableError, match="API key"):
        build_providers("openrouter", "m", "", True, False)


def test_build_providers_local_has_no_key_requirement(monkeypatch):
    monkeypatch.setattr("app.application.headless.KeyringSecretStore", NoKeyStore)
    text_provider, vision_provider = build_providers("ollama", "llama3", "", True, False)
    assert text_provider is not None
    assert vision_provider is None


def test_resolve_segment_seconds_default(monkeypatch):
    class Store:
        def get(self, key):
            return None

    monkeypatch.setattr("app.application.headless.JsonSettingsStore", lambda: Store())
    assert resolve_segment_seconds() == 30.0


def test_resolve_segment_seconds_disabled(monkeypatch):
    class Store:
        def get(self, key):
            return 0

    monkeypatch.setattr("app.application.headless.JsonSettingsStore", lambda: Store())
    assert resolve_segment_seconds() is None
