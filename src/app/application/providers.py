"""Shared AI provider construction for single jobs and batch jobs.

Provider identity is resolved through ``application.provider_registry`` so
adding a provider is a registry entry plus an adapter, not a new branch here.
"""
from app.application.provider_registry import (
    KIND_GEMINI,
    KIND_OPENAI_COMPAT,
    get_provider,
)
from app.infrastructure.gemini import GeminiTextProvider, GeminiVisionProvider
from app.infrastructure.ollama import OllamaTextProvider, OllamaVisionProvider
from app.infrastructure.openai_compat import (
    OpenAICompatTextProvider,
    OpenAICompatVisionProvider,
)
from app.infrastructure.secrets import KeyringSecretStore


def _key_getter(spec):
    return lambda: KeyringSecretStore().get(spec.key_name)


def build_text_provider(spec: tuple[str, str] | None, prompts=None):
    if not spec:
        return None
    provider_name, model = spec
    resolved = get_provider(provider_name)
    if resolved is None:
        return OllamaTextProvider(model, prompts=prompts)
    if resolved.kind == KIND_GEMINI:
        return GeminiTextProvider(model, prompts=prompts)
    if resolved.kind == KIND_OPENAI_COMPAT:
        return OpenAICompatTextProvider(
            model,
            prompts=prompts,
            base_url=resolved.base_url,
            provider=resolved.id,
            key_getter=_key_getter(resolved),
        )
    return OllamaTextProvider(model, prompts=prompts)


def build_vision_provider(spec: tuple[str, str] | None, prompts=None):
    if not spec:
        return None
    provider_name, model = spec
    resolved = get_provider(provider_name)
    if resolved is None:
        return OllamaVisionProvider(model, prompts=prompts)
    if resolved.kind == KIND_GEMINI:
        return GeminiVisionProvider(model, prompts=prompts)
    if resolved.kind == KIND_OPENAI_COMPAT:
        return OpenAICompatVisionProvider(
            model,
            prompts=prompts,
            base_url=resolved.base_url,
            provider=resolved.id,
            key_getter=_key_getter(resolved),
        )
    return OllamaVisionProvider(model, prompts=prompts)
