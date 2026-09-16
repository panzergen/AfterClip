"""Cloud provider consent policy (Phase 3 privacy requirements).

Local providers (Ollama, Whisper) never require consent. Cloud providers must
have explicit, revocable, persisted consent before any media content is sent.
Video and audio files are never uploaded; only transcript text and/or single
frame images may leave the machine (T18b/T18c).
"""

from typing import Protocol

from app.application.provider_registry import cloud_provider_ids

CLOUD_PROVIDERS = frozenset(cloud_provider_ids())
CONSENT_KEY_PREFIX = "cloud_consent_"


class SettingsLike(Protocol):
    def get(self, key: str): ...
    def set(self, key: str, value) -> None: ...


def is_cloud_provider(provider: str | None) -> bool:
    return bool(provider) and provider in CLOUD_PROVIDERS


def consent_key(provider: str) -> str:
    return f"{CONSENT_KEY_PREFIX}{provider}"


def has_consent(settings: SettingsLike, provider: str) -> bool:
    """Local/unknown providers are always allowed; cloud requires a stored flag."""
    if not is_cloud_provider(provider):
        return True
    return bool(settings.get(consent_key(provider)))


def grant_consent(settings: SettingsLike, provider: str, stamp: str) -> None:
    settings.set(consent_key(provider), stamp)


def revoke_consent(settings: SettingsLike, provider: str) -> None:
    settings.set(consent_key(provider), None)


def payload_summary(analyze_text: bool, analyze_vision: bool) -> str:
    """Human-readable statement of exactly what a cloud job would upload."""
    items: list[str] = []
    if analyze_text:
        items.append("the transcript text (audio is transcribed locally)")
    if analyze_vision:
        items.append("single extracted frame images")
    if not items:
        return "No media content leaves this machine."
    joined = " and ".join(items)
    return (
        f"Cloud AI is enabled. AfterClip will send {joined} to the provider. "
        "The video and audio files themselves are never uploaded."
    )
