"""Ollama adapter package; the old `infrastructure/ollama.py` module became this package.

All previous module-level names are re-exported so existing imports
(`from app.infrastructure.ollama import ...`) keep working unchanged.
"""

import subprocess  # noqa: F401 - kept importable as app.infrastructure.ollama.subprocess for test monkeypatching

from app.infrastructure.llm.transport import chunk_text, clean_thinking_tags
from app.infrastructure.ollama.client import DEFAULT_OLLAMA_URL, OllamaClient, OllamaError
from app.infrastructure.ollama.prompts import (
    PROMPT_HIGHLIGHTS,
    PROMPT_SUMMARY,
    PROMPT_SUMMARY_COMBINE,
    PROMPT_VISION_FRAME,
)
from app.infrastructure.ollama.service_probe import check_ollama_service, list_ollama_models
from app.infrastructure.ollama.text_provider import CHUNK_SIZE, OllamaTextProvider
from app.infrastructure.ollama.vision_provider import OllamaVisionProvider

__all__ = [
    "CHUNK_SIZE",
    "DEFAULT_OLLAMA_URL",
    "PROMPT_HIGHLIGHTS",
    "PROMPT_SUMMARY",
    "PROMPT_SUMMARY_COMBINE",
    "PROMPT_VISION_FRAME",
    "OllamaClient",
    "OllamaError",
    "OllamaTextProvider",
    "OllamaVisionProvider",
    "check_ollama_service",
    "chunk_text",
    "clean_thinking_tags",
    "list_ollama_models",
]
