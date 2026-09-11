import logging
from collections.abc import Callable
from pathlib import Path

from app.application.cancellation import CancelToken
from app.infrastructure.gemini.client import DEFAULT_GEMINI_MODEL, GeminiClient
from app.infrastructure.llm.prompts import PROMPT_VISION_FRAME

LOGGER = logging.getLogger(__name__)


class GeminiVisionProvider:
    """Single-frame vision analysis; only image/png frames are ever sent."""

    provider_name = "gemini"

    def __init__(self, model: str = DEFAULT_GEMINI_MODEL, client: GeminiClient | None = None):
        self.model = model
        self.client = client or GeminiClient(model=model)

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
            on_progress(f"Gemini vision is analyzing {Path(image_path).name}")
        prompt = PROMPT_VISION_FRAME.format(user_desc=user_task, audio_context=audio_context, lang=language or "en")
        parts = [{"text": prompt}, self.client.image_part(image_path)]
        return self.client.generate(parts, cancel_token)
