import json
import re
import threading
import time
import urllib.request

from app.application.cancellation import ProcessingCancelled, wait_for_cancellation

THINK_TAG_PATTERN = r"<think.*?/think>"


def clean_thinking_tags(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    cleaned = cleaned.replace("\r", "")
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", cleaned)
    # Remove <think>.../</think> blocks and common reasoning output leftovers.
    cleaned = re.sub(THINK_TAG_PATTERN, "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    return cleaned.strip()


def chunk_text(text: str, size: int = 3500) -> tuple[str, ...]:
    text = text.strip()
    if len(text) <= size:
        return (text,) if text else ()
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        break_point = text.rfind("\n", start, end)
        if break_point > start:
            end = break_point + 1
        chunks.append(text[start:end].strip())
        start = end
    return tuple(chunk for chunk in chunks if chunk)


def http_post_json(url: str, payload: dict, timeout: float, headers: dict | None = None) -> dict:
    merged = {"Content-Type": "application/json"}
    if headers:
        merged.update(headers)
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=merged,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def http_get_json(url: str, timeout: float = 30.0, headers: dict | None = None) -> dict:
    merged = {"Accept": "application/json"}
    if headers:
        merged.update(headers)
    request = urllib.request.Request(url, headers=merged, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json_cancellable(
    url: str,
    payload: dict,
    timeout: float,
    cancel_token=None,
    request_fn=http_post_json,
) -> dict:
    """POST JSON with periodic cancel polling; urllib cannot be interrupted directly.

    Runs the blocking request on a helper thread and wakes the instant the
    token's cancel event fires (sub-millisecond when the token is event-based).
    """
    result: dict = {}
    error: BaseException | None = None
    done = threading.Event()

    def execute() -> None:
        nonlocal result, error
        try:
            result = request_fn(url, payload, timeout)
        except BaseException as request_error:
            error = request_error
        finally:
            done.set()

    worker = threading.Thread(target=execute, daemon=True)
    worker.start()
    # urllib's timeout is not reliable once a server has accepted the
    # connection and then stalls; enforce a wall-clock deadline as well. The
    # daemon worker is abandoned, which is safe because the caller moves on.
    deadline = time.monotonic() + timeout + 5.0
    while not done.wait(0.2):
        if time.monotonic() >= deadline:
            raise TimeoutError(f"HTTP request timed out after {timeout:.0f} seconds")
        if wait_for_cancellation(cancel_token, 0.1):
            raise ProcessingCancelled
    if error is not None:
        raise error
    return result
