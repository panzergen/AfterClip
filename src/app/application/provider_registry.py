"""Provider registry (Phase 4 WS-A).

One place maps a provider id to its label, endpoint, credential name and
adapter kind, so adding a provider is a registry entry plus one adapter instead
of another hard-coded branch in ``providers.py``.
"""

from dataclasses import dataclass

from app.infrastructure.gemini.client import DEFAULT_GEMINI_URL, GEMINI_KEY_NAME

OLLAMA_BASE_URL = "http://localhost:11434"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENCODE_GO_BASE_URL = "https://opencode.ai/zen/go/v1"

OPENROUTER_KEY_NAME = "openrouter_api_key"
OPENCODE_GO_KEY_NAME = "opencode_go_api_key"

#: Adapter kinds understood by ``application.providers``.
KIND_OLLAMA = "ollama"
KIND_GEMINI = "gemini"
KIND_OPENAI_COMPAT = "openai_compat"


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    label: str
    kind: str
    base_url: str
    key_name: str = ""
    models_path: str = "/models"
    #: When live capability metadata is unavailable, assume all models can see.
    vision_default: bool = False

    @property
    def is_cloud(self) -> bool:
        return self.kind in {KIND_GEMINI, KIND_OPENAI_COMPAT}


PROVIDERS: dict[str, ProviderSpec] = {
    "ollama": ProviderSpec(
        id="ollama",
        label="Ollama (local)",
        kind=KIND_OLLAMA,
        base_url=OLLAMA_BASE_URL,
        models_path="/api/tags",
        vision_default=True,
    ),
    "gemini": ProviderSpec(
        id="gemini",
        label="Gemini (cloud)",
        kind=KIND_GEMINI,
        base_url=DEFAULT_GEMINI_URL,
        key_name=GEMINI_KEY_NAME,
    ),
    "openrouter": ProviderSpec(
        id="openrouter",
        label="OpenRouter (cloud)",
        kind=KIND_OPENAI_COMPAT,
        base_url=OPENROUTER_BASE_URL,
        key_name=OPENROUTER_KEY_NAME,
    ),
    "opencode_go": ProviderSpec(
        id="opencode_go",
        label="OpenCode Go (cloud)",
        kind=KIND_OPENAI_COMPAT,
        base_url=OPENCODE_GO_BASE_URL,
        key_name=OPENCODE_GO_KEY_NAME,
    ),
}


def get_provider(provider_id: str | None) -> ProviderSpec | None:
    return PROVIDERS.get(provider_id or "")


def is_cloud(provider_id: str | None) -> bool:
    spec = get_provider(provider_id)
    return bool(spec and spec.is_cloud)


def cloud_provider_ids() -> tuple[str, ...]:
    return tuple(provider_id for provider_id, spec in PROVIDERS.items() if spec.is_cloud)
