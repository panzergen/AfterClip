"""Crash-safe text file writes.

``os.replace`` is atomic on the same filesystem, so a reader (resume,
history, the UI) always sees either the old file or the new complete one --
never a half-written report.

Two details matter on Windows:

* The temporary file name must be **unique per call**. A fixed name such as
  ``.report.json.tmp`` lets two writers racing on the same target collide on
  the same temp file; the loser's ``os.replace`` then fails with
  ``PermissionError`` (Windows refuses to replace a file another handle still
  has open) and the file can end up truncated.
* Antivirus scanners and the Windows search indexer can briefly hold a handle
  on a just-written file, so a transient ``PermissionError`` is retried for a
  short while before it is treated as a real failure.
"""

import os
import time
import uuid
from pathlib import Path

#: How long to keep retrying a replace that Windows refuses, in seconds.
REPLACE_RETRY_SECONDS = 2.0
_RETRY_DELAY = 0.02


def atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        temp.write_text(text, encoding="utf-8")
        _replace_with_retry(temp, path)
    finally:
        # No-op after a successful replace; removes the leftover on failure.
        temp.unlink(missing_ok=True)


def _replace_with_retry(temp: Path, path: Path) -> None:
    deadline = time.monotonic() + REPLACE_RETRY_SECONDS
    while True:
        try:
            os.replace(temp, path)
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(_RETRY_DELAY)
