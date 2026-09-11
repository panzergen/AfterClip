import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from app.application.cancellation import CancelToken, ProcessingCancelled, wait_for_cancellation
from app.domain.models import CloudUsage
from app.infrastructure.gemini.permissions import assert_not_video_file, inline_data_part
from app.infrastructure.llm.transport import clean_thinking_tags, post_json_cancellable
from app.infrastructure.logging_filter import SECRET_REDACTOR
from app.infrastructure.secrets import KeyringSecretStore

LOGGER = logging.getLogger(__name__)

DEFAULT_GEMINI_URL = "https://generativelanguage.googleapis.com"
DEFAULT_GEMINI_MODEL = "gemini-flash-latest"
GEMINI_KEY_NAME = "gemini_api_key"
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class GeminiError(RuntimeError):
    """Gemini request failure; `retryable` marks transient errors (T21)."""

    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class GeminiKeyMissing(RuntimeError):
    """Raised when no Gemini API key is stored (T20)."""


def _error_is_retryable(error: BaseException) -> bool:
    import urllib.error

    if isinstance(error, urllib.error.HTTPError):
        return error.code in RETRYABLE_STATUS_CODES
    return isinstance(error, OSError)  # network/socket issues; HTTPError is an OSError subclass


def _http_post_with_status(url: str, payload: dict, timeout: float) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def extract_text(response: dict) -> str:
    for candidate in response.get("candidates", []):
        parts = candidate.get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts if isinstance(part, dict) and "text" in part)
        if text.strip():
            return clean_thinking_tags(text.strip())
    reason = next((candidate.get("finishReason", "unknown") for candidate in response.get("candidates", [])), "no candidates")
    raise GeminiError(f"Gemini returned no text (finishReason: {reason})")


class GeminiClient:
    """Cancellable Gemini REST client with bounded retry/backoff (T21).

    Requests are throttled to `min_interval` seconds apart so a burst of
    chunks/frames does not trip the free-tier rate limit (T21).
    """

    def __init__(
        self,
        model: str = DEFAULT_GEMINI_MODEL,
        base_url: str = DEFAULT_GEMINI_URL,
        timeout: float = 120.0,
        max_retries: int = 3,
        min_interval: float = 4.0,
        key_getter: Callable[[], str | None] | None = None,
        request_fn: Callable[[str, dict, float], dict] | None = None,
        sleep_fn: Callable[[float], None] | None = None,
        clock_fn: Callable[[], float] | None = None,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.min_interval = min_interval
        self.key_getter = key_getter or (lambda: KeyringSecretStore().get(GEMINI_KEY_NAME))
        self.request_fn = request_fn or _http_post_with_status
        self.sleep_fn = sleep_fn or time.sleep
        self.clock_fn = clock_fn or time.monotonic
        self._last_request_time: float | None = None
        self.usage = CloudUsage(provider="gemini", model=model)

    def _accumulate_usage(self, response: dict, parts: list[dict]) -> None:
        usage = (response.get("usageMetadata") or {}) if isinstance(response, dict) else {}
        images = sum(
            1
            for part in parts
            if isinstance(part, dict) and ("inline_data" in part or "inlineData" in part)
        )
        self.usage = self.usage.merged(
            CloudUsage(
                provider="gemini",
                model=self.model,
                requests=1,
                input_tokens=int(usage.get("promptTokenCount") or 0),
                output_tokens=int(usage.get("candidatesTokenCount") or 0),
                images=images,
            )
        )

    def generate(self, parts: list[dict], cancel_token: CancelToken | None = None) -> str:
        key = self.key_getter()
        if not key:
            raise GeminiKeyMissing("No Gemini API key is stored. Add one in Settings; it is kept in the OS credential manager.")
        SECRET_REDACTOR.register(key)
        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 4096},
        }
        url = f"{self.base_url}/v1beta/models/{self.model}:generateContent?key={key}"
        for attempt in range(self.max_retries + 1):
            self._throttle(cancel_token)
            try:
                raw = post_json_cancellable(
                    url, payload, self.timeout, cancel_token, self.request_fn
                )
                self._accumulate_usage(raw, parts)
                result = extract_text(raw)
                self._last_request_time = self.clock_fn()
                return result
            except ProcessingCancelled:
                raise
            except GeminiError:
                raise
            except urllib.error.HTTPError as error:
                if error.code == 404:
                    raise GeminiError(
                        f"Gemini model '{self.model}' was not found (404). Open Settings and pick a valid model.",
                        retryable=False,
                    ) from error
                if attempt >= self.max_retries or not _error_is_retryable(error):
                    raise GeminiError(f"Gemini request failed: HTTP {error.code}", retryable=False) from error
                delay = self._backoff(error.code, attempt)
                LOGGER.warning("Gemini request attempt %d failed (HTTP %d); retrying in %.1fs", attempt + 1, error.code, delay)
                self._sleep_interruptible(delay, cancel_token)
            except Exception as error:
                if attempt >= self.max_retries or not _error_is_retryable(error):
                    raise GeminiError(f"Gemini request failed: {error}", retryable=False) from error
                delay = self._backoff(0, attempt)
                LOGGER.warning("Gemini request attempt %d failed (%s); retrying in %.1fs", attempt + 1, error, delay)
                self._sleep_interruptible(delay, cancel_token)

    def _throttle(self, cancel_token: CancelToken | None) -> None:
        if self._last_request_time is None:
            return
        elapsed = self.clock_fn() - self._last_request_time
        remaining = self.min_interval - elapsed
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

    def list_models(self) -> tuple[str, ...]:
        """Generate-capable model names from the live API (Settings 'Load models')."""
        key = self.key_getter()
        if not key:
            raise GeminiKeyMissing("No Gemini API key is stored. Add one in Settings; it is kept in the OS credential manager.")
        request = urllib.request.Request(f"{self.base_url}/v1beta/models?key={key}&pageSize=1000")
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
        models = data.get("models", [])
        return tuple(
            model["name"].split("/")[-1]
            for model in models
            if "generateContent" in model.get("supportedGenerationMethods", [])
        )

    def image_part(self, image_path) -> dict:
        path = Path(image_path)
        assert_not_video_file(path)
        return inline_data_part("image/png", path.read_bytes())
