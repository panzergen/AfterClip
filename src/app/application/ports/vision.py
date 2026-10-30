from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from app.application.cancellation import CancelToken


class VisionProvider(Protocol):
    """Frame image analysis; only single frames are ever sent, never video."""

    def analyze_frame(
        self,
        image_path: Path,
        audio_context: str,
        user_task: str,
        language: str,
        on_progress: Callable[[str], None],
        cancel_token: CancelToken,
        prompt: str | None = None,
    ) -> str: ...
