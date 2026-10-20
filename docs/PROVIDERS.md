# Cloud Providers

Phase 4 (WS-A) makes AI providers pluggable through a single registry and a
shared OpenAI-compatible adapter.

| Provider | Id | Kind | Endpoint | Key name |
| --- | --- | --- | --- | --- |
| Ollama (local) | `ollama` | local | `http://localhost:11434` | — |
| Gemini (cloud) | `gemini` | gemini | `generativelanguage.googleapis.com` | `gemini_api_key` |
| OpenRouter (cloud) | `openrouter` | openai_compat | `https://openrouter.ai/api/v1` | `openrouter_api_key` |
| OpenCode Go (cloud) | `opencode_go` | openai_compat | `https://opencode.ai/zen/go/v1` | `opencode_go_api_key` |
| OpenCode Zen (cloud) | `opencode_zen` | openai_compat | `https://opencode.ai/zen/v1` | `opencode_go_api_key` (shared platform key) |

Zen and Go share one OpenCode platform key: saving it under either provider
unlocks both catalogs. Zen's `/models` endpoint also lists `/responses`,
`/messages`, `/systemone` and native-Google ids that this app cannot speak, so
those prefixes (`gpt-`, `claude-`, `gemini-`, `grok-`, `muse-spark-`, `jev-`,
`qwen3.5/3.6/3.7-`, `qwen3.8-flash`) are filtered out of the Zen section — only
`/chat/completions` models are offered (see `exclude_name_prefixes` in
`application/provider_registry.py`).

The model list is never hard-coded: every `openai_compat` provider uses the
live `GET {base_url}/models` response (Settings → Load models). Providers other
than Gemini have no static fallback, so an invalid model name is never offered.

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
Gemini: `401` fails immediately (bad key), `403`/`404` are reported without
retry, and `429`/`5xx`/network errors are retried with exponential backoff up to
a cap. Requests are cancellable. Error responses include the provider's message
body so failures are diagnosable.

## OpenCode Go client requirements

OpenCode Go monitors traffic and requires clients to identify themselves
(<https://opencode.ai/docs/go>):

- A client-specific **User-Agent** (`AfterClip/<version>`), not a raw HTTP
  library name — Python-urllib's default UA is blocked by Cloudflare with 403.
- A stable **`x-opencode-session`** id per conversation. Without it every
  request returns `HTTP 400 {"type":"MissingSessionID"}`.

Both are sent automatically for the `opencode_go` provider (a fresh session id
is generated per client, so each job's text and vision conversations are
distinct).

## Deferred

OpenCode Go serves a subset of models (MiniMax / Qwen) over an
Anthropic-compatible `/v1/messages` endpoint. That adapter is **not**
implemented; only the OpenAI-compatible `/chat/completions` models are
supported for now.
