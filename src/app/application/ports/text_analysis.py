from collections.abc import Callable
from typing import Protocol


class TextAnalysisProvider(Protocol):
    """Local or cloud text analysis over an existing transcript."""

    def summarize(
        self, transcript: str, language: str, on_progress: Callable[[str], None]
    ) -> str: ...

    def extract_highlights(
        self, srt_content: str, language: str, on_progress: Callable[[str], None]
    ) -> str: ...
