import logging
from collections.abc import Callable

from app.application.cancellation import CancelToken
from app.infrastructure.gemini.client import DEFAULT_GEMINI_MODEL, GeminiClient, GeminiError, GeminiKeyMissing
from app.infrastructure.llm.prompts import PROMPT_HIGHLIGHTS, PROMPT_SUMMARY, PROMPT_SUMMARY_COMBINE
from app.infrastructure.llm.transport import chunk_text, clean_highlights_output

LOGGER = logging.getLogger(__name__)

CHUNK_SIZE = 3500

__all__ = ["CHUNK_SIZE", "GeminiError", "GeminiKeyMissing", "GeminiTextProvider"]


class GeminiTextProvider:
    """Summaries and timestamped highlights through the Gemini API (cloud)."""

    provider_name = "gemini"

    def __init__(
        self,
        model: str = DEFAULT_GEMINI_MODEL,
        client: GeminiClient | None = None,
        chunk_size: int = CHUNK_SIZE,
        key_getter: Callable[[], str | None] | None = None,
        request_fn=None,
        sleep_fn=None,
        min_interval: float = 4.0,
    ):
        self.model = model
        self.chunk_size = chunk_size
        self.client = client or GeminiClient(
            model=model,
            key_getter=key_getter,
            request_fn=request_fn,
            sleep_fn=sleep_fn,
            min_interval=min_interval,
        )

    def summarize(self, transcript: str, language: str, on_progress: Callable[[str], None] | None = None, cancel_token: CancelToken | None = None) -> str:
        chunks = chunk_text(transcript, self.chunk_size)
        if not chunks:
            raise GeminiError("Transcript was empty; nothing to summarize.")
        if len(chunks) == 1:
            if on_progress:
                on_progress("Gemini is summarizing the transcript")
            return self.client.generate([{"text": PROMPT_SUMMARY.format(lang=language or "en", transcript=chunks[0])}], cancel_token)
        partials = []
        for index, chunk in enumerate(chunks, 1):
            if on_progress:
                on_progress(f"Gemini is summarizing section {index}/{len(chunks)}")
            partials.append(
                self.client.generate([{"text": PROMPT_SUMMARY.format(lang=language or "en", transcript=chunk)}], cancel_token)
            )
        if on_progress:
            on_progress("Gemini is combining section summaries")
        return self.client.generate(
            [{"text": PROMPT_SUMMARY_COMBINE.format(lang=language or "en", summaries="\n\n".join(partials))}],
            cancel_token,
        )

    def extract_highlights(self, srt_content: str, language: str, on_progress: Callable[[str], None] | None = None, cancel_token: CancelToken | None = None) -> str:
        chunks = chunk_text(srt_content, self.chunk_size)
        if not chunks:
            raise GeminiError("Subtitle content was empty; no highlights can be extracted.")
        sections = []
        for index, chunk in enumerate(chunks, 1):
            if on_progress:
                on_progress(f"Gemini is extracting highlights section {index}/{len(chunks)}")
            try:
                sections.append(
                    self.client.generate([{"text": PROMPT_HIGHLIGHTS.format(lang=language or "en", srt_content=chunk)}], cancel_token)
                )
            except GeminiError as error:
                LOGGER.error("Highlights section %d/%d failed: %s", index, len(chunks), error)
        if not sections:
            raise GeminiError("Highlights failed for all sections.")
        return clean_highlights_output("\n".join(sections))
