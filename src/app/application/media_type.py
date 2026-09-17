"""Media-type classification (Phase 4 WS-D).

Tier 1 is deterministic and instant (filename keywords, track layout, duration,
presence of a speaker VTT) so it can run on selection without freezing the UI
and never blocks a job. Tier 3 (an optional LLM pass over the signals) is parsed
separately; low confidence always falls back to the defaults.
"""

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

MEDIA_TYPES = (
    "meeting",
    "lecture",
    "interview",
    "tutorial",
    "webinar",
    "podcast",
    "presentation",
    "other",
)

KEYWORD_MAP: dict[str, tuple[str, ...]] = {
    "webinar": ("webinar",),
    "meeting": (
        "meeting", "standup", "stand-up", "weekly", "retro", "sync", "toplantı", "toplanti"
    ),
    "interview": ("interview", "mülakat", "mulakat"),
    "lecture": ("lecture", "ders", "seminar", "seminer", "course", "class"),
    "tutorial": ("tutorial", "howto", "how-to", "walkthrough", "screencast", "demo"),
    "podcast": ("podcast", "episode", "bölüm", "bolum"),
    "presentation": ("presentation", "sunum", "keynote", "talk"),
}

#: Frame-extraction mode suggested per media type.
FRAME_MODE_BY_TYPE = {
    "tutorial": "scene",
    "presentation": "scene",
    "lecture": "scene",
    "meeting": "interval",
    "webinar": "interval",
    "interview": "interval",
    "podcast": "interval",
}

CONFIDENT_THRESHOLD = 0.5

_WORD_PATTERN = re.compile(r"[^\W\d_]+", re.UNICODE)


@dataclass(frozen=True)
class MediaSignals:
    filename: str = ""
    duration_seconds: float = 0.0
    width: int = 0
    height: int = 0
    has_video: bool = False
    has_audio: bool = False
    has_support_vtt: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    def as_prompt_text(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


@dataclass(frozen=True)
class MediaTypeGuess:
    media_type: str = "other"
    confidence: float = 0.0
    tier: str = "tier1"
    signals: dict = field(default_factory=dict)
    suggested_frame_mode: str = "interval"
    suggested_preset: str = ""

    @property
    def confident(self) -> bool:
        return self.confidence >= CONFIDENT_THRESHOLD

    def to_dict(self) -> dict:
        return asdict(self)


def _keyword_scores(filename: str) -> dict[str, int]:
    lowered = filename.lower()
    words = {match.group(0).lower() for match in _WORD_PATTERN.finditer(lowered)}
    scores: dict[str, int] = {}
    for media_type, keywords in KEYWORD_MAP.items():
        hits = sum(
            1 for keyword in keywords if keyword in words or keyword in lowered
        )
        if hits:
            scores[media_type] = hits
    return scores


def signals_from_metadata(
    filename: str, metadata: dict, has_support_vtt: bool = False
) -> MediaSignals:
    streams = metadata.get("streams", []) if isinstance(metadata, dict) else []
    has_video = any(stream.get("type") == "video" for stream in streams)
    has_audio = any(stream.get("type") == "audio" for stream in streams)
    width = height = 0
    for stream in streams:
        if stream.get("type") == "video" and stream.get("width") and stream.get("height"):
            width, height = int(stream["width"]), int(stream["height"])
            break
    try:
        duration = float(metadata.get("duration"))
    except (TypeError, ValueError):
        duration = 0.0
    return MediaSignals(
        filename=Path(filename).name,
        duration_seconds=duration,
        width=width,
        height=height,
        has_video=has_video,
        has_audio=has_audio,
        has_support_vtt=has_support_vtt,
    )


def classify_tier1(signals: MediaSignals) -> MediaTypeGuess:
    """Instant deterministic guess from filename and track layout."""
    scores = _keyword_scores(signals.filename)
    media_type = "other"
    confidence = 0.0
    if scores:
        media_type = max(scores, key=lambda key: (scores[key], key))
        confidence = min(0.9, 0.55 + 0.15 * scores[media_type])
    elif signals.has_support_vtt and signals.has_video and signals.duration_seconds >= 600:
        media_type, confidence = "meeting", 0.5
    elif signals.has_audio and not signals.has_video and signals.duration_seconds >= 1200:
        media_type, confidence = "podcast", 0.4
    elif signals.has_video and 0 < signals.duration_seconds <= 900:
        media_type, confidence = "tutorial", 0.35
    if signals.has_support_vtt and media_type in {"meeting", "webinar", "interview"}:
        confidence = min(0.95, confidence + 0.1)
    return MediaTypeGuess(
        media_type=media_type,
        confidence=round(confidence, 2),
        tier="tier1",
        signals=signals.to_dict(),
        suggested_frame_mode=FRAME_MODE_BY_TYPE.get(media_type, "interval"),
        suggested_preset=media_type if media_type != "other" else "",
    )


def parse_classification_output(text: str) -> dict | None:
    """Parse a Tier-3 LLM reply into {media_type, confidence, reason}."""
    if not text:
        return None
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    media_type = str(payload.get("media_type", "other")).strip().lower()
    if media_type not in MEDIA_TYPES:
        media_type = "other"
    try:
        confidence = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "media_type": media_type,
        "confidence": max(0.0, min(1.0, confidence)),
        "reason": str(payload.get("reason", "")),
    }


def merge_tier3(base: MediaTypeGuess, parsed: dict) -> MediaTypeGuess:
    """Overlay an LLM classification on the Tier-1 guess."""
    media_type = parsed.get("media_type") or base.media_type
    confidence = float(parsed.get("confidence") or 0.0)
    return MediaTypeGuess(
        media_type=media_type,
        confidence=round(confidence, 2),
        tier="tier3",
        signals={**base.signals, "reason": parsed.get("reason", "")},
        suggested_frame_mode=FRAME_MODE_BY_TYPE.get(media_type, "interval"),
        suggested_preset=media_type if media_type != "other" else "",
    )
