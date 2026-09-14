"""Hardware memory strategy (Phase 3).

On unified-memory machines (Apple Silicon, some integrated GPUs) the CPU and GPU
share one RAM pool, so the GPU's usable memory equals total system RAM. On
discrete-GPU machines it is the VRAM budget that matters. This module turns that
into a *conservative recommendation* for frame resolution and vision
concurrency; it never changes results on its own.

The recommendation is intentionally capped: oversubscribing a small GPU or
tripping provider rate limits is worse than running a little slower.
"""

import os
import platform
import sys
from dataclasses import dataclass

# Conservative caps.
MAX_VISION_CONCURRENCY = 2
FRAME_FULL_MEMORY_MB = 16 * 1024
FRAME_MID_MEMORY_MB = 8 * 1024


@dataclass(frozen=True)
class MemoryProfile:
    unified: bool
    total_ram_mb: int
    gpu_name: str | None = None
    gpu_memory_mb: int | None = None

    @property
    def total_ram_gb(self) -> float:
        return round(self.total_ram_mb / 1024, 1)

    @property
    def effective_gpu_memory_mb(self) -> int:
        """GPU budget: shared RAM when unified, else dedicated VRAM (0 if none)."""
        if self.unified:
            return self.total_ram_mb
        return self.gpu_memory_mb or 0


def is_unified_memory() -> bool:
    """True on hosts where CPU and GPU share one memory pool."""
    if sys.platform == "darwin":
        return platform.machine().lower() in {"arm64", "aarch64"}
    return False


def _windows_total_ram_mb() -> int:
    try:
        import ctypes

        class MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatusEx()
        status.dwLength = ctypes.sizeof(MemoryStatusEx)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return 0
        return int(status.ullTotalPhys / (1024 * 1024))
    except Exception:  # missing ctypes/API: treat as unknown
        return 0


def total_ram_mb() -> int:
    if sys.platform.startswith("win"):
        return _windows_total_ram_mb()
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        size = os.sysconf("SC_PAGE_SIZE")
        return int(pages * size / (1024 * 1024))
    except (AttributeError, ValueError, OSError):
        return 0


def detect_memory_profile(
    gpu_name: str | None = None, gpu_memory_mb: int | None = None
) -> MemoryProfile:
    return MemoryProfile(
        unified=is_unified_memory(),
        total_ram_mb=total_ram_mb(),
        gpu_name=gpu_name,
        gpu_memory_mb=gpu_memory_mb,
    )


def recommend_frame_resolution(profile: MemoryProfile) -> str:
    """Suggested frame resolution: ``full`` / ``mid`` / ``low``.

    Without a GPU (or VRAM) frames are kept small; with a large budget they can
    stay at full resolution for sharper vision analysis.
    """
    effective = profile.effective_gpu_memory_mb
    if effective >= FRAME_FULL_MEMORY_MB:
        return "full"
    if effective >= FRAME_MID_MEMORY_MB:
        return "mid"
    return "low"


def recommend_vision_concurrency(profile: MemoryProfile) -> int:
    """Suggested number of frames to analyze at once (bounded)."""
    if profile.effective_gpu_memory_mb >= FRAME_FULL_MEMORY_MB:
        return MAX_VISION_CONCURRENCY
    return 1
