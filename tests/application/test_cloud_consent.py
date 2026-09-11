from app.application.cloud_consent import (
    consent_key,
    grant_consent,
    has_consent,
    is_cloud_provider,
    payload_summary,
    revoke_consent,
)
from app.infrastructure.settings import InMemorySettingsStore


def test_local_and_unknown_providers_need_no_consent():
    settings = InMemorySettingsStore()
    assert has_consent(settings, "ollama") is True
    assert has_consent(settings, "") is True
    assert has_consent(settings, None) is True
    assert is_cloud_provider("gemini") is True
    assert is_cloud_provider("ollama") is False
    assert is_cloud_provider(None) is False


def test_grant_and_revoke_roundtrip():
    settings = InMemorySettingsStore()
    assert has_consent(settings, "gemini") is False
    grant_consent(settings, "gemini", "2026-01-01T00:00:00")
    assert has_consent(settings, "gemini") is True
    assert settings.get(consent_key("gemini")) == "2026-01-01T00:00:00"
    revoke_consent(settings, "gemini")
    assert has_consent(settings, "gemini") is False


def test_payload_summary_describes_what_leaves_machine():
    text_only = payload_summary(True, False)
    assert "transcript text" in text_only
    assert "never uploaded" in text_only

    vision_only = payload_summary(False, True)
    assert "frame" in vision_only

    both = payload_summary(True, True)
    assert "transcript text" in both
    assert "frame" in both

    assert "No media content" in payload_summary(False, False)
