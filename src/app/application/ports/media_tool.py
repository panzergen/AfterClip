from pathlib import Path
from typing import Protocol

from app.application.cancellation import CancelToken


class MediaTool(Protocol):
    def prepare_audio(self, input_path: Path, work_dir: Path, cancel_token: CancelToken, clip_start: float | None = None, clip_end: float | None = None) -> Path: ...

    def extract_interval_frames(self, input_path: Path, frames_dir: Path, interval: int, cancel_token: CancelToken, clip_start: float | None = None, clip_end: float | None = None, highlight_times: tuple[float, ...] = (), mode: str = "interval", sensitivity: float = 0.35, resolution: str = "full") -> tuple[Path, ...]: ...
