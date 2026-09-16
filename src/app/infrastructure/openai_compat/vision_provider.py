import logging
from collections.abc import Callable
from pathlib import Path

from app.application.cancellation import CancelToken
from app.domain.prompts import PromptSet
from app.infrastructure.openai_compat.client import (
    DEFAULT_OPENAI_COMPAT_BASE_URL,
    OpenAICompatClient,
)

LOGGER = logging.getLogger(__name__)


class OpenAICompatVisionProvider:
    """Single-frame vision analysis; only image/* frames are ever sent."""

    def __init__(
        self,
        model: str,
        client: OpenAICompatClient | None = None,
        prompts: PromptSet | None = None,
        base_url: str = DEFAULT_OPENAI_COMPAT_BASE_URL,
        provider: str = "openai_compat",
        key_getter: Callable[[], str | None] | None = None,
    ):
        self.provider_name = provider
        self.model = model
        self.prompts = prompts or PromptSet()
        self.client = client or OpenAICompatClient(
            model=model, base_url=base_url, provider=provider, key_getter=key_getter
        )

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
            on_progress(f"{self.provider_name} vision is analyzing {Path(image_path).name}")
        prompt = self.prompts.render(
            "vision_frame",
            user_desc=user_task,
            audio_context=audio_context,
            lang=language or "en",
        )
        content = [{"type": "text", "text": prompt}, self.client.image_part(image_path)]
        return self.client.generate(content, cancel_token)
