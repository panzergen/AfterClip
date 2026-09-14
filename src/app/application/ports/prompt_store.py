from typing import Protocol

from app.domain.prompts import PromptSet


class PromptStore(Protocol):
    """Persistence for user-editable prompt templates (Phase 4 WS-B)."""

    def load(self) -> PromptSet: ...
    def save(self, prompt_set: PromptSet) -> None: ...
