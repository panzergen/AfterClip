from collections.abc import Callable
from pathlib import Path

from app.application.cancellation import CancelToken
from app.domain.prompts import PromptSet
from app.infrastructure.ollama.client import OllamaClient


class OllamaVisionProvider:
    """Single-frame vision analysis; frames are sent as base64 images."""

    def __init__(
        self,
        model: str,
        client: OllamaClient | None = None,
        prompts: PromptSet | None = None,
    ):
        self.model = model
        self.client = client or OllamaClient()
        self.prompts = prompts or PromptSet()

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
            self.prompts.render(
                "vision_frame", user_desc=user_task, audio_context=audio_context, lang=language or "en"
            ),
            cancel_token,
            on_progress,
            images=(image_path,),
        )
