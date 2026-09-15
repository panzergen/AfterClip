import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path

from app.application.cancellation import CancelToken, ProcessingCancelled, wait_for_cancellation
from app.domain.models import TranscriptionResult

LOGGER = logging.getLogger(__name__)
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


def executable_available(name: str) -> bool:
    return shutil.which(name) is not None


def find_whisper_executable() -> str | None:
    candidates = [
        Path(sys.executable).parent / "Scripts" / "whisper.exe",
        Path(sys.executable).parent / "Scripts" / "whisper",
    ]
    return next((str(path) for path in candidates if path.is_file()), None) or shutil.which(
        "whisper"
    )


def get_media_metadata(input_path: Path) -> dict[str, object]:
    metadata: dict[str, object] = {
        "file_name": input_path.name,
        "file_size_mb": round(input_path.stat().st_size / (1024 * 1024), 2),
    }
    if not executable_available("ffprobe"):
        metadata["probe_status"] = "FFprobe not available"
        return metadata
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(input_path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            creationflags=CREATE_NO_WINDOW,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            fmt = data.get("format", {})
            streams = data.get("streams", [])
            creation_date = fmt.get("tags", {}).get("creation_time") or fmt.get("tags", {}).get(
                "date"
            )
            if not creation_date:
                creation_date = next(
                    (
                        stream.get("tags", {}).get("creation_time")
                        or stream.get("tags", {}).get("date")
                        for stream in streams
                        if stream.get("tags", {}).get("creation_time")
                        or stream.get("tags", {}).get("date")
                    ),
                    "Unknown",
                )
            metadata.update(
                {
                    "duration": fmt.get("duration", "Unknown"),
                    "format": fmt.get("format_name", "Unknown"),
                    "bit_rate": fmt.get("bit_rate", "Unknown"),
                    "creation_date": creation_date,
                    "streams": [
                        {
                            "type": stream.get("codec_type"),
                            "codec": stream.get("codec_name"),
                            "width": stream.get("width"),
                            "height": stream.get("height"),
                            "sample_rate": stream.get("sample_rate"),
                        }
                        for stream in streams
                    ],
                }
            )
        else:
            metadata["probe_status"] = "FFprobe failed"
    except Exception as error:
        LOGGER.warning("Could not read media metadata: %s", error)
        metadata["probe_status"] = "Metadata unavailable"
    return metadata


class ProcessRunner:
    def run(
        self, command: list[str], cancel_token: CancelToken
    ) -> subprocess.CompletedProcess[str]:
        LOGGER.info("Running %s", command[0])
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
                creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP,
            )
        except FileNotFoundError as error:
            LOGGER.error("Executable not found: %s", command[0])
            raise RuntimeError(
                f"Required program was not found: {command[0]}. "
                "Install it and ensure it is available in PATH."
            ) from error

        stdout_lines: list[str] = []
        stderr_lines: list[str] = []

        def drain(stream, target: list[str]) -> None:
            for line in iter(stream.readline, ""):
                target.append(line)
            stream.close()

        stdout_thread = threading.Thread(
            target=drain, args=(process.stdout, stdout_lines), daemon=True
        )
        stderr_thread = threading.Thread(
            target=drain, args=(process.stderr, stderr_lines), daemon=True
        )
        stdout_thread.start()
        stderr_thread.start()
        while process.poll() is None:
            if wait_for_cancellation(cancel_token, 0.1):
                terminate_process_tree(process)
                LOGGER.warning("Process cancelled: %s", command[0])
                process.wait()
                stdout_thread.join(timeout=2)
                stderr_thread.join(timeout=2)
                raise ProcessingCancelled
        stdout_thread.join()
        stderr_thread.join()
        stdout = "".join(stdout_lines)
        stderr = "".join(stderr_lines)
        if process.returncode:
            LOGGER.error(
                "Process failed with exit code %s: %s\n%s",
                process.returncode,
                command[0],
                (stderr or stdout or "").strip(),
            )
        else:
            LOGGER.info("Process completed successfully: %s", command[0])
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def terminate_process_tree(process: subprocess.Popen) -> None:
    if os.name == "nt" and process.pid:
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        process.terminate()


class FfmpegMediaTool:
    def __init__(self, runner: ProcessRunner | None = None):
        self.runner = runner or ProcessRunner()

    def prepare_audio(
        self,
        input_path: Path,
        work_dir: Path,
        cancel_token: CancelToken,
        clip_start=None,
        clip_end=None,
    ) -> Path:
        if input_path.suffix.lower() == ".wav" and clip_start is None and clip_end is None:
            return input_path
        output = work_dir / "converted_audio.wav"
        seek_args = []
        if clip_start is not None:
            seek_args += ["-ss", str(clip_start)]
        if clip_end is not None:
            seek_args += ["-to", str(clip_end)]
        result = self.runner.run(
            [
                "ffmpeg",
                "-y",
                *seek_args,
                "-i",
                str(input_path),
                "-vn",
                "-acodec",
                "pcm_s16le",
                "-ar",
                "16000",
                "-ac",
                "1",
                str(output),
            ],
            cancel_token,
        )
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg audio conversion failed: {result.stderr.strip()}")
        return output

    def extract_interval_frames(
        self,
        input_path: Path,
        frames_dir: Path,
        interval: int,
        cancel_token,
        clip_start: float | None = None,
        clip_end: float | None = None,
        highlight_times: tuple[float, ...] = (),
        mode: str = "interval",
        sensitivity: float = 0.35,
        resolution: str = "full",
    ) -> tuple[Path, ...]:
        frames_dir.mkdir(parents=True, exist_ok=True)
        seek_args = []
        if clip_start is not None:
            seek_args += ["-ss", str(clip_start)]
        if clip_end is not None:
            seek_args += ["-to", str(clip_end)]
        # Vision models downscale internally anyway; scaling shrinks base64
        # size and speeds up the analysis round-trips.
        scale_map = {"mid": ",scale=1024:-2", "low": ",scale=768:-2"}
        scale = scale_map.get(resolution, "")
        output_pattern = frames_dir / ("scene_%06d.png" if mode == "scene" else "interval_%06d.png")
        filters = (
            f"select='gt(scene,{sensitivity})',showinfo{scale}"
            if mode == "scene"
            else f"fps=1/{max(1, interval)}{scale}"
        )
        result = self.runner.run(
            [
                "ffmpeg",
                "-y",
                *seek_args,
                "-i",
                str(input_path),
                "-vf",
                filters,
                "-vsync",
                "vfr",
                str(output_pattern),
            ],
            cancel_token,
        )
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg frame extraction failed: {result.stderr.strip()}")
        scene_stderr = result.stderr
        highlight_scale = scale_map.get(resolution, "")
        highlight_args = ["-vf", highlight_scale.lstrip(",")] if highlight_scale else []
        for index, timestamp in enumerate(highlight_times, 1):
            if clip_start is not None and timestamp < clip_start:
                continue
            if clip_end is not None and timestamp > clip_end:
                continue
            frame = frames_dir / f"{mode}_highlight_{index:03d}.png"
            result = self.runner.run(
                [
                    "ffmpeg",
                    "-y",
                    "-ss",
                    str(timestamp),
                    "-i",
                    str(input_path),
                    "-frames:v",
                    "1",
                    *highlight_args,
                    str(frame),
                ],
                cancel_token,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"FFmpeg highlighted frame extraction failed: {result.stderr.strip()}"
                )
        if mode == "scene":
            timestamps = re.findall(r"pts_time:([\d.]+)", scene_stderr)
            # Remove frames from any earlier run before renaming this run's
            # output: leftover timestamp-named files otherwise collide (WinError
            # 183) and shift every subsequent frame to a wrong name.
            final_name = re.compile(r"scene_\d{2}h\d{2}m\d{2}s(_\d+)?\.png")
            for stale in list(frames_dir.glob("scene_*.png")):
                if final_name.fullmatch(stale.name):
                    stale.unlink(missing_ok=True)
            raw_name = re.compile(r"scene_\d+\.png")
            scene_frames = sorted(
                path for path in frames_dir.glob("scene_*.png") if raw_name.fullmatch(path.name)
            )
            for index, frame in enumerate(scene_frames):
                timestamp = float(timestamps[index]) if index < len(timestamps) else float(index)
                total = int(timestamp)
                stamp = f"{total // 3600:02d}h{total % 3600 // 60:02d}m{total % 60:02d}s"
                # Duplicate timestamps happen at cut boundaries; keep both
                # frames by suffixing instead of crashing the rename.
                target = frames_dir / f"scene_{stamp}.png"
                copy = 1
                while target.exists():
                    copy += 1
                    target = frames_dir / f"scene_{stamp}_{copy}.png"
                frame.rename(target)
        return tuple(sorted(frames_dir.glob("*.png")))


class WhisperCliProvider:
    def __init__(
        self,
        runner: ProcessRunner | None = None,
        executable: str | None = None,
        condition_on_previous_text: bool = True,
    ):
        self.runner = runner or ProcessRunner()
        self.executable = executable or find_whisper_executable() or "whisper"
        # Disabling this reduces hallucination loops; the hallucination filter
        # turns it off, and it stays on otherwise to preserve default output.
        self.condition_on_previous_text = condition_on_previous_text

    def transcribe(self, request, on_progress: Callable[[str], None], cancel_token: CancelToken):
        command = [
            self.executable,
            str(request.input_path),
            "--model",
            request.model,
            "--output_dir",
            str(request.output_dir),
            "--output_format",
            "all",
        ]
        if not self.condition_on_previous_text:
            command += ["--condition_on_previous_text", "False"]
        if request.language.strip():
            command += ["--language", request.language.strip()]
        on_progress("Whisper is running")
        result = self.runner.run(command, cancel_token)
        if result.returncode != 0:
            raise RuntimeError(f"Whisper failed: {(result.stderr or result.stdout).strip()}")
        files = tuple(sorted(request.output_dir.glob(f"{request.input_path.stem}.*")))
        if not files:
            raise RuntimeError("Whisper completed but produced no transcript files.")
        return TranscriptionResult(request.output_dir, files)
