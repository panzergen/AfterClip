import threading
from typing import Protocol


class ProcessingCancelled(Exception):
    """Raised when a running external process is asked to stop."""


class JobCancelled(Exception):
    """Raised when the active job is cancelled between processing steps."""


class CancelToken(Protocol):
    def is_cancelled(self) -> bool: ...


class CancellationToken:
    """Thread-safe token with an event so waiters wake up the instant
    cancellation happens instead of polling on a sleep interval."""

    def __init__(self):
        self._event = threading.Event()

    @property
    def cancelled_event(self) -> threading.Event:
        return self._event

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()


def wait_for_cancellation(cancel_token: CancelToken | None, timeout: float) -> bool:
    """Wait up to `timeout` seconds; return True as soon as cancellation is seen.

    Tokens exposing a `cancelled_event` respond sub-millisecond; other tokens
    (and None) fall back to a timeout poll.
    """
    event = getattr(cancel_token, "cancelled_event", None) or threading.Event()
    if event.wait(timeout):
        return True
    return cancel_token is not None and cancel_token.is_cancelled()
