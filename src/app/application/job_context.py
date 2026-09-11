import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from app.application.cancellation import JobCancelled, ProcessingCancelled
from app.application.service_io import save_state, write_report
from app.domain.models import ProgressEvent, TranscriptionRequest

LOGGER = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class JobContext:
    """Everything one job run needs to record its own lifecycle."""

    job_dir: Path
    state_path: Path
    report_path: Path
    request: TranscriptionRequest
    metadata: dict
    state: dict
    steps: dict[str, dict]
    on_event: Callable[[ProgressEvent], None]


class StepRecorder:
    """The only place that mutates `state["steps"][key]` or writes the state file."""

    def __init__(self, context: JobContext):
        self.context = context

    def save(self, current_step: str | None = None) -> None:
        self.context.state["current_step"] = current_step
        save_state(self.context.state_path, self.context.state)

    def report(self, status: str) -> None:
        write_report(self.context.report_path, self.context.request, status, self.context.metadata, self.context.steps)

    def discard(self, key: str) -> None:
        self.context.steps.pop(key, None)

    def begin(self, key: str, name: str, percent: int) -> None:
        self.context.steps[key] = {"name": name, "status": "running"}
        self.save(current_step=key)
        self.report("Running")
        self.context.on_event(ProgressEvent(name, percent))

    def record(
        self,
        key: str,
        name: str,
        percent: int,
        action: Callable[[], T],
        *,
        end_percent: int | None = None,
        emit_start: bool = True,
        tolerated_failure_event: tuple[str, int] | None = None,
    ) -> T | None:
        """Run `action` as a checkpointed step.

        Cancel -> JobCancelled after recording the step; unexpected errors are
        re-raised unless `tolerated_failure_event` is set (T16: non-fatal steps
        record their failure and let the job continue).
        """
        started = time.monotonic()
        self.context.steps[key] = {"name": name, "status": "running"}
        self.save(current_step=key)
        self.report("Running")
        if emit_start:
            self.context.on_event(ProgressEvent(name, percent))
        try:
            result = action()
        except ProcessingCancelled as error:
            self.context.steps[key] = {"name": name, "status": "cancelled", "duration_seconds": round(time.monotonic() - started, 2)}
            self.save(current_step=key)
            self.report("Cancelled")
            raise JobCancelled from error
        except Exception as error:
            self.context.steps[key] = {"name": name, "status": "failed", "duration_seconds": round(time.monotonic() - started, 2), "error": str(error)}
            self.save(current_step=key)
            self.report("Failed")
            if tolerated_failure_event is None:
                raise
            LOGGER.warning("%s failed; keeping existing results: %s", name, error)
            self.context.on_event(ProgressEvent(tolerated_failure_event[0], tolerated_failure_event[1]))
            return None
        duration = round(time.monotonic() - started, 2)
        self.context.steps[key] = {"name": name, "status": "completed", "duration_seconds": duration}
        self.save(current_step=None)
        self.report("Running")
        self.context.on_event(ProgressEvent(f"{name} finished in {duration} seconds", end_percent if end_percent is not None else percent))
        return result

    def finish(self, status: str) -> None:
        self.context.state.update({"status": status, "steps": self.context.steps, "current_step": None})
        save_state(self.context.state_path, self.context.state)
        self.report(status)
