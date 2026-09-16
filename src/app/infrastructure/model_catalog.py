"""Cross-provider model catalog with capability filtering.

Providers (Ollama local, Gemini cloud, later OpenRouter) contribute sections
of `ModelEntry` items; the UI renders each section as a disabled group header
with its models underneath. A model available in several providers simply
appears under each section.
"""
import json
import logging
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

LOGGER = logging.getLogger(__name__)

OLLAMA_VISION_HINTS = ("vision", "llava", "minicpm", "bakllava", "moondream", "-vl")
GEMINI_NON_TEXT_HINTS = ("tts", "embedding", "aqa")
GEMINI_STATIC_MODELS = ("gemini-flash-latest", "gemini-2.5-flash", "gemini-2.5-pro")


@dataclass(frozen=True)
class ModelEntry:
    provider: str  # "ollama" | "gemini" | later "openrouter"
    name: str
    text_capable: bool = True
    vision_capable: bool = False


@dataclass(frozen=True)
class ModelSection:
    title: str
    provider: str
    entries: tuple[ModelEntry, ...]


def _ollama_heuristic_vision(name: str) -> bool:
    lowered = name.lower()
    return any(hint in lowered for hint in OLLAMA_VISION_HINTS)


def ollama_section(
    base_url: str = "http://localhost:11434",
    timeout: float = 5.0,
    tags_fn: Callable | None = None,
    show_fn: Callable | None = None,
) -> ModelSection | None:
    """Live Ollama section; vision capability via /api/show with name fallback."""
    import urllib.error

    def default_tags():
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8")).get("models", [])

    def default_show(name: str):
        request = urllib.request.Request(
            f"{base_url}/api/show",
            data=json.dumps({"model": name}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    tags_fn = tags_fn or default_tags
    show_fn = show_fn or default_show
    try:
        models = tags_fn()
    except Exception as error:
        LOGGER.info("Ollama model list unavailable: %s", error)
        return None
    entries = []
    for model in models:
        name = model.get("name") or model.get("model")
        if not name:
            continue
        vision = False
        try:
            capabilities = show_fn(name).get("capabilities", [])
            vision = "vision" in capabilities
        except Exception:
            vision = _ollama_heuristic_vision(name)
        entries.append(ModelEntry("ollama", name, text_capable=True, vision_capable=vision))
    if not entries:
        return None
    return ModelSection("Ollama (local)", "ollama", tuple(entries))


def gemini_section(key_getter, list_models_fn=None) -> ModelSection | None:
    """Live Gemini section; falls back to the static list when the API is unreachable."""
    from app.infrastructure.gemini.client import GeminiClient, GeminiKeyMissing

    try:
        names = (list_models_fn or (lambda: GeminiClient(key_getter=key_getter).list_models()))()
    except GeminiKeyMissing:
        return None
    except Exception as error:
        LOGGER.info("Gemini model list unavailable (%s); using static list", error)
        names = None
    if not names:
        names = GEMINI_STATIC_MODELS
    entries = tuple(
        ModelEntry(
            "gemini",
            name,
            text_capable=not any(hint in name.lower() for hint in GEMINI_NON_TEXT_HINTS),
            vision_capable=not any(hint in name.lower() for hint in GEMINI_NON_TEXT_HINTS),
        )
        for name in names
    )
    return ModelSection("Gemini (cloud API)", "gemini", entries)


def openai_compat_section(spec, key_getter, list_fn=None) -> ModelSection | None:
    """Live section for an OpenAI-compatible provider (OpenRouter, OpenCode Go).

    Vision capability is gated per model from live metadata, falling back to
    conservative name hints and the provider default - never assumed from the
    endpoint being compatible.
    """
    from app.infrastructure.openai_compat import (
        OpenAICompatClient,
        OpenAICompatKeyError,
        infer_vision_capable,
    )

    if list_fn is None:

        def list_fn():
            client = OpenAICompatClient(
                model="", base_url=spec.base_url, provider=spec.id, key_getter=key_getter
            )
            return client.list_models_raw()

    try:
        items = list_fn()
    except OpenAICompatKeyError:
        return None
    except Exception as error:
        LOGGER.info("%s model list unavailable: %s", spec.label, error)
        return None
    entries = []
    for item in items or []:
        name = str(item.get("id") or "")
        if not name:
            continue
        vision = infer_vision_capable(item) or (
            spec.vision_default and _ollama_heuristic_vision(name)
        )
        entries.append(ModelEntry(spec.id, name, text_capable=True, vision_capable=vision))
    if not entries:
        return None
    return ModelSection(spec.label, spec.id, tuple(entries))


def collect_catalog(
    ollama_reachable: bool,
    cloud_keys: dict[str, str | None] | None = None,
    ollama_base_url: str = "http://localhost:11434",
) -> tuple[ModelSection, ...]:
    """Sections currently available: live Ollama and any provider with a key.

    ``cloud_keys`` maps provider id -> stored key (None/missing = no section).
    """
    from app.application.provider_registry import (
        KIND_GEMINI,
        cloud_provider_ids,
        get_provider,
    )

    sections = []
    if ollama_reachable:
        section = ollama_section(base_url=ollama_base_url)
        if section:
            sections.append(section)
    keys = cloud_keys or {}
    for provider_id in cloud_provider_ids():
        key = keys.get(provider_id)
        if not key:
            continue
        spec = get_provider(provider_id)
        if spec is None:
            continue
        if spec.kind == KIND_GEMINI:
            section = gemini_section(key_getter=lambda stored=key: stored)
        else:
            section = openai_compat_section(spec, key_getter=lambda stored=key: stored)
        if section:
            sections.append(section)
    return tuple(sections)
