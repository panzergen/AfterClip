import subprocess
from pathlib import Path

import pytest

from app.application.cancellation import CancellationToken
from app.domain.models import TranscriptionRequest
from app.infrastructure.process import FfmpegMediaTool, WhisperCliProvider, terminate_process_tree


class FakeRunner:
    """Stands in for ProcessRunner; records commands and fakes success."""

    def __init__(self, stderr: str = ""):
        self.commands = []
        self.stderr = stderr

    def run(self, command, cancel_token):
        self.commands.append(command)
        output = Path(command[-1])
        if output.suffix == ".png":
            output.write_bytes(b"frame")
        return subprocess.CompletedProcess(command, 0, "", self.stderr)


def test_extract_interval_frames_skips_highlights_outside_clip(tmp_path):
    tool = FfmpegMediaTool(FakeRunner())
    frames = tool.extract_interval_frames(
        tmp_path / "in.mp4",
        tmp_path / "frames",
        10,
        CancellationToken(),
        clip_start=10,
        clip_end=20,
        highlight_times=(0, 15, 25),
        mode="interval",
        sensitivity=0.35,
    )
    highlight_commands = [
        command for command in tool.runner.commands if "highlight" in str(command[-1])
    ]
    assert len(highlight_commands) == 1
    assert "interval_highlight_002.png" in str(highlight_commands[0][-1])
    assert (tmp_path / "frames" / "interval_highlight_002.png").is_file()
    assert frames


def test_extract_interval_frames_renames_scene_frames_by_timestamp(tmp_path):
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    (frames_dir / "scene_000000.png").write_bytes(b"frame")
    (frames_dir / "scene_000001.png").write_bytes(b"frame")
    stderr = "pts_time:3661.5 pts_time:59.9"
    tool = FfmpegMediaTool(FakeRunner(stderr=stderr))
    frames = tool.extract_interval_frames(
        tmp_path / "in.mp4", frames_dir, 10, CancellationToken(), mode="scene"
    )
    assert (frames_dir / "scene_01h01m01s.png").is_file()
    assert (frames_dir / "scene_00h00m59s.png").is_file()
    assert {"scene_01h01m01s.png", "scene_00h00m59s.png"} <= {frame.name for frame in frames}


def test_extract_interval_frames_survives_duplicate_scene_timestamps(tmp_path):
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    (frames_dir / "scene_000000.png").write_bytes(b"first")
    (frames_dir / "scene_000001.png").write_bytes(b"second")
    # Both frames report the same pts_time (cut boundary) - the old rename
    # crashed with WinError 183 here.
    tool = FfmpegMediaTool(FakeRunner(stderr="pts_time:59.9 pts_time:59.9"))
    frames = tool.extract_interval_frames(
        tmp_path / "in.mp4", frames_dir, 10, CancellationToken(), mode="scene"
    )
    names = {frame.name for frame in frames}
    assert "scene_00h00m59s.png" in names
    assert "scene_00h00m59s_2.png" in names


def test_extract_interval_frames_scene_rerun_replaces_stale_frames(tmp_path):
    """Re-extracting must not duplicate/shift names from a previous run."""
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    (frames_dir / "scene_00h00m59s.png").write_bytes(b"stale")
    (frames_dir / "scene_000000.png").write_bytes(b"fresh")
    tool = FfmpegMediaTool(FakeRunner(stderr="pts_time:59.9"))
    frames = tool.extract_interval_frames(
        tmp_path / "in.mp4", frames_dir, 10, CancellationToken(), mode="scene"
    )
    names = {frame.name for frame in frames}
    assert "scene_00h00m59s.png" in names
    assert "scene_00h00m59s_2.png" not in names
    assert (frames_dir / "scene_00h00m59s.png").read_bytes() == b"fresh"


def test_extract_interval_frames_builds_mode_filters(tmp_path):
    tool = FfmpegMediaTool(FakeRunner())
    tool.extract_interval_frames(
        tmp_path / "in.mp4", tmp_path / "f1", 15, CancellationToken(), mode="interval"
    )
    tool.extract_interval_frames(
        tmp_path / "in.mp4", tmp_path / "f2", 15, CancellationToken(), mode="scene", sensitivity=0.4
    )
    tool.extract_interval_frames(
        tmp_path / "in.mp4",
        tmp_path / "f3",
        15,
        CancellationToken(),
        mode="interval",
        resolution="mid",
    )
    tool.extract_interval_frames(
        tmp_path / "in.mp4",
        tmp_path / "f4",
        15,
        CancellationToken(),
        mode="interval",
        resolution="low",
    )
    interval_command = tool.runner.commands[0]
    scene_command = tool.runner.commands[1]
    mid_command = tool.runner.commands[2]
    low_command = tool.runner.commands[3]
    assert (
        "-vf" in interval_command
        and "fps=1/15" in interval_command
        and "scale" not in "".join(interval_command)
    )
    assert "select='gt(scene,0.4)',showinfo" in scene_command and "scale" not in "".join(
        scene_command
    )
    assert "fps=1/15,scale=1024:-2" in mid_command
    assert "fps=1/15,scale=768:-2" in low_command


def test_extract_interval_frames_scales_highlights(tmp_path):
    tool = FfmpegMediaTool(FakeRunner())
    tool.extract_interval_frames(
        tmp_path / "in.mp4",
        tmp_path / "frames",
        10,
        CancellationToken(),
        highlight_times=(15.0,),
        mode="interval",
        resolution="mid",
    )
    highlight_command = [
        command for command in tool.runner.commands if "highlight" in str(command[-1])
    ][0]
    assert "-vf" in highlight_command and "scale=1024:-2" in highlight_command


def test_whisper_provider_collects_files_by_stem(tmp_path):
    transcript_dir = tmp_path / "Transcripts"
    transcript_dir.mkdir()

    class ProducingRunner(FakeRunner):
        def run(self, command, cancel_token):
            self.commands.append(command)
            (transcript_dir / "sample.txt").write_text("hi", encoding="utf-8")
            (transcript_dir / "sample.srt").write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8"
            )
            return subprocess.CompletedProcess(command, 0, "", "")

    provider = WhisperCliProvider(runner=ProducingRunner(), executable="whisper")
    result = provider.transcribe(
        TranscriptionRequest(tmp_path / "sample.wav", transcript_dir, "tiny", ""),
        lambda message: None,
        CancellationToken(),
    )
    assert {file.name for file in result.transcript_files} == {"sample.txt", "sample.srt"}


def test_whisper_provider_condition_flag_disabled_adds_arg(tmp_path):
    class RecordingRunner(FakeRunner):
        def run(self, command, cancel_token):
            self.commands.append(command)
            output = tmp_path / "out"
            output.mkdir(exist_ok=True)
            (output / "sample.srt").write_text(
                "1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8"
            )
            return subprocess.CompletedProcess(command, 0, "", "")

    provider = WhisperCliProvider(
        runner=RecordingRunner(), executable="whisper", condition_on_previous_text=False
    )
    provider.transcribe(
        TranscriptionRequest(tmp_path / "sample.wav", tmp_path / "out", "tiny", ""),
        lambda message: None,
        CancellationToken(),
    )
    assert "--condition_on_previous_text" in provider.runner.commands[0]


def test_whisper_provider_surfaces_failure(tmp_path):
    class FailingRunner(FakeRunner):
        def run(self, command, cancel_token):
            self.commands.append(command)
            return subprocess.CompletedProcess(command, 1, "", "boom")

    provider = WhisperCliProvider(runner=FailingRunner(), executable="whisper")
    with pytest.raises(RuntimeError, match="Whisper failed"):
        provider.transcribe(
            TranscriptionRequest(tmp_path / "sample.wav", tmp_path / "out", "tiny", ""),
            lambda message: None,
            CancellationToken(),
        )


def test_terminate_process_tree_uses_taskkill_on_windows(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "app.infrastructure.process.subprocess.run", lambda command, **kwargs: calls.append(command)
    )

    class FakeProcess:
        pid = 123

    terminate_process_tree(FakeProcess())
    assert calls == [["taskkill", "/PID", "123", "/T", "/F"]]


def test_terminate_process_tree_falls_back_on_posix(monkeypatch):
    terminated = []

    class FakeProcess:
        pid = 123

        def terminate(self):
            terminated.append(True)

    monkeypatch.setattr("os.name", "posix")
    terminate_process_tree(FakeProcess())
    assert terminated == [True]
