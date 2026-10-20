"""Process time forecasting from historical job metrics (Phase 4 WS-H).

Groups previous jobs by configuration, then estimates the current job from the
per-second rate (total processing seconds / media seconds) of the most similar
jobs, reported as a median with a p10-p90 range. With too little history it
falls back to a clearly-labelled heuristic. Estimates never leave the machine.
"""

import json
import logging
import statistics
from dataclasses import dataclass
from pathlib import Path

LOGGER = logging.getLogger(__name__)

MIN_SAMPLES = 3
MAX_NEIGHBOURS = 12

# Cold-start fraction of media duration by Whisper model (very rough; hardware
# and GPU/CPU dominate, so this is only a "rough estimate").
HEURISTIC_FACTORS = {
    "tiny": 0.05,
    "base": 0.08,
    "small": 0.12,
    "medium": 0.20,
    "large": 0.30,
    "turbo": 0.25,
}
DEFAULT_HEURISTIC_FACTOR = 0.20


@dataclass(frozen=True)
class HistoricalJob:
    duration_seconds: float
    total_seconds: float
    model: str
    frame_modes: tuple[str, ...]
    analyze_text: bool
    analyze_vision: bool
    frame_resolution: str
    predicted_seconds: float | None = None

    @property
    def rate(self) -> float | None:
        if self.duration_seconds > 0 and self.total_seconds > 0:
            return self.total_seconds / self.duration_seconds
        return None


@dataclass(frozen=True)
class Forecast:
    available: bool
    expected_seconds: float | None
    low_seconds: float | None
    high_seconds: float | None
    sample_count: int
    basis: str  # "similar" | "model" | "history" | "heuristic" | "unknown"

    def text(self) -> str:
        if not self.available or self.expected_seconds is None:
            return ""
        expected = format_estimate(self.expected_seconds)
        if self.low_seconds is None or self.high_seconds is None:
            return f"Estimated {expected}"
        low = format_estimate(self.low_seconds).lstrip("~")
        high = format_estimate(self.high_seconds).lstrip("~")
        range_text = f"{expected} ({low}–{high})"
        if self.basis == "heuristic" or self.sample_count == 0:
            return f"Rough estimate {range_text}"
        return f"Estimated {range_text} · {self.sample_count} similar job(s)"


def format_estimate(seconds: float) -> str:
    minutes = max(0, round(seconds)) // 60
    if minutes < 1:
        return "under 1m"
    if minutes < 60:
        return f"~{minutes}m"
    hours, remainder = divmod(minutes, 60)
    return f"~{hours}h {remainder:02d}m" if remainder else f"~{hours}h"


def _as_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _history_from_state(state: dict) -> HistoricalJob | None:
    steps = state.get("steps", {})
    if not isinstance(steps, dict):
        return None
    total = sum(
        _as_float(step.get("duration_seconds")) for step in steps.values() if isinstance(step, dict)
    )
    if total <= 0:
        return None
    media = state.get("media") if isinstance(state.get("media"), dict) else {}
    settings = state.get("run_settings") if isinstance(state.get("run_settings"), dict) else {}
    modes = settings.get("frame_modes")
    modes = tuple(str(mode) for mode in modes) if isinstance(modes, (list, tuple)) else ()
    forecast_state = state.get("forecast") if isinstance(state.get("forecast"), dict) else {}
    predicted = _as_float(forecast_state.get("expected_seconds"))
    return HistoricalJob(
        duration_seconds=_as_float(media.get("duration")),
        total_seconds=total,
        model=str(settings.get("model", "")),
        frame_modes=modes,
        analyze_text=bool(settings.get("analyze_text")),
        analyze_vision=bool(settings.get("analyze_vision")),
        frame_resolution=str(settings.get("frame_resolution", "")),
        predicted_seconds=predicted if predicted > 0 else None,
    )


def load_history(output_dir: Path) -> list[HistoricalJob]:
    """Read past job metrics from ``job_state.json`` files ([] when none)."""
    jobs: list[HistoricalJob] = []
    if not output_dir.is_dir():
        return jobs
    for state_path in output_dir.glob("*/job_state.json"):
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            LOGGER.debug("Skipping history %s: %s", state_path, error)
            continue
        if isinstance(state, dict):
            job = _history_from_state(state)
            if job is not None:
                jobs.append(job)
    return jobs


def _is_similar(
    job: HistoricalJob,
    model: str,
    frame_modes: tuple[str, ...],
    analyze_text: bool,
    analyze_vision: bool,
) -> bool:
    return (
        job.model == model
        and job.frame_modes == frame_modes
        and job.analyze_text == analyze_text
        and job.analyze_vision == analyze_vision
    )


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    position = fraction * (len(values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def _self_correction_factor(jobs: list[HistoricalJob]) -> float:
    """Median actual/predicted ratio across jobs that stored a forecast.

    A ratio above 1.0 means past estimates ran under; below 1.0 over. Clamped
    to a sane band so a single outlier cannot swing the estimate wildly.
    """
    ratios = [job.total_seconds / job.predicted_seconds for job in jobs if job.predicted_seconds]
    if len(ratios) < MIN_SAMPLES:
        return 1.0
    return min(2.0, max(0.5, statistics.median(ratios)))


def forecast(
    duration_seconds: float,
    model: str,
    frame_modes: tuple[str, ...] = (),
    analyze_text: bool = False,
    analyze_vision: bool = False,
    frame_resolution: str = "",
    history: list[HistoricalJob] | None = None,
) -> Forecast:
    history = history or []
    if duration_seconds <= 0:
        return Forecast(False, None, None, None, 0, "unknown")

    modes = tuple(frame_modes)
    matches = [
        job
        for job in history
        if job.rate is not None and _is_similar(job, model, modes, analyze_text, analyze_vision)
    ]
    basis = "similar"
    if len(matches) < MIN_SAMPLES:
        matches = [job for job in history if job.rate is not None and job.model == model]
        basis = "model"
    if len(matches) < MIN_SAMPLES:
        matches = [job for job in history if job.rate is not None]
        basis = "history"

    if len(matches) >= MIN_SAMPLES:
        nearest = sorted(matches, key=lambda job: abs(job.duration_seconds - duration_seconds))[
            :MAX_NEIGHBOURS
        ]
        rates = sorted(job.rate for job in nearest if job.rate is not None)
        correction = _self_correction_factor(nearest)
        expected = statistics.median(rates) * duration_seconds * correction
        low = _percentile(rates, 0.1) * duration_seconds * correction
        high = _percentile(rates, 0.9) * duration_seconds * correction
        return Forecast(True, expected, low, high, len(nearest), basis)

    factor = HEURISTIC_FACTORS.get(model, DEFAULT_HEURISTIC_FACTOR)
    expected = duration_seconds * factor
    return Forecast(True, expected, expected * 0.6, expected * 1.8, 0, "heuristic")
