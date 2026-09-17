import logging
from collections.abc import Callable

from app.application.cancellation import CancelToken
from app.domain.prompts import PromptSet
from app.infrastructure.llm.transport import chunk_text, clean_highlights_output
from app.infrastructure.openai_compat.client import (
    DEFAULT_OPENAI_COMPAT_BASE_URL,
    OpenAICompatClient,
    OpenAICompatError,
)

LOGGER = logging.getLogger(__name__)

CHUNK_SIZE = 3500

__all__ = ["CHUNK_SIZE", "OpenAICompatError", "OpenAICompatTextProvider"]


class OpenAICompatTextProvider:
    """Summaries and timestamped highlights through an OpenAI-compatible API."""

    def __init__(
        self,
        model: str,
        client: OpenAICompatClient | None = None,
        chunk_size: int = CHUNK_SIZE,
        prompts: PromptSet | None = None,
        base_url: str = DEFAULT_OPENAI_COMPAT_BASE_URL,
        provider: str = "openai_compat",
        key_getter: Callable[[], str | None] | None = None,
    ):
        self.provider_name = provider
        self.model = model
        self.chunk_size = chunk_size
        self.prompts = prompts or PromptSet()
        self.client = client or OpenAICompatClient(
            model=model, base_url=base_url, provider=provider, key_getter=key_getter
        )

    @staticmethod
    def _text(prompt: str) -> list[dict]:
        return [{"type": "text", "text": prompt}]

    def generate(self, prompt: str, cancel_token: CancelToken | None = None) -> str:
        """Single-prompt generation (used for topic titles and similar)."""
        return self.client.generate(self._text(prompt), cancel_token)

    def summarize(
        self,
        transcript: str,
        language: str,
        on_progress: Callable[[str], None] | None = None,
        cancel_token: CancelToken | None = None,
    ) -> str:
        chunks = chunk_text(transcript, self.chunk_size)
        if not chunks:
            raise OpenAICompatError("Transcript was empty; nothing to summarize.")
        if len(chunks) == 1:
            if on_progress:
                on_progress(f"{self.provider_name} is summarizing the transcript")
            prompt = self.prompts.render("summary", lang=language or "en", transcript=chunks[0])
            return self.client.generate(self._text(prompt), cancel_token)
        partials = []
        for index, chunk in enumerate(chunks, 1):
            if on_progress:
                on_progress(f"{self.provider_name} is summarizing section {index}/{len(chunks)}")
            prompt = self.prompts.render("summary", lang=language or "en", transcript=chunk)
            partials.append(self.client.generate(self._text(prompt), cancel_token))
        if on_progress:
            on_progress(f"{self.provider_name} is combining section summaries")
        return self.client.generate(
            self._text(
                self.prompts.render(
                    "summary_combine", lang=language or "en", summaries="\n\n".join(partials)
                )
            ),
            cancel_token,
        )

    def extract_highlights(
        self,
        srt_content: str,
        language: str,
        on_progress: Callable[[str], None] | None = None,
        cancel_token: CancelToken | None = None,
    ) -> str:
        chunks = chunk_text(srt_content, self.chunk_size)
        if not chunks:
            raise OpenAICompatError("Subtitle content was empty; no highlights can be extracted.")
        sections = []
        for index, chunk in enumerate(chunks, 1):
            if on_progress:
                on_progress(
                    f"{self.provider_name} is extracting highlights section {index}/{len(chunks)}"
                )
            try:
                sections.append(
                    self.client.generate(
                        self._text(
                            self.prompts.render(
                                "highlights", lang=language or "en", srt_content=chunk
                            )
                        ),
                        cancel_token,
                    )
                )
            except OpenAICompatError as error:
                LOGGER.error("Highlights section %d/%d failed: %s", index, len(chunks), error)
        if not sections:
            raise OpenAICompatError("Highlights failed for all sections.")
        return clean_highlights_output("\n".join(sections))
