"""Non-Qt job composition for the CLI and MCP server (Phase 4 WS-E).

Builds the transcription pipeline without importing PySide6 so scripts and
agents can drive AfterClip headlessly with the same service the GUI uses.
"""

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from app.application.cancellation import CancellationToken
from app.application.provider_registry import get_provider
from app.application.providers import build_text_provider, build_vision_provider
from app.application.topics import (
    DEFAULT_TOPIC_MAX_SECTIONS,
    DEFAULT_TOPIC_METHOD,
    DEFAULT_TOPIC_MIN_SECONDS,
    TOPIC_METHODS,
)
from app.application.transcript_sanitizer import SanitizerConfig
from app.domain.models import ProgressEvent, TranscriptionRequest
from app.domain.prompts import PromptSet
from app.infrastructure.process import FfmpegMediaTool, WhisperCliProvider
from app.infrastructure.prompts import JsonPromptStore
from app.infrastructure.secrets import KeyringSecretStore
from app.infrastructure.settings import JsonSettingsStore
from app.infrastructure.voiceprints import JsonVoiceprintStore

SANITIZER_SETTINGS_KEY = "transcript_filter"
SEGMENT_SETTINGS_KEY = "transcript_segment_seconds"
TOPIC_METHOD_SETTINGS_KEY = "topic_method"
TOPIC_MIN_SETTINGS_KEY = "topic_min_seconds"
TOPIC_MAX_SETTINGS_KEY = "topic_max_sections"
DEFAULT_SEGMENT_SECONDS = 30.0


class ProviderUnavailableError(RuntimeError):
    """Raised when a requested provider cannot be used (unknown id, missing key)."""


def resolve_prompts(path: Path | None = None) -> PromptSet:
    return (JsonPromptStore(path) if path else JsonPromptStore()).load()


def resolve_sanitizer(enabled: bool | None = None) -> SanitizerConfig:
    config = SanitizerConfig.from_dict(JsonSettingsStore().get(SANITIZER_SETTINGS_KEY) or {})
    return config if enabled is None else replace(config, enabled=enabled)


def resolve_segment_seconds() -> float | None:
    """Default transcript merge seconds from settings (0/<=0 means Whisper raw)."""
    stored = JsonSettingsStore().get(SEGMENT_SETTINGS_KEY)
    if stored is None:
        return DEFAULT_SEGMENT_SECONDS
    try:
        value = float(stored)
    except (TypeError, ValueError):
        return DEFAULT_SEGMENT_SECONDS
    return value if value > 0 else None


def resolve_topics() -> tuple[str, float, int]:
    """Topic segmentation settings: (method, min_seconds, max_sections)."""
    store = JsonSettingsStore()
    method = str(store.get(TOPIC_METHOD_SETTINGS_KEY) or DEFAULT_TOPIC_METHOD)
    if method not in TOPIC_METHODS:
        method = DEFAULT_TOPIC_METHOD
    try:
        min_seconds = float(store.get(TOPIC_MIN_SETTINGS_KEY) or DEFAULT_TOPIC_MIN_SECONDS)
    except (TypeError, ValueError):
        min_seconds = DEFAULT_TOPIC_MIN_SECONDS
    try:
        max_sections = int(store.get(TOPIC_MAX_SETTINGS_KEY) or DEFAULT_TOPIC_MAX_SECTIONS)
    except (TypeError, ValueError):
        max_sections = DEFAULT_TOPIC_MAX_SECTIONS
    return method, max(0.0, min_seconds), max(0, max_sections)


def build_providers(
    provider_name: str | None,
    text_model: str,
    vision_model: str,
    analyze_text: bool,
    analyze_vision: bool,
    prompts: PromptSet | None = None,
):
    """Resolve (text_provider, vision_provider) from registry specs.

    Raises ``ProviderUnavailableError`` for an unknown provider or a cloud provider
    without a stored key; a missing key must never produce a silent request.
    """
    spec = get_provider(provider_name) if provider_name else None
    if provider_name and spec is None:
        raise ProviderUnavailableError(f"Unknown provider: {provider_name}")
    if spec is not None and spec.is_cloud and not KeyringSecretStore().get(spec.key_name):
        raise ProviderUnavailableError(
            f"No {spec.label} API key is stored. Add one in Settings first."
        )
    text_provider = (
        build_text_provider((provider_name, text_model), prompts)
        if analyze_text and provider_name
        else None
    )
    vision_provider = (
        build_vision_provider((provider_name, vision_model), prompts)
        if analyze_vision and provider_name
        else None
    )
    return text_provider, vision_provider


def run_request(
    request: TranscriptionRequest,
    text_provider=None,
    vision_provider=None,
    sanitizer_config: SanitizerConfig | None = None,
    on_event: Callable[[ProgressEvent], None] | None = None,
    cancel_token=None,
    resume_dir: Path | None = None,
):
    from app.application.service import TranscriptionService

    service = TranscriptionService(
        WhisperCliProvider(
            condition_on_previous_text=not (sanitizer_config and sanitizer_config.enabled)
        ),
        FfmpegMediaTool(),
        text_provider,
        vision_provider,
        sanitizer_config=sanitizer_config,
        # The store is enough to restore names on a resumed job; embedding new
        # audio still needs the optional extra and a request that enables it.
        voiceprint_store=JsonVoiceprintStore(),
    )
    return service.run(
        request,
        on_event or (lambda _event: None),
        cancel_token or CancellationToken(),
        resume_dir=resume_dir,
    )
