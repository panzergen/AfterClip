"""Backward-compatible prompt constants.

Phase 4 WS-B moved prompts into :mod:`app.domain.prompts`, where providers
receive a resolved ``PromptSet``. These module constants remain for callers
that still import them directly.
"""

from app.domain.prompts import DEFAULT_PROMPTS

PROMPT_SUMMARY = DEFAULT_PROMPTS["summary"]
PROMPT_SUMMARY_COMBINE = DEFAULT_PROMPTS["summary_combine"]
PROMPT_HIGHLIGHTS = DEFAULT_PROMPTS["highlights"]
PROMPT_VISION_FRAME = DEFAULT_PROMPTS["vision_frame"]

__all__ = [
    "PROMPT_HIGHLIGHTS",
    "PROMPT_SUMMARY",
    "PROMPT_SUMMARY_COMBINE",
    "PROMPT_VISION_FRAME",
]
