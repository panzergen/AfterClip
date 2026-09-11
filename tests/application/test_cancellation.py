import time

from app.application.cancellation import CancellationToken, wait_for_cancellation


def test_cancellation_token_event_wakes_waiters_immediately():
    token = CancellationToken()
    token.cancel()
    started = time.monotonic()
    assert wait_for_cancellation(token, timeout=30)
    assert time.monotonic() - started < 1.0


def test_wait_for_cancellation_falls_back_to_polling():
    class StaticToken:
        def is_cancelled(self) -> bool:
            return False

    started = time.monotonic()
    assert not wait_for_cancellation(StaticToken(), timeout=0.05)
    assert time.monotonic() - started < 1.0


def test_wait_for_cancellation_accepts_none_token():
    started = time.monotonic()
    assert not wait_for_cancellation(None, timeout=0.05)
    assert time.monotonic() - started < 1.0


def test_cancel_is_idempotent_and_is_cancelled_persists():
    token = CancellationToken()
    assert not token.is_cancelled()
    token.cancel()
    token.cancel()
    assert token.is_cancelled()
