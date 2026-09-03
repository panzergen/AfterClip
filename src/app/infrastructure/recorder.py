import subprocess
import logging
import re
from functools import lru_cache
import threading
from pathlib import Path

from app.infrastructure.process import CREATE_NO_WINDOW

LOGGER = logging.getLogger(__name__)


def list_microphone_devices() -> list[str]:
    try:
        result = subprocess.run(
            ["ffmpeg", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=CREATE_NO_WINDOW,
        )
    except OSError:
        return []
    return list(dict.fromkeys(re.findall(r'"([^"]+)"\s*\(audio\)', result.stderr)))


@lru_cache(maxsize=1)
def supports_system_audio() -> bool:
    try:
        result = subprocess.run(
            ["ffmpeg", "-formats"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", creationflags=CREATE_NO_WINDOW,
        )
        return "wasapi" in result.stdout.lower() or "wasapi" in result.stderr.lower()
    except OSError:
        return False


class AudioRecorder:
    """Small Windows-first FFmpeg recorder; device names are supplied by the UI."""

    def __init__(self):
        self.process = None
        self.output_path = None
        self.stderr_lines = []

    def start(self, output_path: Path, microphone: bool, system_audio: bool, microphone_device: str = "default"):
        if not microphone and not system_audio:
            raise ValueError("Select microphone audio, system audio, or both.")
        if system_audio and not supports_system_audio():
            raise RuntimeError("System audio recording is unavailable because this FFmpeg build has no WASAPI support.")
        if microphone and system_audio:
            command = [
                "ffmpeg", "-y", "-f", "dshow", "-i", f'audio={microphone_device}',
                "-f", "wasapi", "-i", "default", "-filter_complex", "amix=inputs=2:duration=longest",
                "-ac", "2", "-ar", "48000", str(output_path),
            ]
        elif microphone:
            command = ["ffmpeg", "-y", "-f", "dshow", "-i", f'audio={microphone_device}', "-ac", "1", "-ar", "16000", str(output_path)]
        else:
            command = ["ffmpeg", "-y", "-f", "wasapi", "-i", "default", "-ac", "2", "-ar", "48000", str(output_path)]
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", creationflags=CREATE_NO_WINDOW)
        self.output_path = output_path
        self.stderr_lines = []
        threading.Thread(target=self._drain_stderr, daemon=True).start()
        LOGGER.info("Started audio recording: %s", output_path)
        return output_path

    def stop(self):
        if not self.process:
            return None
        if self.process.poll() is None and self.process.stdin:
            self.process.stdin.write("q\n")
            self.process.stdin.flush()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        process = self.process
        output_path = self.output_path
        self.process = None
        self.output_path = None
        if process.returncode != 0 or not output_path.is_file() or output_path.stat().st_size == 0:
            detail = "".join(self.stderr_lines)
            LOGGER.error("Audio recording failed with exit code %s: %s", process.returncode, detail.strip())
            raise RuntimeError(f"FFmpeg could not create the recording. {detail.strip()[-500:]}")
        LOGGER.info("Audio recording saved: %s (%s bytes)", output_path, output_path.stat().st_size)
        return output_path

    def _drain_stderr(self):
        if self.process and self.process.stderr:
            for line in self.process.stderr:
                self.stderr_lines.append(line)
