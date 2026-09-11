"""Gemini cloud adapter (Phase 2). Text analysis and single-frame vision run
through the Generative Language API; the upload policy in `permissions.py`
makes video uploads impossible (T18b/T18c). The API key lives only in the
Windows Credential Manager via `KeyringSecretStore` (T19/T20) and is scrubbed
from logs by the redaction filter (T22).
"""
from app.infrastructure.gemini.client import (
    DEFAULT_GEMINI_MODEL,
    DEFAULT_GEMINI_URL,
    GEMINI_KEY_NAME,
    GeminiClient,
    GeminiError,
    GeminiKeyMissing,
    extract_text,
)
from app.infrastructure.gemini.permissions import ALLOWED_INLINE_MIME_TYPES, CloudPolicyViolation, inline_data_part
from app.infrastructure.gemini.text_provider import CHUNK_SIZE, GeminiTextProvider
from app.infrastructure.gemini.vision_provider import GeminiVisionProvider

__all__ = [
    "ALLOWED_INLINE_MIME_TYPES",
    "CHUNK_SIZE",
    "DEFAULT_GEMINI_MODEL",
    "DEFAULT_GEMINI_URL",
    "GEMINI_KEY_NAME",
    "CloudPolicyViolation",
    "GeminiClient",
    "GeminiError",
    "GeminiKeyMissing",
    "GeminiTextProvider",
    "GeminiVisionProvider",
    "extract_text",
    "inline_data_part",
]
