import base64
import logging
import subprocess
from collections.abc import Callable
from pathlib import Path

from app.application.cancellation import ProcessingCancelled, wait_for_cancellation
from app.infrastructure.llm.transport import clean_thinking_tags, http_post_json, post_json_cancellable
from app.infrastructure.process import CREATE_NEW_PROCESS_GROUP, CREATE_NO_WINDOW, ProcessRunner, terminate_process_tree

LOGGER = logging.getLogger(__name__)

DEFAULT_OLLAMA_URL = "http://localhost:11434"


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
            "options": {"temperature": 0.2, "num_predict": 1200},
        }
        encoded_images = []
        for image in images:
            try:
                encoded_images.append(base64.b64encode(Path(image).read_bytes()).decode("utf-8"))
            except OSError as error:
                LOGGER.error("Failed to read image %s: %s", image, error)
        if encoded_images:
            payload["images"] = encoded_images
        try:
            response = post_json_cancellable(
                f"{self.base_url}/api/generate", payload, self.timeout, cancel_token, self.request_fn
            )
            if response.get("thinking"):
                LOGGER.info("Discarded separate Ollama thinking field.")
            return clean_thinking_tags(response.get("response", "").strip())
        except ProcessingCancelled:
            raise
        except Exception as error:
            LOGGER.warning("Ollama API call failed, falling back to CLI: %s", error)
            return self._run_cli(model, prompt, cancel_token)

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
        try:
            while process.poll() is None:
                if wait_for_cancellation(cancel_token, 0.1):
                    terminate_process_tree(process)
                    process.wait()
                    raise ProcessingCancelled
        finally:
            stdout_data, stderr_data = process.communicate()
        if process.returncode != 0:
            raise OllamaError(f"Ollama CLI returned exit code {process.returncode}: {(stderr_data or '').strip()}")
        return clean_thinking_tags(stdout_data)
