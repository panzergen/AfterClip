# Cloud Providers

Phase 4 (WS-A) makes AI providers pluggable through a single registry and a
shared OpenAI-compatible adapter.

| Provider | Id | Kind | Endpoint | Key name |
| --- | --- | --- | --- | --- |
| Ollama (local) | `ollama` | local | `http://localhost:11434` | — |
| Gemini (cloud) | `gemini` | gemini | `generativelanguage.googleapis.com` | `gemini_api_key` |
| OpenRouter (cloud) | `openrouter` | openai_compat | `https://openrouter.ai/api/v1` | `openrouter_api_key` |
| OpenCode Go (cloud) | `opencode_go` | openai_compat | `https://opencode.ai/zen/go/v1` | `opencode_go_api_key` |

`application/provider_registry.py` is the source of truth (label, base URL,
credential name, endpoint, kind). Adding a provider is a registry entry plus an
adapter — no new branch in the application layer.

## Configuring

1. **Settings → Cloud provider** — choose the provider.
2. Paste its API key and **Save key** (stored in the OS credential manager).
3. **Load models** to fetch the live model list.
4. **Grant consent** before the first cloud job (also asked in a pre-job dialog).

Model dropdowns in the Advanced panel are grouped per provider. Vision options
are gated per model: a model is only offered for vision when its metadata (or a
conservative name hint) says it accepts images. OpenCode Go is coding-focused,
so vision is the exception rather than the rule.

## What is sent

Every cloud provider routes through `infrastructure/cloud_policy.py`:

- **Text analysis:** transcript text only.
- **Vision analysis:** single frame images (`image/png`/`image/jpeg`).

Video files are refused before any request is built, for all providers. Audio
chunks are allowed by the policy but not currently used.

## Retry and cancellation

The OpenAI-compatible client reuses the same bounded retry/backoff pattern as
Gemini: `401/403` fail immediately (bad key), `404` reports an unknown model,
and `429`/`5xx`/network errors are retried with exponential backoff up to a cap.
Requests are cancellable.

## Deferred

OpenCode Go serves a subset of models (MiniMax / Qwen) over an
Anthropic-compatible `/v1/messages` endpoint. That adapter is **not**
implemented; only the OpenAI-compatible `/chat/completions` models are
supported for now.
