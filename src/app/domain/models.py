from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class JobState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    CANCELLING = "cancelling"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class TranscriptionRequest:
    input_path: Path
    output_dir: Path
    model: str = "turbo"
    language: str = ""
    user_task: str = ""
    clip_start: float | None = None
    clip_end: float | None = None
    extract_frames: bool = False
    frame_interval: int = 10
    highlight_times: tuple[float, ...] = ()


@dataclass(frozen=True)
class TranscriptionResult:
    output_dir: Path
    transcript_files: tuple[Path, ...]


@dataclass(frozen=True)
class ProgressEvent:
    message: str
    percent: int | None = None
