from dataclasses import dataclass
from enum import Enum
from pathlib import Path

"""Domain objects shared by every layer.

TranscriptionRequest field groups:
- Input/output: input_path, output_dir, output_name
- Whisper: model, language (transcription source language hint)
- Clip: clip_start, clip_end
- Frames: extract_frames, frame_interval, frame_modes, frame_mode, scene_sensitivity,
  frame_resolution, highlight_times, embed_frames
- AI analysis: analyze_text, analysis_model, analyze_vision, vision_model, output_language
  (output_language is the report language for summaries/highlights/vision text and is
  independent of the transcription language; empty falls back to `language`)
- Timeline: speaker_vtt_path, transcript_merge_seconds
- Misc: user_task
"""


class JobState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    CANCELLING = "cancelling"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class TranscriptionRequest:
    input_path: Path
    output_dir: Path
    model: str = "turbo"
    language: str = ""
    user_task: str = ""
    clip_start: float | None = None
    clip_end: float | None = None
    extract_frames: bool = False
    frame_interval: int = 10
    highlight_times: tuple[float, ...] = ()
    output_name: str = ""
    frame_mode: str = "interval"
    scene_sensitivity: float = 0.35
    frame_modes: tuple[str, ...] = ()
    speaker_vtt_path: str = ""
    analyze_text: bool = False
    analysis_model: str = ""
    analyze_vision: bool = False
    vision_model: str = ""
    embed_frames: bool = False
    frame_resolution: str = "full"
    transcript_merge_seconds: float | None = None
    output_language: str = ""
    support_files: tuple[str, ...] = ()


@dataclass(frozen=True)
class TranscriptionResult:
    output_dir: Path
    transcript_files: tuple[Path, ...]


@dataclass(frozen=True)
class ProgressEvent:
    message: str
    percent: int | None = None


@dataclass(frozen=True)
class SpeakerInterval:
    start_ms: int
    end_ms: int
    speaker: str


@dataclass(frozen=True)
class TimelineEntry:
    start_ms: int
    end_ms: int
    start_str: str
    end_str: str
    context_type: str
    text: str
