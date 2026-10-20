import json
import logging
import urllib.request

from app.infrastructure.ollama.client import DEFAULT_OLLAMA_URL

LOGGER = logging.getLogger(__name__)


def check_ollama_service(base_url: str = DEFAULT_OLLAMA_URL, timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(f"{base_url.rstrip('/')}/api/tags", timeout=timeout):
            return True
    except Exception:
        return False


def list_ollama_models(base_url: str = DEFAULT_OLLAMA_URL, timeout: float = 3.0) -> tuple[str, ...]:
    try:
        with urllib.request.urlopen(
            f"{base_url.rstrip('/')}/api/tags", timeout=timeout
        ) as response:
            models = json.loads(response.read().decode("utf-8")).get("models", [])
            return tuple(model["name"] for model in models if model.get("name"))
    except Exception as error:
        LOGGER.warning("Could not fetch Ollama models: %s", error)
        return ()
