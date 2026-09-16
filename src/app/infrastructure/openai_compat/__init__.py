"""OpenAI-compatible provider adapter (Phase 4 WS-A).

Shared by OpenRouter (``openrouter``) and OpenCode Go (``opencode_go``). The
upload policy in :mod:`app.infrastructure.cloud_policy` ensures only text and
single frames are ever sent (video is impossible); keys live in the OS
credential manager and are scrubbed from logs.
"""

from app.infrastructure.openai_compat.capabilities import infer_vision_capable
from app.infrastructure.openai_compat.client import (
    DEFAULT_OPENAI_COMPAT_BASE_URL,
    OpenAICompatClient,
    OpenAICompatError,
    OpenAICompatKeyError,
    extract_text,
)
from app.infrastructure.openai_compat.text_provider import OpenAICompatTextProvider
from app.infrastructure.openai_compat.vision_provider import OpenAICompatVisionProvider

__all__ = [
    "DEFAULT_OPENAI_COMPAT_BASE_URL",
    "OpenAICompatClient",
    "OpenAICompatError",
    "OpenAICompatKeyError",
    "OpenAICompatTextProvider",
    "OpenAICompatVisionProvider",
    "extract_text",
    "infer_vision_capable",
]
