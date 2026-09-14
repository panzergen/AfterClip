import platform
import sys

import app.infrastructure.hardware as hardware
from app.infrastructure.hardware import (
    FRAME_FULL_MEMORY_MB,
    MAX_VISION_CONCURRENCY,
    MemoryProfile,
    detect_memory_profile,
    is_unified_memory,
    recommend_frame_resolution,
    recommend_vision_concurrency,
)


def test_is_unified_memory_apple_silicon(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(platform, "machine", lambda: "arm64")
    assert is_unified_memory() is True


def test_is_unified_memory_intel_mac_is_not(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(platform, "machine", lambda: "x86_64")
    assert is_unified_memory() is False


def test_is_unified_memory_windows_is_not(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert is_unified_memory() is False


def test_total_ram_is_positive_on_this_host():
    assert hardware.total_ram_mb() > 0


def test_effective_gpu_memory_uses_ram_when_unified():
    profile = MemoryProfile(unified=True, total_ram_mb=32_768, gpu_memory_mb=None)
    assert profile.effective_gpu_memory_mb == 32_768


def test_effective_gpu_memory_uses_vram_when_discrete():
    profile = MemoryProfile(unified=False, total_ram_mb=32_768, gpu_memory_mb=8_192)
    assert profile.effective_gpu_memory_mb == 8_192
    assert MemoryProfile(unified=False, total_ram_mb=8_000).effective_gpu_memory_mb == 0


def test_frame_resolution_recommendations():
    assert recommend_frame_resolution(MemoryProfile(True, FRAME_FULL_MEMORY_MB)) == "full"
    assert recommend_frame_resolution(MemoryProfile(False, 32_000, gpu_memory_mb=10_000)) == "mid"
    assert recommend_frame_resolution(MemoryProfile(False, 32_000, gpu_memory_mb=2_000)) == "low"
    assert recommend_frame_resolution(MemoryProfile(False, 32_000)) == "low"


def test_vision_concurrency_recommendations():
    assert (
        recommend_vision_concurrency(MemoryProfile(True, FRAME_FULL_MEMORY_MB))
        == MAX_VISION_CONCURRENCY
    )
    assert recommend_vision_concurrency(MemoryProfile(False, 8_000, gpu_memory_mb=4_000)) == 1


def test_detect_memory_profile_uses_injected_gpu(monkeypatch):
    monkeypatch.setattr(hardware, "total_ram_mb", lambda: 16_384)
    monkeypatch.setattr(hardware, "is_unified_memory", lambda: False)
    profile = detect_memory_profile("Test GPU", 6_000)
    assert profile.gpu_name == "Test GPU"
    assert profile.gpu_memory_mb == 6_000
    assert profile.total_ram_mb == 16_384
    assert profile.total_ram_gb == 16.0
