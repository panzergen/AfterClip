import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from app.infrastructure.hardware import (
    detect_memory_profile,
    recommend_frame_resolution,
    recommend_vision_concurrency,
)
from app.infrastructure.process import (
    CREATE_NO_WINDOW,
    executable_available,
    find_whisper_executable,
)
from app.version import version_string

# Fail a job before it starts rather than when frame extraction fills the disk.
MIN_FREE_DISK_MB = 200


@dataclass(frozen=True)
class EnvironmentStatus:
    ffmpeg: bool
    ffprobe: bool
    whisper: bool
    voiceprint: bool


@dataclass(frozen=True)
class DiskSpace:
    path: str
    total_bytes: int
    free_bytes: int

    @property
    def free_gb(self) -> float:
        return round(self.free_bytes / (1024**3), 1)


@dataclass(frozen=True)
class GpuInfo:
    name: str
    memory_mb: int | None = None


def check_environment() -> EnvironmentStatus:
    from app.infrastructure.voiceprint_embedder import voiceprints_available

    return EnvironmentStatus(
        ffmpeg=executable_available("ffmpeg"),
        ffprobe=executable_available("ffprobe"),
        whisper=find_whisper_executable() is not None,
        voiceprint=voiceprints_available(),
    )


def disk_space(path: Path) -> DiskSpace | None:
    """Disk usage for the nearest existing ancestor of ``path`` (or None)."""
    target = path
    while not target.exists() and target != target.parent:
        target = target.parent
    try:
        usage = shutil.disk_usage(target)
    except OSError:
        return None
    return DiskSpace(str(path), usage.total, usage.free)


def check_output_dir(path: Path, min_free_mb: int = MIN_FREE_DISK_MB) -> str | None:
    """Return a user-facing problem for an output dir, or None when usable.

    Verifies the path is a directory, can be created and written to, and has
    enough free space for a processing job (T64).
    """
    if path.exists() and not path.is_dir():
        return f"The output path is a file, not a directory:\n{path}"
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".afterclip_write_test"
        probe.write_text("", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError as error:
        return f"The output directory is not writable:\n{path}\n({error})"
    space = disk_space(path)
    if space is not None and space.free_bytes < min_free_mb * 1024 * 1024:
        return (
            f"Not enough free disk space in the output directory:\n{path}\n"
            f"{space.free_gb} GB free, at least {min_free_mb} MB required."
        )
    return None


def detect_gpu() -> GpuInfo | None:
    """Best-effort NVIDIA GPU detection; returns None when unavailable."""
    if shutil.which("nvidia-smi") is None:
        return None
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            creationflags=CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    first = next((line for line in result.stdout.splitlines() if line.strip()), None)
    if not first:
        return None
    name, _, memory = first.partition(",")
    try:
        memory_mb: int | None = int(memory.strip())
    except ValueError:
        memory_mb = None
    return GpuInfo(name=name.strip(), memory_mb=memory_mb)


def collect_diagnostics(output_dir: Path | None = None) -> dict:
    """Redacted diagnostic payload for logs and bug reports (T62)."""
    env = check_environment()
    gpu = detect_gpu()
    profile = detect_memory_profile(
        gpu_name=gpu.name if gpu else None,
        gpu_memory_mb=gpu.memory_mb if gpu else None,
    )
    payload: dict = {
        "app_version": version_string(),
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "ffmpeg": env.ffmpeg,
        "ffprobe": env.ffprobe,
        "whisper": env.whisper,
        "voiceprint": env.voiceprint,
        "gpu": None if gpu is None else {"name": gpu.name, "memory_mb": gpu.memory_mb},
        "memory": {
            "unified": profile.unified,
            "total_ram_gb": profile.total_ram_gb,
            "effective_gpu_memory_mb": profile.effective_gpu_memory_mb,
            "recommended_frame_resolution": recommend_frame_resolution(profile),
            "recommended_vision_concurrency": recommend_vision_concurrency(profile),
        },
    }
    if output_dir is not None:
        space = disk_space(output_dir)
        payload["output_dir"] = str(output_dir)
        payload["disk"] = (
            None
            if space is None
            else {
                "total_gb": round(space.total_bytes / (1024**3), 1),
                "free_gb": space.free_gb,
            }
        )
    return payload
