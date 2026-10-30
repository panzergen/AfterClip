import base64
import logging
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from app.application.cancellation import ProcessingCancelled, wait_for_cancellation
from app.infrastructure.llm.transport import (
    clean_thinking_tags,
    http_post_json,
    post_json_cancellable,
)
from app.infrastructure.process import (
    CREATE_NEW_PROCESS_GROUP,
    CREATE_NO_WINDOW,
    ProcessRunner,
    terminate_process_tree,
)

LOGGER = logging.getLogger(__name__)

DEFAULT_OLLAMA_URL = "http://localhost:11434"
#: The CLI fallback is a last resort; never let a stuck `ollama run` hang a job.
CLI_TIMEOUT_SECONDS = 600


class OllamaError(RuntimeError):
    """Raised when Ollama API and CLI fallback both fail."""


class OllamaClient:
    """Ollama HTTP API client with a CLI fallback, both cancellable."""

    def __init__(
        self,
        base_url: str = DEFAULT_OLLAMA_URL,
        timeout: float = 120.0,
        request_fn: Callable[[str, dict, float], dict] | None = None,
        runner: ProcessRunner | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.request_fn = request_fn or http_post_json
        self.runner = runner or ProcessRunner()

    def generate(
        self,
        model: str,
        prompt: str,
        cancel_token=None,
        on_progress: Callable[[str], None] | None = None,
        images: tuple[Path, ...] = (),
    ) -> str:
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            # Long slide-by-slide reports need more than the old 1200-token cap;
            # this is an upper bound, not a target, so short answers still stop
            # at their natural end.
            "options": {"temperature": 0.2, "num_predict": 4096},
        }
        encoded_images = []
        for image in images:
            try:
                encoded_images.append(base64.b64encode(Path(image).read_bytes()).decode("utf-8"))
            except OSError as error:
                LOGGER.error("Failed to read image %s: %s", image, error)
        if encoded_images:
            payload["images"] = encoded_images
        def post() -> dict:
            return post_json_cancellable(
                f"{self.base_url}/api/generate",
                payload,
                self.timeout,
                cancel_token,
                self.request_fn,
            )

        try:
            response = post()
        except ProcessingCancelled:
            raise
        except Exception as error:
            if images:
                # The CLI fallback cannot carry an image, so it would answer
                # without looking at the frame. Retry the HTTP call once and
                # fail clearly instead of spending a 600-second CLI timeout.
                LOGGER.warning("Ollama vision request failed; retrying once: %s", error)
                try:
                    response = post()
                except ProcessingCancelled:
                    raise
                except Exception as retry_error:
                    raise OllamaError(
                        f"Ollama vision request failed: {retry_error}"
                    ) from retry_error
            else:
                LOGGER.warning("Ollama API call failed, falling back to CLI: %s", error)
                return self._run_cli(model, prompt, cancel_token)
        if response.get("thinking"):
            LOGGER.info("Discarded separate Ollama thinking field.")
        return clean_thinking_tags(response.get("response", "").strip())

    def _run_cli(self, model: str, prompt: str, cancel_token) -> str:
        command = ["ollama", "run", model, "--think=false", prompt]
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP,
        )
        deadline = time.monotonic() + CLI_TIMEOUT_SECONDS
        try:
            while process.poll() is None:
                if wait_for_cancellation(cancel_token, 0.1):
                    terminate_process_tree(process)
                    process.wait()
                    raise ProcessingCancelled
                if time.monotonic() >= deadline:
                    terminate_process_tree(process)
                    process.wait()
                    raise OllamaError(
                        f"Ollama CLI timed out after {CLI_TIMEOUT_SECONDS} seconds"
                    )
        finally:
            stdout_data, stderr_data = process.communicate()
        if process.returncode != 0:
            raise OllamaError(
                f"Ollama CLI returned exit code {process.returncode}: {(stderr_data or '').strip()}"
            )
        return clean_thinking_tags(stdout_data)
