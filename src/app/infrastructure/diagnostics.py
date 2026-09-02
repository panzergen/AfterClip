from dataclasses import dataclass

from app.infrastructure.process import executable_available, find_whisper_executable


@dataclass(frozen=True)
class EnvironmentStatus:
    ffmpeg: bool
    ffprobe: bool
    whisper: bool


def check_environment() -> EnvironmentStatus:
    return EnvironmentStatus(
        ffmpeg=executable_available("ffmpeg"),
        ffprobe=executable_available("ffprobe"),
        whisper=find_whisper_executable() is not None,
    )
