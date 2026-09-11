from collections.abc import Callable
from pathlib import Path

from app.application.cancellation import CancelToken
from app.infrastructure.ollama.client import OllamaClient
from app.infrastructure.ollama.prompts import PROMPT_VISION_FRAME


class OllamaVisionProvider:
    """Single-frame vision analysis; frames are sent as base64 images."""

    def __init__(self, model: str, client: OllamaClient | None = None):
        self.model = model
        self.client = client or OllamaClient()

    def analyze_frame(
        self,
        image_path: Path,
        audio_context: str,
        user_task: str,
        language: str,
        on_progress: Callable[[str], None] | None = None,
        cancel_token: CancelToken | None = None,
    ) -> str:
        if on_progress:
            on_progress(f"Ollama vision is analyzing {Path(image_path).name}")
        return self.client.generate(
            self.model,
            PROMPT_VISION_FRAME.format(user_desc=user_task, audio_context=audio_context, lang=language or "en"),
            cancel_token,
            on_progress,
            images=(image_path,),
        )
