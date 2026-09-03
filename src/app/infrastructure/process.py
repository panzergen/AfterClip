import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import json
from collections.abc import Callable
from pathlib import Path

from app.application.ports import CancelToken, ProcessingCancelled
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
    return next((str(path) for path in candidates if path.is_file()), None) or shutil.which("whisper")


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
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(input_path)],
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
            creation_date = fmt.get("tags", {}).get("creation_time")
            if not creation_date:
                creation_date = next(
                    (stream.get("tags", {}).get("creation_time") for stream in streams if stream.get("tags", {}).get("creation_time")),
                    "Unknown",
                )
            metadata.update({
                "duration": fmt.get("duration", "Unknown"),
                "format": fmt.get("format_name", "Unknown"),
                "bit_rate": fmt.get("bit_rate", "Unknown"),
                "creation_date": creation_date,
                "streams": [
                    {"type": stream.get("codec_type"), "codec": stream.get("codec_name"), "width": stream.get("width"), "height": stream.get("height"), "sample_rate": stream.get("sample_rate")}
                    for stream in streams
                ],
            })
        else:
            metadata["probe_status"] = "FFprobe failed"
    except Exception as error:
        LOGGER.warning("Could not read media metadata: %s", error)
        metadata["probe_status"] = "Metadata unavailable"
    return metadata


class ProcessRunner:
    def run(self, command: list[str], cancel_token: CancelToken) -> subprocess.CompletedProcess[str]:
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

        stdout_thread = threading.Thread(target=drain, args=(process.stdout, stdout_lines), daemon=True)
        stderr_thread = threading.Thread(target=drain, args=(process.stderr, stderr_lines), daemon=True)
        stdout_thread.start()
        stderr_thread.start()
        while process.poll() is None:
            if cancel_token.is_cancelled():
                terminate_process_tree(process)
                LOGGER.warning("Process cancelled: %s", command[0])
                process.wait()
                stdout_thread.join(timeout=2)
                stderr_thread.join(timeout=2)
                raise ProcessingCancelled
            # `poll()` is the non-blocking check. Do not use `wait(timeout=...)`
            # here: its TimeoutExpired exception is expected for long media jobs.
            time.sleep(0.1)
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
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        process.terminate()


class FfmpegMediaTool:
    def __init__(self, runner: ProcessRunner | None = None):
        self.runner = runner or ProcessRunner()

    def prepare_audio(self, input_path: Path, work_dir: Path, cancel_token: CancelToken, clip_start=None, clip_end=None) -> Path:
        if input_path.suffix.lower() == ".wav" and clip_start is None and clip_end is None:
            return input_path
        output = work_dir / "converted_audio.wav"
        seek_args = []
        if clip_start is not None:
            seek_args += ["-ss", str(clip_start)]
        if clip_end is not None:
            seek_args += ["-to", str(clip_end)]
        result = self.runner.run(
            ["ffmpeg", "-y", *seek_args, "-i", str(input_path), "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", str(output)],
            cancel_token,
        )
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg audio conversion failed: {result.stderr.strip()}")
        return output

    def extract_interval_frames(self, input_path, frames_dir, interval, cancel_token, clip_start=None, clip_end=None, highlight_times=()):
        frames_dir.mkdir(parents=True, exist_ok=True)
        seek_args = []
        if clip_start is not None:
            seek_args += ["-ss", str(clip_start)]
        if clip_end is not None:
            seek_args += ["-to", str(clip_end)]
        output_pattern = frames_dir / "frame_%06d.png"
        result = self.runner.run(
            ["ffmpeg", "-y", *seek_args, "-i", str(input_path), "-vf", f"fps=1/{max(1, interval)}", str(output_pattern)],
            cancel_token,
        )
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg frame extraction failed: {result.stderr.strip()}")
        for index, timestamp in enumerate(highlight_times, 1):
            if clip_start is not None and timestamp < clip_start:
                continue
            if clip_end is not None and timestamp > clip_end:
                continue
            frame = frames_dir / f"highlight_{index:03d}.png"
            result = self.runner.run(
                ["ffmpeg", "-y", "-ss", str(timestamp), "-i", str(input_path), "-frames:v", "1", str(frame)],
                cancel_token,
            )
            if result.returncode != 0:
                raise RuntimeError(f"FFmpeg highlighted frame extraction failed: {result.stderr.strip()}")
        return tuple(sorted(frames_dir.glob("*.png")))


class WhisperCliProvider:
    def __init__(self, runner: ProcessRunner | None = None, executable: str | None = None):
        self.runner = runner or ProcessRunner()
        self.executable = executable or find_whisper_executable() or "whisper"

    def transcribe(self, request, on_progress: Callable[[str], None], cancel_token: CancelToken):
        command = [self.executable, str(request.input_path), "--model", request.model, "--output_dir", str(request.output_dir), "--output_format", "all"]
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
