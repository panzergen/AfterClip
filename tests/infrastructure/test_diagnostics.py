import subprocess

import app.infrastructure.diagnostics as diagnostics
from app.infrastructure.diagnostics import (
    DiskSpace,
    GpuInfo,
    check_output_dir,
    collect_diagnostics,
    detect_gpu,
    disk_space,
)


def test_check_output_dir_creates_and_accepts(tmp_path):
    target = tmp_path / "nested" / "out"
    assert check_output_dir(target) is None
    assert target.is_dir()
    assert not (target / ".afterclip_write_test").exists()


def test_check_output_dir_rejects_file(tmp_path):
    target = tmp_path / "afile"
    target.write_text("x", encoding="utf-8")
    problem = check_output_dir(target)
    assert problem is not None
    assert "not a directory" in problem


def test_check_output_dir_rejects_low_space(tmp_path, monkeypatch):
    monkeypatch.setattr(
        diagnostics, "disk_space", lambda path: DiskSpace(str(path), 1_000_000, 1024)
    )
    problem = check_output_dir(tmp_path, min_free_mb=200)
    assert problem is not None
    assert "Not enough free disk space" in problem


def test_disk_space_resolves_missing_path_to_ancestor(tmp_path):
    space = disk_space(tmp_path / "does-not-exist")
    assert space is not None
    assert space.free_bytes > 0
    assert space.free_gb >= 0


def test_detect_gpu_none_without_nvidia_smi(monkeypatch):
    monkeypatch.setattr(diagnostics.shutil, "which", lambda name: None)
    assert detect_gpu() is None


def test_detect_gpu_parses_nvidia_smi(monkeypatch):
    monkeypatch.setattr(diagnostics.shutil, "which", lambda name: "nvidia-smi")

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, "NVIDIA RTX 4090, 24564\n", "")

    monkeypatch.setattr(diagnostics.subprocess, "run", fake_run)
    assert detect_gpu() == GpuInfo(name="NVIDIA RTX 4090", memory_mb=24564)


def test_detect_gpu_tolerates_failure(monkeypatch):
    monkeypatch.setattr(diagnostics.shutil, "which", lambda name: "nvidia-smi")

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, "", "error")

    monkeypatch.setattr(diagnostics.subprocess, "run", fake_run)
    assert detect_gpu() is None


def test_collect_diagnostics_shape(tmp_path, monkeypatch):
    monkeypatch.setattr(diagnostics, "detect_gpu", lambda: GpuInfo("Test GPU", 8192))
    monkeypatch.setattr(
        diagnostics,
        "check_environment",
        lambda: diagnostics.EnvironmentStatus(True, True, False, False),
    )
    payload = collect_diagnostics(tmp_path)
    assert payload["app_version"]
    assert payload["python"]
    assert payload["ffmpeg"] is True
    assert payload["ffprobe"] is True
    assert payload["whisper"] is False
    assert payload["voiceprint"] is False
    assert payload["gpu"] == {"name": "Test GPU", "memory_mb": 8192}
    assert payload["disk"]["free_gb"] >= 0
    assert payload["output_dir"] == str(tmp_path)
    assert payload["memory"]["total_ram_gb"] >= 0
    assert payload["memory"]["recommended_vision_concurrency"] >= 1
