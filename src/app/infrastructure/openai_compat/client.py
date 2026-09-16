"""OpenAI-compatible chat-completions adapter (Phase 4 WS-A).

Shared by OpenRouter and OpenCode Go: bearer auth, cancellable requests, bounded
retry/backoff and usage accumulation. Vision is opt-in per model because
OpenAI-compatible servers differ in image support.
"""

import base64
import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from app.application.cancellation import CancelToken, ProcessingCancelled, wait_for_cancellation
from app.domain.models import CloudUsage
from app.infrastructure.cloud_policy import assert_not_video_file
from app.infrastructure.llm.transport import (
    clean_thinking_tags,
    http_post_json,
    post_json_cancellable,
)
from app.infrastructure.logging_filter import SECRET_REDACTOR
from app.infrastructure.secrets import KeyringSecretStore

LOGGER = logging.getLogger(__name__)

DEFAULT_OPENAI_COMPAT_BASE_URL = "https://openrouter.ai/api/v1"
RETRYABLE_STATUS_CODES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
_MIME_BY_SUFFIX = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


class OpenAICompatError(RuntimeError):
    """OpenAI-compatible request failure; ``retryable`` marks transient errors."""

    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class OpenAICompatKeyError(RuntimeError):
    """Raised when no API key is stored for the provider."""


def _error_is_retryable(error: BaseException) -> bool:
    if isinstance(error, urllib.error.HTTPError):
        return error.code in RETRYABLE_STATUS_CODES
    return isinstance(error, OSError)


def extract_text(response: dict) -> str:
    choices = response.get("choices") if isinstance(response, dict) else None
    if not choices:
        raise OpenAICompatError("The provider returned no choices.")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        text = "".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") in (None, "text")
        )
    else:
        text = str(content or "")
    text = clean_thinking_tags(text)
    if not text.strip():
        finish = choices[0].get("finish_reason", "unknown")
        raise OpenAICompatError(f"The provider returned no text (finish_reason: {finish}).")
    return text


class OpenAICompatClient:
    """Cancellable ``/chat/completions`` client with bounded retry/backoff."""

    def __init__(
        self,
        model: str,
        base_url: str = DEFAULT_OPENAI_COMPAT_BASE_URL,
        provider: str = "openai_compat",
        timeout: float = 120.0,
        max_retries: int = 3,
        min_interval: float = 1.0,
        key_getter: Callable[[], str | None] | None = None,
        transport_fn: Callable[[str, dict, float, dict], dict] | None = None,
        sleep_fn: Callable[[float], None] | None = None,
        clock_fn: Callable[[], float] | None = None,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.provider = provider
        self.timeout = timeout
        self.max_retries = max_retries
        self.min_interval = min_interval
        self.key_getter = key_getter or (
            lambda: KeyringSecretStore().get(f"{provider}_api_key")
        )
        self.transport_fn = transport_fn or http_post_json
        self.sleep_fn = sleep_fn or time.sleep
        self.clock_fn = clock_fn or time.monotonic
        self._last_request_time: float | None = None
        self.usage = CloudUsage(provider=provider, model=model)

    def _accumulate_usage(self, response: dict, content: list[dict]) -> None:
        usage = (response.get("usage") or {}) if isinstance(response, dict) else {}
        images = sum(
            1 for part in content if isinstance(part, dict) and part.get("type") == "image_url"
        )
        self.usage = self.usage.merged(
            CloudUsage(
                provider=self.provider,
                model=self.model,
                requests=1,
                input_tokens=int(usage.get("prompt_tokens") or 0),
                output_tokens=int(usage.get("completion_tokens") or 0),
                images=images,
            )
        )

    def generate(self, content: list[dict], cancel_token: CancelToken | None = None) -> str:
        key = self.key_getter()
        if not key:
            raise OpenAICompatKeyError(
                f"No {self.provider} API key is stored. Add one in Settings to use this provider."
            )
        SECRET_REDACTOR.register(key)
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0.2,
        }
        url = f"{self.base_url}/chat/completions"

        def request(url_: str, payload_: dict, timeout_: float) -> dict:
            return self.transport_fn(url_, payload_, timeout_, headers)

        for attempt in range(self.max_retries + 1):
            self._throttle(cancel_token)
            try:
                raw = post_json_cancellable(url, payload, self.timeout, cancel_token, request)
                self._accumulate_usage(raw, content)
                result = extract_text(raw)
                self._last_request_time = self.clock_fn()
                return result
            except ProcessingCancelled:
                raise
            except OpenAICompatError:
                raise
            except urllib.error.HTTPError as error:
                if error.code in (401, 403):
                    raise OpenAICompatError(
                        f"{self.provider} rejected the API key (HTTP {error.code}).",
                        retryable=False,
                    ) from error
                if error.code == 404:
                    raise OpenAICompatError(
                        f"{self.provider} model '{self.model}' was not found (404).",
                        retryable=False,
                    ) from error
                if attempt >= self.max_retries or not _error_is_retryable(error):
                    raise OpenAICompatError(
                        f"{self.provider} request failed: HTTP {error.code}"
                    ) from error
                delay = self._backoff(error.code, attempt)
                LOGGER.warning(
                    "%s attempt %d failed (HTTP %d); retrying in %.1fs",
                    self.provider,
                    attempt + 1,
                    error.code,
                    delay,
                )
                self._sleep_interruptible(delay, cancel_token)
            except Exception as error:
                if attempt >= self.max_retries or not _error_is_retryable(error):
                    raise OpenAICompatError(f"{self.provider} request failed: {error}") from error
                delay = self._backoff(0, attempt)
                self._sleep_interruptible(delay, cancel_token)

    def _throttle(self, cancel_token: CancelToken | None) -> None:
        if self._last_request_time is None:
            return
        remaining = self.min_interval - (self.clock_fn() - self._last_request_time)
        if remaining > 0:
            self._sleep_interruptible(remaining, cancel_token)

    @staticmethod
    def _backoff(status_code: int, attempt: int) -> float:
        base = 8.0 if status_code == 429 else 2.0
        return min(60.0, base * (2**attempt))

    def _sleep_interruptible(self, delay: float, cancel_token: CancelToken | None) -> None:
        if cancel_token is None:
            self.sleep_fn(delay)
        elif wait_for_cancellation(cancel_token, delay):
            raise ProcessingCancelled

    def list_models_raw(self) -> list[dict]:
        """Raw ``/models`` items (id + capability metadata where provided)."""
        key = self.key_getter()
        if not key:
            raise OpenAICompatKeyError(f"No {self.provider} API key is stored.")
        request = urllib.request.Request(
            f"{self.base_url}/models", headers={"Authorization": f"Bearer {key}"}
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
        items = data.get("data", []) if isinstance(data, dict) else []
        return [item for item in items if isinstance(item, dict) and item.get("id")]

    def list_models(self) -> tuple[str, ...]:
        return tuple(str(item["id"]) for item in self.list_models_raw())

    def image_part(self, image_path) -> dict:
        path = Path(image_path)
        assert_not_video_file(path)
        mime = _MIME_BY_SUFFIX.get(path.suffix.lower(), "image/png")
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}}
