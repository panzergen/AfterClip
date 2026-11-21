"""Preflight duration checks for a selected media file.

A container can advertise a long duration while its audio/video payload is
truncated (a broken export, an interrupted download, a partial screen
recording). Whisper then transcribes only the decodable part and the report
silently covers less than the user expects. This module compares the container
duration, the duration of the audio AfterClip actually extracts, and an optional
VTT duration before a job starts.

Only durations are compared; nothing is uploaded or modified.
"""

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.application.cancellation import CancellationToken
from app.application.timeline import vtt_duration_seconds
from app.infrastructure.process import FfmpegMediaTool, get_media_metadata

LOGGER = logging.getLogger(__name__)

DEFAULT_TOLERANCE = 0.05


@dataclass(frozen=True)
class DurationIssue:
    """Two measured durations that differ by more than the tolerance."""

    left_label: str
    left_seconds: float
    right_label: str
    right_seconds: float

    @property
    def difference_ratio(self) -> float:
        larger = max(self.left_seconds, self.right_seconds)
        if larger <= 0:
            return 0.0
        return abs(self.left_seconds - self.right_seconds) / larger


@dataclass(frozen=True)
class MediaDurationReport:
    video_seconds: float | None
    audio_seconds: float | None
    vtt_seconds: float | None
    issues: tuple[DurationIssue, ...]
    video_label: str = "Video metadata"
    tolerance: float = DEFAULT_TOLERANCE

    @property
    def has_warning(self) -> bool:
        return bool(self.issues)

    @property
    def shortest(self) -> tuple[str, float] | None:
        candidates = (
            (self.video_label, self.video_seconds),
            ("Processed audio", self.audio_seconds),
            ("VTT", self.vtt_seconds),
        )
        measured = [(label, seconds) for label, seconds in candidates if seconds and seconds > 0]
        return min(measured, key=lambda item: item[1]) if measured else None


def compare_durations(
    video_seconds: float | None,
    audio_seconds: float | None,
    vtt_seconds: float | None,
    *,
    tolerance: float = DEFAULT_TOLERANCE,
    video_label: str = "Video metadata",
) -> tuple[DurationIssue, ...]:
    """Return every pair whose lengths differ by more than ``tolerance``.

    ``tolerance`` is a fraction of the longer duration (0.05 = 5%). Missing or
    zero durations are ignored rather than treated as mismatches.
    """
    pairs = (
        (video_label, video_seconds, "Processed audio", audio_seconds),
        (video_label, video_seconds, "VTT", vtt_seconds),
        ("Processed audio", audio_seconds, "VTT", vtt_seconds),
    )
    issues: list[DurationIssue] = []
    for left_label, left, right_label, right in pairs:
        if left is None or right is None or left <= 0 or right <= 0:
            continue
        larger = max(left, right)
        if abs(left - right) / larger > tolerance:
            issues.append(
                DurationIssue(
                    left_label=left_label,
                    left_seconds=float(left),
                    right_label=right_label,
                    right_seconds=float(right),
                )
            )
    return tuple(issues)


def check_media_durations(
    input_path: Path,
    *,
    video_seconds: float | None = None,
    clip_start: float | None = None,
    clip_end: float | None = None,
    vtt_path: str = "",
    tolerance: float = DEFAULT_TOLERANCE,
) -> MediaDurationReport:
    """Measure the source, the extracted audio and the optional VTT.

    The audio is extracted to a temporary folder and removed immediately; the
    real job still performs its normal media preparation afterwards.
    """
    input_path = Path(input_path)
    full_duration = _positive(video_seconds) or _metadata_duration(input_path)
    clipped = clip_start is not None or clip_end is not None
    if clipped:
        start = float(clip_start or 0.0)
        end = float(clip_end) if clip_end is not None else full_duration
        expected_video = (end - start) if end is not None and end > start else None
        video_label = "Requested clip"
        vtt_seconds = None
    else:
        expected_video = full_duration
        video_label = "Video metadata"
        vtt_seconds = vtt_duration_seconds(vtt_path)

    audio_seconds = _probe_audio_duration(input_path, clip_start, clip_end)
    issues = compare_durations(
        expected_video,
        audio_seconds,
        vtt_seconds,
        tolerance=tolerance,
        video_label=video_label,
    )
    if issues:
        LOGGER.warning(
            "Media duration mismatch for %s: video=%s audio=%s vtt=%s",
            input_path,
            expected_video,
            audio_seconds,
            vtt_seconds,
        )
    return MediaDurationReport(
        video_seconds=expected_video,
        audio_seconds=audio_seconds,
        vtt_seconds=vtt_seconds,
        issues=issues,
        video_label=video_label,
        tolerance=tolerance,
    )


def _probe_audio_duration(
    input_path: Path, clip_start: float | None, clip_end: float | None
) -> float | None:
    if input_path.suffix.lower() == ".wav" and clip_start is None and clip_end is None:
        return _metadata_duration(input_path)
    try:
        with tempfile.TemporaryDirectory(prefix="afterclip-duration-") as work_dir:
            audio_path = FfmpegMediaTool().prepare_audio(
                input_path,
                Path(work_dir),
                CancellationToken(),
                clip_start=clip_start,
                clip_end=clip_end,
            )
            return _metadata_duration(audio_path)
    except Exception as error:  # a probe failure must not block the job itself
        LOGGER.warning("Could not measure processed audio duration for %s: %s", input_path, error)
        return None


def _metadata_duration(path: Path) -> float | None:
    return _positive(get_media_metadata(path).get("duration"))


def _positive(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None
