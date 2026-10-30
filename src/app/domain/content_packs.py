"""Starter prompt packs for content types (Phase 2).

These are **starter texts**, not active presets. The prompt editor can load one
into the session-custom prompt set; the user reviews/edits it and saves it as
their own preset. The built-in defaults stay meeting-oriented, so existing
users see no change until they load a starter.

Phase 2 starts with the slide pack. Further packs are added here as their
starter texts are written, following docs/PLAN_CONTENT_PACKS.md.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ContentPack:
    """One content type's starter prompt texts."""

    name: str
    label: str
    description: str
    prompts: dict[str, str]


_SLIDES_PROMPTS: dict[str, str] = {
    "summary": (
        "Below is the transcript of a slide-based presentation, with slide "
        "descriptions where available.\n\n"
        "Produce:\n"
        "1. A slide-by-slide or section-by-section outline in order.\n"
        "2. The main claim of each section and the evidence or numbers shown on "
        "the slides.\n"
        "3. Exact names, dates, definitions and numbers.\n"
        "4. Conclusions, recommendations and Q&A points.\n"
        "5. Mark whether each point came from the slide, the speech, or both.\n\n"
        "Write entirely in language '{lang}'. Translate visible slide text into "
        "'{lang}'; keep proper nouns and brand names in their original spelling. "
        "Do NOT output any thinking, reasoning or internal monologue, and do not "
        "address the user or the prompt. Start directly with the report.\n\n"
        "Transcript and slide descriptions:\n{transcript}"
    ),
    "summary_combine": (
        "Below are partial summaries from consecutive sections of one "
        "slide-based presentation. Combine them into a single slide-ordered "
        "report covering all sections. Preserve the slide order, main claims, "
        "bullet points, exact names, dates, definitions and numbers, plus "
        "conclusions, recommendations and Q&A points.\n\n"
        "Write entirely in language '{lang}'. Do NOT output any thinking, "
        "reasoning or internal monologue, and do not address the user or the "
        "prompt. Start directly with the report.\n\n"
        "Partial summaries:\n{summaries}"
    ),
    "highlights": (
        "Analyze the following SRT subtitles (which include exact timestamps) "
        "and identify the key highlights of this slide-based presentation: "
        "central claims, exact data points, definitions, recommendations, "
        "conclusions and answered questions.\n"
        "Score each candidate 0-10 as a highlight.\n"
        "High score when: the speaker states a central claim or conclusion; "
        "gives an exact number or data point shown on a slide; defines a term; "
        "makes a recommendation or decision; answers a question; refers to the "
        "slide ('as you can see here', 'this chart shows', 'next slide').\n"
        "Low score when: the item is small talk, repetition, logistics, agenda "
        "overview, or optional detail.\n"
        "Highlight specific moments with timestamps, not section headers.\n"
        "Return a compact JSON array of scored candidates only, no prose. Each "
        "candidate has 'start' (HH:MM:SS), 'end' (HH:MM:SS), 'title', 'score' "
        "(integer 0-10) and 'reason'.\n"
        "Example: [{\"start\":\"00:03:10\",\"end\":\"00:03:45\",\"title\":\"Q3 "
        "revenue up 12 percent\",\"score\":8,\"reason\":\"Exact number shown on "
        "slide and emphasized\"}]\n"
        "Do NOT output any thinking, reasoning or internal monologue. Output "
        "ONLY the JSON array.\n"
        "You MUST write 'title' and 'reason' entirely in language '{lang}'.\n\n"
        "SRT Subtitles:\n{srt_content}"
    ),
    "vision_frame": (
        "This frame is from a slide-based presentation.\n"
        "Recording task: '{user_desc}'.\n"
        "At this timestamp the speaker said: '{audio_context}'.\n\n"
        "Read the slide itself, not the room. Output exactly these lines:\n"
        "TITLE: <slide title, or [none]>\n"
        "SLIDE TEXT: <all legible bullets in reading order, translated to "
        "'{lang}'; separate with ' | '; write [unreadable] for unclear text>\n"
        "VISUALS: <chart, table or diagram type; axes, series, labels and key "
        "numbers; [none]>\n"
        "HIGHLIGHT: <only what the presenter points at or highlights; [none]>\n\n"
        "If the slide is blank or a transition, output exactly: BLANK: true\n"
        "Do not describe the presenter, audience or room unless they are part of "
        "the slide content. Do not infer text that is not visible. Do not guess "
        "numbers.\n"
        "Do NOT output any thinking or reasoning steps. Output ONLY the final "
        "frame description.\n"
        "You MUST write your response entirely in language '{lang}'.\n"
    ),
    "topic_segmentation": (
        "Split the transcript of a slide-based presentation into topic sections, "
        "preferring slide changes (listen for cues like 'next slide', 'moving "
        "on', 'as you see here'). Return a compact JSON array of objects with "
        "'start' (HH:MM:SS), 'end' (HH:MM:SS) and 'title'. Boundaries must be "
        "monotonic and non-overlapping, and titles must be in language "
        "'{lang}'.\n\n"
        "Transcript:\n{transcript}"
    ),
    "topic_title": (
        "Write a short, descriptive title (3-8 words) in language '{lang}' that "
        "summarises what the transcript section below is about; prefer the slide "
        "title when the speaker states one. Output ONLY the title, no quotes or "
        "punctuation at the end.\n\n"
        "Section:\n{content}"
    ),
}


CONTENT_PACKS: tuple[ContentPack, ...] = (
    ContentPack(
        name="slides",
        label="Slides / presentation",
        description=(
            "PowerPoint, Keynote or other slide-based presentations. Prefers "
            "slide changes for topics and reads the slide rather than the room."
        ),
        prompts=_SLIDES_PROMPTS,
    ),
)

_BY_LABEL = {pack.label: pack for pack in CONTENT_PACKS}
_BY_NAME = {pack.name: pack for pack in CONTENT_PACKS}


def find_pack(value: str | None) -> ContentPack | None:
    """Look up a starter pack by label or internal name."""
    if not value:
        return None
    return _BY_LABEL.get(value) or _BY_NAME.get(value)


def pack_labels() -> list[str]:
    return [pack.label for pack in CONTENT_PACKS]
