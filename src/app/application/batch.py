"""Batch queue: sequential multi-file processing with crash-safe state (T08b/T26b).

The queue state lives in ``batch_queue.json`` inside the default output
directory. Jobs are executed one at a time; individual failures do not stop
the batch, and a batch cancel leaves pending jobs pending so the batch can be
resumed later.
"""
import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from app.application.cancellation import CancellationToken
from app.application.service import JobCancelled
from app.domain.models import TranscriptionRequest

LOGGER = logging.getLogger(__name__)

TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})


@dataclass
class BatchJob:
    id: str
    input_path: str
    output_dir: str
    model: str = "turbo"
    language: str = ""
    task: str = ""
    speaker_vtt_path: str = ""
    clip_start: float | None = None
    clip_end: float | None = None
    extract_frames: bool = False
    frame_interval: int = 10
    frame_modes: tuple[str, ...] = ()
    frame_resolution: str = "full"
    scene_sensitivity: float = 0.35
    highlight_times: tuple[float, ...] = ()
    analyze_text: bool = False
    text_provider_name: str = "ollama"
    text_model: str = ""
    analyze_vision: bool = False
    vision_provider_name: str = "ollama"
    vision_model: str = ""
    embed_frames: bool = False
    transcript_merge_seconds: float | None = None
    output_language: str = ""
    output_name: str = ""
    status: str = "pending"
    error: str = ""

    @property
    def display_name(self) -> str:
        return Path(self.input_path).name

    def text_spec(self) -> tuple[str, str] | None:
        return (self.text_provider_name, self.text_model) if self.analyze_text else None

    def vision_spec(self) -> tuple[str, str] | None:
        return (self.vision_provider_name, self.vision_model) if self.analyze_vision else None

    def to_request(self) -> TranscriptionRequest:
        return TranscriptionRequest(
            input_path=Path(self.input_path),
            output_dir=Path(self.output_dir),
            model=self.model,
            language=self.language,
            user_task=self.task,
            clip_start=self.clip_start,
            clip_end=self.clip_end,
            extract_frames=self.extract_frames,
            frame_interval=self.frame_interval,
            highlight_times=self.highlight_times,
            output_name=self.output_name,
            frame_mode=self.frame_modes[0] if self.frame_modes else "interval",
            scene_sensitivity=self.scene_sensitivity,
            frame_modes=self.frame_modes,
            speaker_vtt_path=self.speaker_vtt_path,
            analyze_text=self.analyze_text,
            analysis_model=self.text_model,
            analyze_vision=self.analyze_vision,
            vision_model=self.vision_model,
            embed_frames=self.embed_frames,
            frame_resolution=self.frame_resolution,
            transcript_merge_seconds=self.transcript_merge_seconds,
            output_language=self.output_language,
        )


class BatchStore:
    """JSON-file persistence; 'running' jobs recover to 'pending' (T26b)."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> list[BatchJob]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        jobs = []
        for record in data.get("jobs", []):
            record["frame_modes"] = tuple(record.get("frame_modes", ()))
            record["highlight_times"] = tuple(record.get("highlight_times", ()))
            job = BatchJob(**record)
            if job.status == "running":
                job.status = "pending"
            jobs.append(job)
        return jobs

    def save(self, jobs: list[BatchJob]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "jobs": [asdict(job) for job in jobs]}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def update(self, job_id: str, **fields) -> None:
        jobs = self.load()
        for job in jobs:
            if job.id == job_id:
                for key, value in fields.items():
                    setattr(job, key, value)
        self.save(jobs)


def new_batch_job(input_path: Path, output_dir: Path, **settings) -> BatchJob:
    job = BatchJob(id=uuid.uuid4().hex[:12], input_path=str(input_path), output_dir=str(output_dir))
    for key, value in settings.items():
        if hasattr(job, key):
            setattr(job, key, value)
    return job


def run_batch(
    jobs: list[BatchJob],
    store: BatchStore,
    job_runner: Callable[[BatchJob, Callable[[str], None], CancellationToken], None],
    on_event: Callable[[str], None],
    cancel_token: CancellationToken,
) -> None:
    """Execute pending jobs sequentially; a job failure never stops the batch."""
    for job in jobs:
        if job.status != "pending":
            continue
        if cancel_token.is_cancelled():
            on_event("Batch cancelled; pending jobs kept for resume")
            return
        store.update(job.id, status="running", error="")
        on_event(f"Batch: {job.display_name} started")
        try:
            job_runner(job, on_event, cancel_token)
        except JobCancelled:
            store.update(job.id, status="cancelled")
            on_event(f"Batch: {job.display_name} cancelled; remaining jobs kept pending")
            return
        except Exception as error:
            LOGGER.exception("Batch job failed: %s", job.input_path)
            store.update(job.id, status="failed", error=str(error))
            on_event(f"Batch: {job.display_name} failed ({error})")
            continue
        store.update(job.id, status="completed")
        on_event(f"Batch: {job.display_name} completed")
    on_event("Batch finished")
