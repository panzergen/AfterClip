import logging
from collections.abc import Callable

from app.application.cancellation import CancelToken
from app.domain.prompts import PromptSet
from app.infrastructure.llm.transport import chunk_text, clean_highlights_output
from app.infrastructure.ollama.client import OllamaClient, OllamaError

LOGGER = logging.getLogger(__name__)

CHUNK_SIZE = 3500


class OllamaTextProvider:
    """Summaries and timestamped highlights through a local Ollama model."""

    provider_name = "ollama"

    def __init__(
        self,
        model: str,
        client: OllamaClient | None = None,
        chunk_size: int = CHUNK_SIZE,
        prompts: PromptSet | None = None,
    ):
        self.model = model
        self.client = client or OllamaClient()
        self.chunk_size = chunk_size
        self.prompts = prompts or PromptSet()

    def generate(
        self, prompt: str, cancel_token: CancelToken | None = None
    ) -> str:
        """Single-prompt generation (used for topic titles and similar)."""
        return self.client.generate(self.model, prompt, cancel_token)

    def summarize(self, transcript: str, language: str, on_progress: Callable[[str], None] | None = None, cancel_token: CancelToken | None = None) -> str:
        chunks = chunk_text(transcript, self.chunk_size)
        if not chunks:
            raise OllamaError("Transcript was empty; nothing to summarize.")
        if len(chunks) == 1:
            if on_progress:
                on_progress("Ollama is summarizing the transcript")
            return self.client.generate(
                self.model,
                self.prompts.render("summary", lang=language or "en", transcript=chunks[0]),
                cancel_token,
                on_progress,
            )
        partials = []
        for index, chunk in enumerate(chunks, 1):
            if on_progress:
                on_progress(f"Ollama is summarizing section {index}/{len(chunks)}")
            partials.append(
                self.client.generate(
                    self.model,
                    self.prompts.render("summary", lang=language or "en", transcript=chunk),
                    cancel_token,
                    on_progress,
                )
            )
        if on_progress:
            on_progress("Ollama is combining section summaries")
        return self.client.generate(
            self.model,
            self.prompts.render(
                "summary_combine", lang=language or "en", summaries="\n\n".join(partials)
            ),
            cancel_token,
            on_progress,
        )

    def extract_highlights(self, srt_content: str, language: str, on_progress: Callable[[str], None] | None = None, cancel_token: CancelToken | None = None) -> str:
        chunks = chunk_text(srt_content, self.chunk_size)
        if not chunks:
            raise OllamaError("Subtitle content was empty; no highlights can be extracted.")
        sections = []
        for index, chunk in enumerate(chunks, 1):
            if on_progress:
                on_progress(f"Ollama is extracting highlights section {index}/{len(chunks)}")
            try:
                sections.append(
                    self.client.generate(
                        self.model,
                        self.prompts.render("highlights", lang=language or "en", srt_content=chunk),
                        cancel_token,
                        on_progress,
                    )
                )
            except OllamaError as error:
                LOGGER.error("Highlights section %d/%d failed: %s", index, len(chunks), error)
        if not sections:
            raise OllamaError("Highlights failed for all sections.")
        return clean_highlights_output("\n".join(sections))
