"""Vision capability hints for OpenAI-compatible models.

OpenAI-compatible servers advertise capability differently (or not at all), so
vision is never assumed from endpoint compatibility: prefer live metadata, then
fall back to conservative name hints.
"""

VISION_NAME_HINTS = (
    "vision",
    "-vl",
    "vl-",
    "llava",
    "gemini",
    "gpt-4o",
    "gpt-4.1",
    "claude-3",
    "claude-4",
    "pixtral",
    "qwen-vl",
    "qwen2-vl",
    "qwen2.5-vl",
    "qwen3-vl",
    "qwen3.8",
    "gemma",
    "deepseek",
    "mimo",
    "internvl",
    "minicpm-v",
    "moondream",
)


def infer_vision_capable(item: dict) -> bool:
    """True when a ``/models`` item can accept images."""
    architecture = item.get("architecture") if isinstance(item.get("architecture"), dict) else {}
    modalities = architecture.get("input_modalities")
    if isinstance(modalities, list):
        return any(str(modality).lower() == "image" for modality in modalities)
    name = str(item.get("id", "")).lower()
    return any(hint in name for hint in VISION_NAME_HINTS)
