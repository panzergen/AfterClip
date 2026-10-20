"""Prompt templates as data (Phase 4 WS-B).

Templates use named placeholders in braces, e.g. ``{transcript}``. Rendering
uses explicit token replacement, never ``str.format``, so an edited template or
media text containing braces can never raise or expose object attributes.
"""

import re
from dataclasses import dataclass, replace

# Placeholders each template may use. Validation rejects unknown placeholders
# and templates missing a required one.
TEMPLATE_PLACEHOLDERS: dict[str, frozenset[str]] = {
    "summary": frozenset({"lang", "transcript"}),
    "summary_combine": frozenset({"lang", "summaries"}),
    "highlights": frozenset({"lang", "srt_content"}),
    "vision_frame": frozenset({"user_desc", "audio_context", "lang"}),
    "media_type_classification": frozenset({"signals"}),
    "transcript_cleanup": frozenset({"lang", "transcript"}),
    "review_revision": frozenset({"lang", "instructions", "content"}),
    "topic_segmentation": frozenset({"lang", "transcript"}),
    "topic_title": frozenset({"lang", "content"}),
}

TEMPLATE_NAMES: tuple[str, ...] = tuple(TEMPLATE_PLACEHOLDERS)

DEFAULT_PROMPTS: dict[str, str] = {
    "summary": (
        "Below is an audio transcript section from a recording. "
        "Please provide a concise, structured executive summary of what is discussed.\n"
        "CRITICAL REQUIREMENT: Do NOT output any thinking, reasoning steps, or internal "
        "monologue. Output ONLY the final summary.\n"
        "CRITICAL REQUIREMENT: You MUST write your response entirely in the language "
        "corresponding to language code '{lang}'.\n\n"
        "Transcript:\n{transcript}"
    ),
    "summary_combine": (
        "Below are partial summaries from consecutive sections of one recording. "
        "Combine them into one concise, structured executive summary covering all sections. "
        "Preserve important decisions, action items, names, dates, and technical details.\n"
        "CRITICAL REQUIREMENT: Do NOT output any thinking, reasoning steps, or internal "
        "monologue. Output ONLY the final summary.\n"
        "CRITICAL REQUIREMENT: You MUST write your response entirely in the language "
        "corresponding to language code '{lang}'.\n\n"
        "Partial summaries:\n{summaries}"
    ),
    "highlights": (
        "Analyze the following SRT subtitles (which include exact timestamps) and "
        "identify the key highlights — decisions, commitments, assigned actions or "
        "scheduled follow-ups.\n"
        "Score each candidate 0-10 as a highlight.\n"
        "High score when: the speaker emphasizes importance/commitment ('this is "
        "important', 'we definitely do this', 'we must…'); a decision changes ('we said "
        "X before, now we change to Y'); an action is assigned ('I'll add this to my "
        "list', '<person> will do it', 'we will open a task/ticket'); a follow-up is "
        "scheduled ('let's talk about this next meeting', 'we'll revisit this').\n"
        "Low score when: the item is optional, a 'nice to have', or for the distant "
        "future.\n"
        "Return a compact JSON array of scored candidates only, no prose. Each candidate "
        'has "start" (HH:MM:SS), "end" (HH:MM:SS), "title", "score" (integer 0-10) '
        'and "reason".\n'
        'Example: [{"start":"00:03:10","end":"00:03:45","title":"Launch date '
        'moved to May","score":8,"reason":"Explicit commitment"}]\n'
        "CRITICAL REQUIREMENT: Do NOT output any thinking, reasoning steps, or internal "
        "monologue. Output ONLY the JSON array.\n"
        'CRITICAL REQUIREMENT: You MUST write "title" and "reason" entirely in the '
        "language corresponding to language code '{lang}'.\n\n"
        "SRT Subtitles:\n{srt_content}"
    ),
    "vision_frame": (
        "This frame belongs to a video recording described as: '{user_desc}'. "
        "At this timestamp, the speaker said: '{audio_context}'. "
        "If the frame shows a browser screen try to capture the whole URL. "
        "Analyze this frame and extract active URLs, UI elements, and screen interactions "
        "relevant to what was spoken, and pinpoint where the mouse pointer / cursor is "
        "located on the screen if visible.\n"
        "CRITICAL REQUIREMENT: Do NOT output any thinking or reasoning steps. Output ONLY "
        "the final frame description.\n"
        "CRITICAL REQUIREMENT: You MUST write your response entirely in the language "
        "corresponding to language code '{lang}'.\n"
    ),
    "media_type_classification": (
        "Classify the media described by the following signals as one of: meeting, lecture, "
        "interview, tutorial, webinar, podcast, presentation, other. "
        'Respond as compact JSON: {"media_type": "...", "confidence": 0.0, "reason": "..."}.\n\n'
        "Signals:\n{signals}"
    ),
    "transcript_cleanup": (
        "The following transcript may contain Whisper hallucination boilerplate on silence "
        "or music. Remove only obvious non-speech boilerplate and repetition; keep all real "
        "speech and timestamps. Write any change notes in language '{lang}'.\n\n"
        "Transcript:\n{transcript}"
    ),
    "review_revision": (
        "Revise the following content using the reviewer instructions. Keep everything the "
        "reviewer did not ask to change. Write the result in language '{lang}'.\n\n"
        "Reviewer instructions:\n{instructions}\n\n"
        "Content:\n{content}"
    ),
    "topic_segmentation": (
        "Split the transcript into topic sections. Return a compact JSON array of objects "
        "with 'start' (HH:MM:SS), 'end' (HH:MM:SS) and 'title'. Boundaries must be "
        "monotonic and non-overlapping, and write titles in language '{lang}'.\n\n"
        "Transcript:\n{transcript}"
    ),
    "topic_title": (
        "Write a short, descriptive title (3-8 words) in language '{lang}' that summarises "
        "what the transcript section below is about. Output ONLY the title, no quotes or "
        "punctuation at the end.\n\n"
        "Section:\n{content}"
    ),
}

_PLACEHOLDER_PATTERN = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


@dataclass(frozen=True)
class PromptSet:
    """A resolved set of prompt templates (defaults = built-ins)."""

    summary: str = DEFAULT_PROMPTS["summary"]
    summary_combine: str = DEFAULT_PROMPTS["summary_combine"]
    highlights: str = DEFAULT_PROMPTS["highlights"]
    vision_frame: str = DEFAULT_PROMPTS["vision_frame"]
    media_type_classification: str = DEFAULT_PROMPTS["media_type_classification"]
    transcript_cleanup: str = DEFAULT_PROMPTS["transcript_cleanup"]
    review_revision: str = DEFAULT_PROMPTS["review_revision"]
    topic_segmentation: str = DEFAULT_PROMPTS["topic_segmentation"]
    topic_title: str = DEFAULT_PROMPTS["topic_title"]

    def template(self, name: str) -> str:
        if name not in TEMPLATE_PLACEHOLDERS:
            raise KeyError(f"Unknown prompt template: {name}")
        return getattr(self, name)

    def render(self, name: str, **values: object) -> str:
        """Fill ``{placeholder}`` tokens via explicit replacement (safe)."""
        text = self.template(name)
        for key, value in values.items():
            text = text.replace("{" + key + "}", str(value))
        return text

    def with_overrides(self, overrides: dict[str, str]) -> "PromptSet":
        cleaned = {
            key: value
            for key, value in overrides.items()
            if key in TEMPLATE_PLACEHOLDERS and isinstance(value, str) and value
        }
        return replace(self, **cleaned) if cleaned else self

    def to_dict(self) -> dict[str, str]:
        return {name: getattr(self, name) for name in TEMPLATE_NAMES}


def validate_template(name: str, template: str) -> list[str]:
    """Return problems with a template's placeholders (empty = valid)."""
    allowed = TEMPLATE_PLACEHOLDERS.get(name)
    if allowed is None:
        return [f"unknown template '{name}'"]
    found = set(_PLACEHOLDER_PATTERN.findall(template))
    problems: list[str] = []
    unknown = found - allowed
    missing = allowed - found
    if unknown:
        problems.append(f"unknown placeholders: {', '.join(sorted(unknown))}")
    if missing:
        problems.append(f"missing placeholders: {', '.join(sorted(missing))}")
    return problems


def validate_prompt_set(prompt_set: PromptSet) -> dict[str, list[str]]:
    """Map template name -> problems; only invalid templates are included."""
    problems = {}
    for name in TEMPLATE_NAMES:
        found = validate_template(name, prompt_set.template(name))
        if found:
            problems[name] = found
    return problems


def build_prompt_set(overrides: dict[str, str] | None = None) -> PromptSet:
    return PromptSet().with_overrides(overrides or {})
