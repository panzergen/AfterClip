"""Evidence-preserving Whisper hallucination filtering (Phase 4 WS-C).

Whisper emits hallucinated text over silence/music/noise, repeated loops and
boilerplate. This module makes deterministic decisions on Whisper JSON segments
(which carry ``no_speech_prob``, ``avg_logprob`` and ``compression_ratio``) and
records every removed/flagged item so the raw transcript can always be kept.
"""

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

#: Common Whisper boilerplate hallucinations over silence/music.
DEFAULT_BLOCKLIST: tuple[str, ...] = (
    "thanks for watching",
    "thank you for watching",
    "please subscribe",
    "subscribe to",
    "amara.org",
    "subtitles by",
    "subtitle by",
    "transcription by",
)

_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class SanitizerConfig:
    enabled: bool = True
    no_speech_threshold: float = 0.6
    avg_logprob_threshold: float = -1.0
    compression_ratio_threshold: float = 2.4
    max_repetition: int = 3
    min_chars: int = 1
    blocklist: tuple[str, ...] = DEFAULT_BLOCKLIST

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "no_speech_threshold": self.no_speech_threshold,
            "avg_logprob_threshold": self.avg_logprob_threshold,
            "compression_ratio_threshold": self.compression_ratio_threshold,
            "max_repetition": self.max_repetition,
            "min_chars": self.min_chars,
            "blocklist": list(self.blocklist),
        }

    @classmethod
    def from_dict(cls, data: object) -> "SanitizerConfig":
        if not isinstance(data, dict):
            return cls()
        blocklist = data.get("blocklist")
        if not isinstance(blocklist, (list, tuple)) or not blocklist:
            blocklist = DEFAULT_BLOCKLIST

        def _float(key: str, default: float) -> float:
            try:
                return float(data.get(key, default))
            except (TypeError, ValueError):
                return default

        def _int(key: str, default: int) -> int:
            try:
                return int(data.get(key, default))
            except (TypeError, ValueError):
                return default

        return cls(
            enabled=bool(data.get("enabled", True)),
            no_speech_threshold=_float("no_speech_threshold", 0.6),
            avg_logprob_threshold=_float("avg_logprob_threshold", -1.0),
            compression_ratio_threshold=_float("compression_ratio_threshold", 2.4),
            max_repetition=_int("max_repetition", 3),
            min_chars=_int("min_chars", 1),
            blocklist=tuple(str(entry) for entry in blocklist),
        )


@dataclass(frozen=True)
class SegmentDecision:
    index: int
    start: float
    end: float
    text: str
    action: str  # "kept" | "removed" | "flagged"
    reason: str = ""


@dataclass
class SanitizeResult:
    kept: list[dict]
    decisions: list[SegmentDecision]

    @property
    def removed(self) -> list[SegmentDecision]:
        return [decision for decision in self.decisions if decision.action == "removed"]

    @property
    def flagged(self) -> list[SegmentDecision]:
        return [decision for decision in self.decisions if decision.action == "flagged"]

    def report(self) -> dict:
        return {
            "kept_count": len(self.kept),
            "removed_count": len(self.removed),
            "flagged_count": len(self.flagged),
            "removed": [asdict(decision) for decision in self.removed],
            "flagged": [asdict(decision) for decision in self.flagged],
        }


def _normalize(text: object) -> str:
    return _WHITESPACE.sub(" ", str(text)).strip().lower()


def _is_blocklisted(normalized: str, blocklist: tuple[str, ...]) -> bool:
    return any(phrase and phrase in normalized for phrase in blocklist)


def _is_repetition(segments: list[dict], index: int, max_repetition: int) -> bool:
    if max_repetition <= 1:
        return False
    current = _normalize(segments[index].get("text", ""))
    if not current:
        return False
    repeats = 1
    cursor = index - 1
    while (
        cursor >= 0
        and repeats < max_repetition
        and _normalize(segments[cursor].get("text", "")) == current
    ):
        repeats += 1
        cursor -= 1
    return repeats >= max_repetition


def _as_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def sanitize_segments(segments: list[dict], config: SanitizerConfig) -> SanitizeResult:
    """Classify each segment as kept/removed/flagged without dropping evidence."""
    kept: list[dict] = []
    decisions: list[SegmentDecision] = []
    for index, segment in enumerate(segments):
        text = str(segment.get("text", "")).strip()
        start = _as_float(segment.get("start"))
        end = _as_float(segment.get("end"))
        normalized = _normalize(text)
        no_speech = _as_float(segment.get("no_speech_prob"))
        logprob = _as_float(segment.get("avg_logprob"))
        compression = _as_float(segment.get("compression_ratio"))

        reason = ""
        if not normalized or len(normalized) < config.min_chars:
            reason = "empty"
        elif _is_blocklisted(normalized, config.blocklist):
            reason = "blocklist"
        elif no_speech >= config.no_speech_threshold:
            reason = "no_speech"
        elif compression >= config.compression_ratio_threshold:
            reason = "compression"
        elif _is_repetition(segments, index, config.max_repetition):
            reason = "repetition"

        if reason:
            decisions.append(SegmentDecision(index, start, end, text, "removed", reason))
            continue
        if logprob <= config.avg_logprob_threshold:
            decisions.append(SegmentDecision(index, start, end, text, "flagged", "low_logprob"))
        else:
            decisions.append(SegmentDecision(index, start, end, text, "kept"))
        kept.append(segment)
    return SanitizeResult(kept, decisions)


def load_segments(json_path) -> list[dict]:
    """Load Whisper JSON ``segments``; returns [] on any problem."""
    path = Path(json_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    segments = payload.get("segments", []) if isinstance(payload, dict) else []
    return [segment for segment in segments if isinstance(segment, dict)]


def _srt_timestamp(seconds: float) -> str:
    total_ms = max(0, round(seconds * 1000))
    hours, remainder = divmod(total_ms, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    secs, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


def render_srt(segments: list[dict]) -> str:
    blocks = []
    for number, segment in enumerate(segments, 1):
        start = _srt_timestamp(_as_float(segment.get("start")))
        end = _srt_timestamp(_as_float(segment.get("end")))
        text = str(segment.get("text", "")).strip()
        blocks.append(f"{number}\n{start} --> {end}\n{text}\n")
    return "\n".join(blocks)


def render_text(segments: list[dict]) -> str:
    return "\n".join(str(segment.get("text", "")).strip() for segment in segments)
