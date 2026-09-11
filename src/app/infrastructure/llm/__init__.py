"""Shared LLM transport and text utilities, reusable by any local/cloud provider
(Ollama today, Gemini in Phase 2) without copy-paste."""
from app.infrastructure.llm.transport import (
    chunk_text,
    clean_highlights_output,
    clean_thinking_tags,
    http_post_json,
    post_json_cancellable,
)

__all__ = [
    "chunk_text",
    "clean_highlights_output",
    "clean_thinking_tags",
    "http_post_json",
    "post_json_cancellable",
]
