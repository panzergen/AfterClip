from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from app.domain.models import TranscriptionRequest, TranscriptionResult


class ProcessingCancelled(Exception):
    """Raised when a running external process is asked to stop."""


class CancelToken(Protocol):
    def is_cancelled(self) -> bool: ...


class TranscriptionProvider(Protocol):
    def transcribe(
        self,
        request: TranscriptionRequest,
        on_progress: Callable[[str], None],
        cancel_token: CancelToken,
    ) -> TranscriptionResult: ...


class MediaTool(Protocol):
    def prepare_audio(self, input_path: Path, work_dir: Path, cancel_token: CancelToken) -> Path: ...


class SecretStore(Protocol):
    def get(self, name: str) -> str | None: ...
    def set(self, name: str, value: str) -> None: ...
    def delete(self, name: str) -> None: ...
