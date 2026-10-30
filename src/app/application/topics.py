"""Topic-change segmentation (Phase 4 WS-I).

Deterministic lexical-cohesion baseline over the merged transcript paragraphs,
plus helpers to render sections into ``Topics.md``/``Topics.json`` and to
insert headings into the Master Timeline, the HTML report and AI analysis.

An optional AI pass can replace titles later; it always falls back to this
baseline, and disabling the feature leaves existing outputs unchanged.
"""

import json
import logging
import re
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from app.application.language import (
    detect_language,
    language_label,
    language_name,
    language_verdict,
    normalize_code,
)
from app.application.summary import looks_like_preamble
from app.domain.models import TimelineEntry
from app.domain.prompts import PromptSet
from app.infrastructure.llm.transport import clean_thinking_tags

LOGGER = logging.getLogger(__name__)

TOPIC_METHODS = ("off", "cohesion", "ai")
DEFAULT_TOPIC_METHOD = "ai"
DEFAULT_TOPIC_MIN_SECONDS = 60.0
# 0 means "auto": derive a cap from the media duration so long recordings can
# split well past the one-hour mark instead of lumping the tail together.
DEFAULT_TOPIC_MAX_SECTIONS = 0
DEFAULT_BOUNDARY_SCORE = 0.55


def auto_max_sections(duration_seconds: float) -> int:
    """Cap sections at roughly one per minute, bounded to a sane range."""
    if duration_seconds <= 0:
        return 1
    return max(4, min(120, int(duration_seconds / 60)))


_WORD_PATTERN = re.compile(r"[^\W\d_]+", re.UNICODE)

STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "if",
        "then",
        "so",
        "to",
        "of",
        "in",
        "on",
        "at",
        "for",
        "with",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "it",
        "its",
        "this",
        "that",
        "these",
        "those",
        "i",
        "you",
        "he",
        "she",
        "we",
        "they",
        "them",
        "his",
        "her",
        "our",
        "your",
        "their",
        "not",
        "no",
        "yes",
        "ok",
        "okay",
        "just",
        "very",
        "really",
        "like",
        "about",
        "bir",
        "bu",
        "şu",
        "o",
        "ve",
        "ile",
        "için",
        "de",
        "da",
        "ki",
        "mi",
        "mı",
        "mu",
        "mü",
        "ne",
        "çok",
        "daha",
        "ama",
        "ancak",
        "gibi",
        "kadar",
        "evet",
        "tamam",
        "yani",
        "şey",
        "şeyi",
        "var",
        "yok",
        "ben",
        "sen",
        "biz",
        "siz",
    }
)


@dataclass(frozen=True)
class TopicSegment:
    start_ms: int
    end_ms: int
    start_str: str
    end_str: str
    title: str

    def to_dict(self) -> dict:
        return asdict(self)


def _tokens(text: str) -> set[str]:
    words = (match.group(0).lower() for match in _WORD_PATTERN.finditer(text))
    return {word for word in words if len(word) > 2 and word not in STOPWORDS}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    union = left | right
    return len(left & right) / len(union) if union else 1.0


def _title_for(entry: TimelineEntry, max_chars: int = 64) -> str:
    text = " ".join(entry.text.split())
    if len(text) <= max_chars:
        return text or "(untitled section)"
    truncated = text[:max_chars].rsplit(" ", 1)[0].strip()
    return f"{truncated or text[:max_chars]}…"


def _make_segment(block: list[TimelineEntry]) -> TopicSegment:
    first, last = block[0], block[-1]
    return TopicSegment(
        first.start_ms, last.end_ms, first.start_str, last.end_str, _title_for(first)
    )


def segment_topics_cohesion(
    entries: tuple[TimelineEntry, ...],
    min_seconds: float = DEFAULT_TOPIC_MIN_SECONDS,
    max_sections: int | None = None,
    min_score: float = DEFAULT_BOUNDARY_SCORE,
) -> list[TopicSegment]:
    """Split merged transcript blocks at the strongest lexical-cohesion valleys.

    Boundaries are monotonic and non-overlapping; a minimum section length and a
    maximum section count keep the result readable. ``max_sections=None`` derives
    the cap from the media duration.
    """
    if not entries:
        return []
    if len(entries) == 1:
        return [_make_segment(list(entries))]
    if max_sections is None:
        total_seconds = (entries[-1].end_ms - entries[0].start_ms) / 1000
        max_sections = auto_max_sections(total_seconds)
    max_sections = max(1, int(max_sections))

    token_sets = [_tokens(entry.text) for entry in entries]
    candidates: list[tuple[int, float]] = []
    for index in range(1, len(entries)):
        score = 1.0 - _jaccard(token_sets[index - 1], token_sets[index])
        candidates.append((index, score))
    candidates.sort(key=lambda item: item[1], reverse=True)

    chosen: list[int] = []
    for index, score in candidates:
        if len(chosen) >= max_sections - 1:
            break
        if score < min_score:
            break
        # Keep the first and last sections at least min_seconds long, and space
        # every other boundary out by the same minimum.
        if entries[index].start_ms < min_seconds * 1000:
            continue
        if entries[-1].end_ms - entries[index].start_ms < min_seconds * 1000:
            continue
        if any(
            abs(entries[index].start_ms - entries[other].start_ms) < min_seconds * 1000
            for other in chosen
        ):
            continue
        chosen.append(index)
    chosen.sort()

    segments: list[TopicSegment] = []
    previous = 0
    for index in chosen:
        segments.append(_make_segment(list(entries[previous:index])))
        previous = index
    segments.append(_make_segment(list(entries[previous:])))
    return segments


def topic_boundary_map(topics: list[TopicSegment]) -> dict[int, TopicSegment]:
    """Map each section's start_ms to its segment (for heading insertion)."""
    return {topic.start_ms: topic for topic in topics}


def render_topics_markdown(topics: list[TopicSegment]) -> str:
    lines = ["# Topics\n\n"]
    for number, topic in enumerate(topics, 1):
        lines.append(f"{number}. `[{topic.start_str} --> {topic.end_str}]` {topic.title}\n")
    return "".join(lines)


def write_topics(job_dir: Path, topics: list[TopicSegment]) -> tuple[Path, Path]:
    markdown_path = job_dir / "Topics.md"
    json_path = job_dir / "Topics.json"
    markdown_path.write_text(render_topics_markdown(topics), encoding="utf-8")
    json_path.write_text(
        json.dumps([topic.to_dict() for topic in topics], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return markdown_path, json_path


def render_topics_summary(topics: list[TopicSegment]) -> str:
    """Compact list used inside AI_Analysis.md and the HTML report."""
    return "\n".join(
        f"- `[{topic.start_str} --> {topic.end_str}]` {topic.title}" for topic in topics
    )


def _section_text(entries: tuple[TimelineEntry, ...], section: TopicSegment) -> str:
    parts = [
        entry.text.strip()
        for entry in entries
        if section.start_ms <= entry.start_ms < section.end_ms and entry.text.strip()
    ]
    return " ".join(parts)


def _clean_title(text: str, max_words: int = 12) -> str:
    lines = [line.strip().strip("\"'` ").strip() for line in text.strip().splitlines()]
    first_line = ""
    for line in lines:
        if not line:
            continue
        if looks_like_preamble(line):
            continue
        first_line = line
        break
    if not first_line:
        for line in lines:
            if line:
                first_line = line
                break
    words = first_line.split()
    return " ".join(words[:max_words]) if words else ""


def _wrong_language(title: str, language: str) -> bool:
    """True only when the title is clearly written in another language."""
    return language_verdict(title, language) is False


_NUMBERED_LINE = re.compile(r"^\s*\d+[.)]\s+(.+?)\s*$", re.MULTILINE)


def _parse_title_array(raw: str | None, count: int) -> list[str] | None:
    """Parse a JSON array (or a numbered list) of titles; ``None`` if unusable."""
    text = clean_thinking_tags(raw or "").strip()
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end > start:
        try:
            values = json.loads(text[start : end + 1])
        except (json.JSONDecodeError, ValueError):
            values = None
        if isinstance(values, list) and len(values) == count:
            if all(isinstance(value, str) for value in values):
                titles = [value.strip() for value in values]
            elif all(isinstance(value, dict) for value in values):
                titles = [
                    str(value.get("title") or value.get("text") or "").strip()
                    for value in values
                ]
            else:
                titles = []
            if titles and all(titles):
                return titles
    lines = _NUMBERED_LINE.findall(text)
    if len(lines) == count and all(line.strip() for line in lines):
        return [line.strip().strip("\"'`") for line in lines]
    return None


def _translation_prompt(titles: list[str], language: str) -> str:
    label = language_label(language)
    numbered = "\n".join(f"{number}. {title}" for number, title in enumerate(titles, 1))
    return (
        f"Rewrite every numbered title below in {label}. Keep the meaning, keep "
        "product and brand names unchanged, and keep each title short (3-8 words). "
        f"Return ONLY a JSON array of {len(titles)} strings in the same order, "
        "no prose and no explanation.\n\n"
        f"Titles:\n{numbered}"
    )


def _translate_one_prompt(title: str, language: str) -> str:
    target = language_name(language)
    source = detect_language(title)
    if source and source != language:
        opening = (
            f"The title below is written in {language_name(source)}. "
            f"Translate it into {target}."
        )
    else:
        opening = f"The title below is not in {target}. Translate it into {target}."
    return (
        f"{opening} Do not repeat the input. Keep product and brand names "
        "unchanged and return ONLY the translated title.\n\n"
        f"Title: {title}"
    )


#: Titles per translation request: a long job can have a hundred sections, and
#: a single oversized answer would hit the model's output limit.
TRANSLATION_BATCH = 20


def _normalise_titles(
    titles: list[str],
    language: str,
    generate,
    cancel_token=None,
) -> list[str]:
    """Rewrite titles that came back in another language than requested."""
    if not language:
        return titles
    result = list(titles)
    wrong = [index for index, title in enumerate(result) if _wrong_language(title, language)]
    if not wrong:
        return result
    remaining: list[int] = []
    for offset in range(0, len(wrong), TRANSLATION_BATCH):
        group = wrong[offset : offset + TRANSLATION_BATCH]
        try:
            raw = generate(
                _translation_prompt([result[index] for index in group], language), cancel_token
            )
        except Exception as error:  # a provider outage must not cost one call per title
            LOGGER.debug("Topic title translation failed: %s", error)
            return result
        translated = _parse_title_array(raw, len(group))
        if not translated:
            remaining.extend(group)
            continue
        for index, candidate in zip(group, translated, strict=True):
            cleaned = _clean_title(candidate)
            if cleaned and not _wrong_language(cleaned, language):
                result[index] = cleaned
            else:
                remaining.append(index)
    for index in remaining:
        try:
            raw = generate(_translate_one_prompt(result[index], language), cancel_token)
        except Exception as error:
            LOGGER.debug("Topic title translation retry failed: %s", error)
            break
        cleaned = _clean_title(raw or "")
        if cleaned and not _wrong_language(cleaned, language):
            result[index] = cleaned
        else:
            LOGGER.warning(
                "Topic title stayed in another language than '%s': %s", language, result[index]
            )
    return result


def retitle_with_provider(
    topics: list[TopicSegment],
    entries: tuple[TimelineEntry, ...],
    provider,
    prompts=None,
    language: str = "en",
    cancel_token=None,
) -> list[TopicSegment]:
    """Replace heuristic titles with short AI titles in the report language.

    A title that comes back in another language (the model copied the section's
    language instead of following ``{lang}``) is translated once as a batch and
    then individually; the old title is only kept when every attempt fails.
    """
    generate = getattr(provider, "generate", None)
    if not callable(generate):
        return list(topics)
    prompt_set = prompts if prompts is not None else getattr(provider, "prompts", None)
    if prompt_set is None:
        prompt_set = PromptSet()
    language = normalize_code(language) or "en"
    titled: list[TopicSegment] = []
    generated: list[int] = []
    titles: list[str] = []
    for topic in topics:
        content = _section_text(entries, topic)
        if not content:
            titled.append(topic)
            continue
        prompt = prompt_set.render("topic_title", lang=language, content=content[:1500])
        try:
            raw = generate(prompt, cancel_token)
        except Exception:  # a title failure must never drop the section
            titled.append(topic)
            continue
        title = _clean_title(raw or "")
        if title:
            generated.append(len(titled))
            titles.append(title)
        titled.append(replace(topic, title=title) if title else topic)
    if generated:
        normalised = _normalise_titles(titles, language, generate, cancel_token)
        for position, title in zip(generated, normalised, strict=True):
            titled[position] = replace(titled[position], title=title)
    return titled
