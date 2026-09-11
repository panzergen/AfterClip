"""Shared AI provider construction for single jobs and batch jobs."""
from app.infrastructure.gemini import GeminiTextProvider, GeminiVisionProvider
from app.infrastructure.ollama import OllamaTextProvider, OllamaVisionProvider


def build_text_provider(spec: tuple[str, str] | None):
    if not spec:
        return None
    provider_name, model = spec
    if provider_name == "gemini":
        return GeminiTextProvider(model)
    return OllamaTextProvider(model)


def build_vision_provider(spec: tuple[str, str] | None):
    if not spec:
        return None
    provider_name, model = spec
    if provider_name == "gemini":
        return GeminiVisionProvider(model)
    return OllamaVisionProvider(model)
