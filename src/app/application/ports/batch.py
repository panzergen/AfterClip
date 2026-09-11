from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.application.batch import BatchJob


class BatchQueue(Protocol):
    """Persistence contract for the batch queue (T08b/T26b)."""

    def load(self) -> "list[BatchJob]": ...

    def save(self, jobs: "list[BatchJob]") -> None: ...

    def update(self, job_id: str, **fields) -> None: ...

    def path(self) -> Path: ...
