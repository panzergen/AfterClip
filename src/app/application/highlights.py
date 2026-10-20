"""Highlight extraction post-processing.

Each transcription chunk is scored by the model into a compact JSON array of
candidates; this module parses those (tolerating prose and malformed output)
and collapses them into a short, globally-ranked bullet list — at most one
highlight per five-minute window and at most three in total.
"""

import json
import re

from app.infrastructure.llm.transport import clean_thinking_tags

MIN_SCORE = 7.0
WINDOW_SECONDS = 300
MAX_HIGHLIGHTS = 3

_NON_ALNUM = re.compile(r"[^\w]+", re.UNICODE)


def parse_candidates(chunk_text: str) -> list[dict]:
    """Extract highlight-candidate objects from a chunk of model output.

    Tolerates prose, markdown fences and malformed JSON; returns an empty list
    when nothing parseable is found.
    """
    if not chunk_text:
        return []
    cleaned = clean_thinking_tags(chunk_text)
    values = _extract_json_arrays(cleaned)
    if not values:
        stripped = cleaned.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
            except (json.JSONDecodeError, ValueError):
                parsed = None
            if parsed is not None:
                values.append(parsed)
    candidates: list[dict] = []
    for value in values:
        _collect(value, candidates)
    return candidates


def aggregate_highlights(candidates: list[dict]) -> str:
    """Collapse scored candidates into the final bullet/timestamp list."""
    scored = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        title = str(candidate.get("title") or "").strip()
        if not title:
            continue
        try:
            score = float(candidate.get("score", 0))
        except (TypeError, ValueError):
            score = 0.0
        if score < MIN_SCORE:
            continue
        scored.append((candidate, title, score))

    deduped = []
    seen = set()
    for candidate, title, score in scored:
        key = _dedupe_key(title)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((candidate, score))

    best_in_window = {}
    for index, (candidate, score) in enumerate(deduped):
        seconds = _to_seconds(str(candidate.get("start") or ""))
        bucket = seconds // WINDOW_SECONDS if seconds is not None else ("unparsed", index)
        current = best_in_window.get(bucket)
        if current is None or score > current[1]:
            best_in_window[bucket] = (candidate, score)

    ranked = sorted(best_in_window.values(), key=lambda item: item[1], reverse=True)
    return _render_highlights([candidate for candidate, _ in ranked[:MAX_HIGHLIGHTS]])


def _extract_json_arrays(text: str) -> list:
    arrays = []
    start = 0
    while True:
        open_index = text.find("[", start)
        if open_index == -1:
            break
        depth = 0
        in_string = False
        escaped = False
        close_index = -1
        for index in range(open_index, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "[":
                depth += 1
            elif char == "]":
                depth -= 1
                if depth == 0:
                    close_index = index
                    break
        if close_index == -1:
            break
        raw = text[open_index : close_index + 1]
        try:
            arrays.append(json.loads(raw))
        except (json.JSONDecodeError, ValueError):
            pass
        start = close_index + 1
    return arrays


def _collect(value, out: list) -> None:
    if isinstance(value, dict):
        if {"title", "start", "score"} & value.keys():
            out.append(value)
        else:
            for nested in value.values():
                _collect(nested, out)
    elif isinstance(value, list):
        for nested in value:
            _collect(nested, out)


def _dedupe_key(title: str) -> str:
    return _NON_ALNUM.sub(" ", title.lower()).strip()


def _to_seconds(text: str) -> int | None:
    value = text.strip()
    if not value:
        return None
    if "." in value:
        value = value.split(".", 1)[0]
    elif "," in value:
        value = value.split(",", 1)[0]
    parts = value.split(":")
    if not 1 <= len(parts) <= 3 or not all(part.isdigit() for part in parts):
        return None
    numbers = [int(part) for part in parts]
    while len(numbers) < 3:
        numbers.insert(0, 0)
    return numbers[0] * 3600 + numbers[1] * 60 + numbers[2]


def _render_highlights(candidates: list[dict]) -> str:
    lines = []
    for candidate in candidates:
        start = str(candidate.get("start") or "").strip()
        title = str(candidate.get("title") or "").strip()
        lines.append(f"- {start} {title}" if start else f"- {title}")
    return "\n".join(lines)
