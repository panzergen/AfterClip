from collections.abc import Callable
from typing import Protocol

from app.application.cancellation import CancelToken
from app.domain.models import TranscriptionRequest, TranscriptionResult


class TranscriptionProvider(Protocol):
    def transcribe(
        self,
        request: TranscriptionRequest,
        on_progress: Callable[[str], None],
        cancel_token: CancelToken,
    ) -> TranscriptionResult: ...
