from app.application.providers import build_text_provider, build_vision_provider
from app.infrastructure.gemini import GeminiTextProvider, GeminiVisionProvider
from app.infrastructure.ollama import OllamaTextProvider, OllamaVisionProvider
from app.infrastructure.openai_compat import (
    OpenAICompatTextProvider,
    OpenAICompatVisionProvider,
)


def test_build_none_for_empty_spec():
    assert build_text_provider(None) is None
    assert build_vision_provider(None) is None


def test_build_openai_compat_for_openrouter_and_opencode_go():
    text = build_text_provider(("openrouter", "openai/gpt-4o"))
    assert isinstance(text, OpenAICompatTextProvider)
    assert text.provider_name == "openrouter"

    vision = build_vision_provider(("opencode_go", "some/model"))
    assert isinstance(vision, OpenAICompatVisionProvider)
    assert vision.provider_name == "opencode_go"


def test_build_local_and_gemini():
    assert isinstance(build_text_provider(("ollama", "llama3")), OllamaTextProvider)
    assert isinstance(build_vision_provider(("ollama", "llava")), OllamaVisionProvider)
    assert isinstance(build_text_provider(("gemini", "gemini-2.5-flash")), GeminiTextProvider)
    assert isinstance(
        build_vision_provider(("gemini", "gemini-2.5-flash")), GeminiVisionProvider
    )
