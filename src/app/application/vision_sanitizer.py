"""Deterministic cleanup for AI vision descriptions (mirrors transcript_sanitizer).

Small vision models degenerate into repetition loops when asked to enumerate UI
elements ("... sekmesinin hemen yanında, adres çubuğunun hemen yanında, ...")
without ever stopping. This module collapses such loops inside a single frame
description and enforces a hard length ceiling. It never drops the frame: only
the text is shortened, and a description is left untouched when nothing is
detected. All decisions are deterministic (no model calls), so the added cost
is a few regex passes per frame.
"""

import re
from dataclasses import dataclass

_WHITESPACE = re.compile(r"\s+")
_CLAUSE_SPLIT = re.compile(r"(?<=[,;.!?])\s+")
_TRAILING_PUNCT = re.compile(r"[\s,;.!?:]+$")
_ELLIPSIS = " \u2026"
#: Only cycles this short are considered loops (a drift loop is always short).
_MAX_PERIOD = 8
#: Isolated mismatches (model drift) are tolerated up to this many in a row.
_MAX_GAP = 2
#: A loop region must still match itself this often, so ordinary text is safe.
_MIN_MATCH_RATIO = 0.6


@dataclass(frozen=True)
class VisionSanitizerConfig:
    enabled: bool = True
    #: A clause run must repeat at least this many times to count as a loop.
    max_repetition: int = 3
    #: How many repetitions to keep after a loop is collapsed.
    keep_cycles: int = 1
    #: Hard upper bound; longer descriptions are cut at a clause boundary.
    #: Real frame descriptions run to ~1.5k chars, so this only bites runaways.
    max_chars: int = 3000

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "max_repetition": self.max_repetition,
            "keep_cycles": self.keep_cycles,
            "max_chars": self.max_chars,
        }

    @classmethod
    def from_dict(cls, data: object) -> "VisionSanitizerConfig":
        if not isinstance(data, dict):
            return cls()

        def _int(key: str, default: int) -> int:
            try:
                return int(data.get(key, default))
            except (TypeError, ValueError):
                return default

        return cls(
            enabled=bool(data.get("enabled", True)),
            max_repetition=max(2, _int("max_repetition", 3)),
            keep_cycles=max(1, _int("keep_cycles", 1)),
            max_chars=max(1, _int("max_chars", 3000)),
        )


@dataclass(frozen=True)
class VisionSanitizeResult:
    text: str
    changed: bool = False
    reason: str = ""
    original_chars: int = 0


def _normalize(text: object) -> str:
    return _WHITESPACE.sub(" ", str(text)).strip()


def _clauses(text: str) -> list[str]:
    return [part.strip() for part in _CLAUSE_SPLIT.split(text) if part.strip()]


def _clause_key(clause: str) -> str:
    """Comparable clause form: lowercase, punctuation stripped, spaces merged.

    Only casing and trailing punctuation are normalised so two genuinely
    different clauses (for example a list of names) never compare equal.
    """
    return _TRAILING_PUNCT.sub("", _WHITESPACE.sub(" ", clause.lower())).strip()


def _periodic_suffix(
    keys: list[str], max_repetition: int, keep_cycles: int
) -> tuple[int, int] | None:
    """Longest looped clause suffix -> (period, start); None when none found.

    ``start`` is the first clause of the loop; ``clauses[start:]`` is ``period``
    clauses repeated at least ``max_repetition`` times. Small models drift mid
    loop (a garbled word, a missing half clause), so up to ``_MAX_GAP``
    consecutive mismatching clauses are tolerated. The region is only accepted
    when it still agrees with itself at least ``_MIN_MATCH_RATIO`` of the time,
    which keeps ordinary enumerations from being mistaken for a loop.
    """
    count = len(keys)
    best: tuple[int, int, int] | None = None  # (removed, period, start)
    for period in range(1, min(_MAX_PERIOD, count // max_repetition) + 1):
        start = 0
        gap = 0
        for index in range(period, count):
            if keys[index] == keys[index - period]:
                gap = 0
            else:
                gap += 1
                if gap > _MAX_GAP:
                    start = index + 1
        compared = count - start - period
        if compared <= 0:
            continue
        matches = sum(1 for i in range(start + period, count) if keys[i] == keys[i - period])
        if matches / compared < _MIN_MATCH_RATIO:
            continue
        repeats = (count - start) // period
        if repeats < max_repetition:
            continue
        removed = (count - start) - period * keep_cycles
        if removed <= 0:
            continue
        if best is None or removed > best[0] or (removed == best[0] and period < best[1]):
            best = (removed, period, start)
    if best is None:
        return None
    return best[1], best[2]


def _truncate(text: str, limit: int) -> str:
    head = text[:limit]
    boundary = max(
        head.rfind(". "), head.rfind(", "), head.rfind("; "), head.rfind("! "), head.rfind("? ")
    )
    if boundary >= limit // 2:
        return head[: boundary + 1].rstrip() + _ELLIPSIS
    space = head.rfind(" ")
    if space > 0:
        head = head[:space]
    return head.rstrip() + _ELLIPSIS


def sanitize_description(
    text: object, config: VisionSanitizerConfig | None = None
) -> VisionSanitizeResult:
    """Collapse repetition loops and cap length in one frame description."""
    config = config or VisionSanitizerConfig()
    original = str(text or "")
    normalized = _normalize(original)
    if not config.enabled or not normalized:
        return VisionSanitizeResult(normalized, False, "", len(original))

    reason = ""
    clauses = _clauses(normalized)
    if len(clauses) >= config.max_repetition:
        found = _periodic_suffix(
            [_clause_key(clause) for clause in clauses],
            config.max_repetition,
            config.keep_cycles,
        )
        if found:
            period, start = found
            kept = clauses[:start] + clauses[start : start + period * config.keep_cycles]
            normalized = " ".join(kept).rstrip(" ,;")
            reason = "repetition"

    if len(normalized) > config.max_chars:
        normalized = _truncate(normalized, config.max_chars)
        reason = reason or "length"

    return VisionSanitizeResult(normalized, normalized != original, reason, len(original))
