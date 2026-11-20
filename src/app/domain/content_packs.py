"""Starter prompt packs for content types (Phase 2).

These are **starter texts**, not active presets. The prompt editor can load one
into the session-custom prompt set; the user reviews/edits it and saves it as
their own preset. The built-in defaults stay meeting-oriented, so existing
users see no change until they load a starter.

Phase 2 starts with the slide pack. Further packs are added here as their
starter texts are written, following docs/PLAN_CONTENT_PACKS.md.
"""

from dataclasses import dataclass

from app.domain.prompts import DEFAULT_PROMPTS


@dataclass(frozen=True)
class ContentPack:
    """One content type's starter prompt texts and recommended frame settings."""

    name: str
    label: str
    description: str
    prompts: dict[str, str]
    frame_modes: tuple[str, ...] = ("interval",)
    frame_interval: int = 10
    frame_resolution: str = "full"


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
        "Recording task: '{task}'\n"
        "Do NOT output any thinking, reasoning or internal monologue, and do not "
        "address the user or the prompt. Start directly with the report.\n\n"
        "Transcript and slide descriptions:\n{transcript}\n\n"
        "Visual context:\n{vision_context}"
    ),
    "summary_combine": (
        "Below are partial summaries from consecutive sections of one "
        "slide-based presentation. Combine them into a single slide-ordered "
        "report covering all sections. Preserve the slide order, main claims, "
        "bullet points, exact names, dates, definitions and numbers, plus "
        "conclusions, recommendations and Q&A points.\n\n"
        "Write entirely in language '{lang}'. Recording task: '{task}'\n"
        "Do NOT output any thinking, reasoning or internal monologue, and do not "
        "address the user or the prompt. Start directly with the report.\n\n"
        "Partial summaries:\n{summaries}\n\n"
        "Visual context:\n{vision_context}"
    ),
    "highlights": (
        "Analyze the following timestamped transcript "
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
        "candidate has 'start' (HH:MM:SS; use the block timestamp), 'title', "
        "'score' (integer 0-10) and 'reason'.\n"
        'Example: [{"start":"00:03:10","title":"Q3 revenue up 12 percent",'
        '"score":8,"reason":"Exact number shown on slide and emphasized"}]\n'
        "Do NOT output any thinking, reasoning or internal monologue. Output "
        "ONLY the JSON array.\n"
        "You MUST write 'title' and 'reason' entirely in language '{lang}'.\n"
        "Task: '{task}'\n\n"
        "Timestamped transcript:\n{srt_content}\n\n"
        "Visual context:\n{vision_context}"
    ),
    "vision_frame": (
        "This frame is from a slide-based presentation.\n"
        "Recording task: '{user_desc}'.\n"
        "At this timestamp the speaker said: '{audio_context}'.\n"
        "Frame timestamp: {timestamp}\n\n"
        "Read the slide itself, not the room. Output exactly these lines:\n"
        "TITLE: <slide title, or [none]>\n"
        "SLIDE TEXT: <all legible bullets in reading order, translated to "
        "'{lang}'; separate with ' | '; write [unreadable] for unclear text>\n"
        "If a table, grid or dense slide is mostly unreadable, write [unreadable] "
        "once for the whole region; do not repeat [unreadable] for every cell.\n"
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
        "'{lang}'.\n"
        "Task: '{task}'\n\n"
        "Transcript:\n{transcript}\n\n"
        "Visual context:\n{vision_context}"
    ),
    "topic_title": (
        "Write a short, descriptive title (3-8 words) in language '{lang}' that "
        "summarises what the transcript section below is about; prefer the slide "
        "title when the speaker states one. Output ONLY the title, no quotes or "
        "punctuation at the end.\n\n"
        "Section:\n{content}"
    ),
}


def _combine(subject: str) -> str:
    return (
        "Below are partial summaries from consecutive sections of one "
        + subject
        + ". Combine them into a single report covering all sections. Preserve "
        "the order, main claims, names, dates, definitions, numbers and "
        "conclusions.\n\n"
        "Write entirely in language '{lang}'. Recording task: '{task}'\n"
        "Do NOT output any thinking, reasoning or internal monologue. Start "
        "directly with the report.\n\n"
        "Partial summaries:\n{summaries}\n\n"
        "Visual context:\n{vision_context}"
    )


def _highlights(focus: str) -> str:
    return (
        "Analyze the following timestamped transcript "
        "and identify the key highlights: " + focus + ".\n"
        "Score each candidate 0-10 as a highlight. High score for a clear claim, "
        "exact number, decision, recommendation, result or answered question; "
        "low score for repetition, logistics or optional detail.\n"
        "Return a compact JSON array of scored candidates only, no prose. Each "
        "candidate has 'start' (HH:MM:SS; use the block timestamp), 'title', "
        "'score' (integer 0-10) and 'reason'. Highlight specific moments, not "
        "section headers.\n"
        "Do NOT output any thinking, reasoning or internal monologue. Output "
        "ONLY the JSON array.\n"
        "You MUST write 'title' and 'reason' entirely in language '{lang}'.\n"
        "Task: '{task}'\n\n"
        "Timestamped transcript:\n{srt_content}\n\n"
        "Visual context:\n{vision_context}"
    )


def _topics(preference: str) -> str:
    return (
        "Split the transcript into topic sections, "
        + preference
        + ". Return a compact JSON array of objects with 'start' (HH:MM:SS), "
        "'end' (HH:MM:SS) and 'title'. Boundaries must be monotonic and "
        "non-overlapping, and titles must be in language '{lang}'.\n"
        "Task: '{task}'\n\n"
        "Transcript:\n{transcript}\n\n"
        "Visual context:\n{vision_context}"
    )


def _title(preference: str) -> str:
    return (
        "Write a short, descriptive title (3-8 words) in language '{lang}' "
        "that summarises the transcript section below; "
        + preference
        + ". Output ONLY the title, no quotes or punctuation at the end.\n\n"
        "Section:\n{content}"
    )


_SOFTWARE_DEMO_PROMPTS: dict[str, str] = {
    "vision_frame": (
        "This frame is from a software demo.\n"
        "Recording task: '{user_desc}'.\n"
        "At this timestamp the speaker said: '{audio_context}'.\n"
        "Frame timestamp: {timestamp}\n\n"
        "Describe the product UI only:\n"
        "APP/PAGE: <application or page name, if visible; [none]>\n"
        "URL: <the complete URL if visible, otherwise [none]>\n"
        "UI STATE: <active menu, tab, dialog or panel; visible labels, data and "
        "errors; [none]>\n"
        "ACTION: <what changed, or what the cursor/click indicates; [none]>\n\n"
        "If the screen is blank or a transition, output exactly: BLANK: true\n"
        "Do not describe the room or presenter. Translate visible UI text into "
        "'{lang}'; keep product names in their original spelling. Do not invent "
        "menu items or URLs.\n"
        "Do NOT output any thinking or reasoning steps. Output ONLY the final "
        "frame description. You MUST write your response entirely in language "
        "'{lang}'.\n"
    ),
    "summary": (
        "Below is the transcript of a software demo.\n\n"
        "Produce:\n"
        "1. The goal of the demo and any prerequisites.\n"
        "2. The steps shown, in order, including the UI state before and after "
        "each step.\n"
        "3. Features demonstrated versus features only mentioned.\n"
        "4. Errors, limitations or caveats.\n"
        "5. The final result.\n\n"
        "Write entirely in language '{lang}'. Translate visible UI text into "
        "'{lang}'; keep product names in their original spelling. Do NOT output "
        "any thinking or internal monologue, and do not address the user or the "
        "prompt. Start directly with the report. Recording task: '{task}'\n\n"
        "Transcript:\n{transcript}\n\n"
        "Visual context:\n{vision_context}"
    ),
    "summary_combine": _combine("software demo"),
    "highlights": _highlights("key steps, features, workarounds, results and practical caveats"),
    "topic_segmentation": _topics("preferring steps or feature changes"),
    "topic_title": _title("prefer the page or feature name when the speaker states one"),
}

_PRODUCT_DEMO_PROMPTS: dict[str, str] = {
    "vision_frame": (
        "This frame is from a physical product demonstration.\n"
        "Recording task: '{user_desc}'.\n"
        "At this timestamp the speaker said: '{audio_context}'.\n"
        "Frame timestamp: {timestamp}\n\n"
        "Describe only what is visible:\n"
        "PRODUCT: <the object; use its name only if legible or unambiguous, "
        "otherwise describe it>\n"
        "PARTS/MATERIALS: <visible parts, materials, colours and controls>\n"
        "ACTION: <hands, assembly, usage step or demonstration; [none]>\n"
        "RESULT: <before/after state, effect or output; [none]>\n"
        "TEXT: <on-screen or packaging text, translated to '{lang}'; [none]>\n\n"
        "If the frame is blank or a transition, output exactly: BLANK: true\n"
        "Do not invent specifications, prices, availability, performance claims "
        "or an off-screen result. Translate visible text into '{lang}'.\n"
        "Do NOT output any thinking or reasoning steps. Output ONLY the final "
        "frame description. You MUST write your response entirely in language "
        "'{lang}'.\n"
    ),
    "summary": (
        "Below is the transcript of a physical product demonstration.\n\n"
        "Produce:\n"
        "1. What the product is, using only visible or spoken evidence.\n"
        "2. The features and parts demonstrated.\n"
        "3. How it is used, in order.\n"
        "4. Results and before/after states that were actually shown.\n"
        "5. Limitations, caveats or claims that were only spoken and not "
        "demonstrated.\n\n"
        "Do not add specifications, prices or availability. Write entirely in "
        "language '{lang}'. Translate visible text into '{lang}'. Do NOT output "
        "any thinking or internal monologue, and do not address the user or the "
        "prompt. Start directly with the report. Recording task: '{task}'\n\n"
        "Transcript:\n{transcript}\n\n"
        "Visual context:\n{vision_context}"
    ),
    "summary_combine": _combine("physical product demonstration"),
    "highlights": _highlights(
        "feature reveals, the clearest demonstrations, shown results and practical caveats"
    ),
    "topic_segmentation": _topics("preferring demonstration steps"),
    "topic_title": _title("prefer the product or step name when the speaker states one"),
}

_NARRATIVE_PROMPTS: dict[str, str] = {
    "vision_frame": (
        "This frame is from a narrative video (movie, TV series or cartoon).\n"
        "Recording task: '{user_desc}'.\n"
        "Dialogue or speech: '{audio_context}'.\n"
        "Frame timestamp: {timestamp}\n\n"
        "Describe only what is visible:\n"
        "SHOT: <wide, medium, close-up, etc.>\n"
        "SETTING: <location and time of day, if visible>\n"
        "CHARACTERS: <count, appearance, clothing and action; do not invent names>\n"
        "ACTION: <what is happening>\n"
        "ON-SCREEN TEXT: <translated to '{lang}'; [none]>\n"
        "MOOD/LIGHT: <mood and lighting>\n"
        "STYLE: <live action or animation style, only if clear>\n\n"
        "Do not invent plot, names, relationships or off-screen events. Separate "
        "what is visible from what you infer. If a detail is unclear, say so.\n"
        "Do NOT output any thinking or reasoning steps. Output ONLY the final "
        "frame description. You MUST write your response entirely in language "
        "'{lang}'.\n"
    ),
    "summary": (
        "Below is the transcript of a narrative video.\n\n"
        "Build a chronological scene recap. For each scene give the setting; the "
        "characters using generic descriptions (do not invent names); the action; "
        "what the dialogue adds; and any on-screen text that matters.\n"
        "Then list the turning points and the strongest moments. Do not invent "
        "events, names or relationships. Mark uncertain inferences. Do not reveal "
        "anything outside the supplied clip.\n\n"
        "Write entirely in language '{lang}'. Do NOT output any thinking or "
        "internal monologue, and do not address the user or the prompt. Start "
        "directly with the report. Recording task: '{task}'\n\n"
        "Transcript:\n{transcript}\n\n"
        "Visual context:\n{vision_context}"
    ),
    "summary_combine": _combine("narrative video"),
    "highlights": _highlights(
        "key scenes and turning points: a reveal, a decision, a conflict, a visual "
        "gag, a dramatic change or an important line"
    ),
    "topic_segmentation": _topics("preferring scene changes"),
    "topic_title": _title("prefer the scene or setting when the speaker states one"),
}

_TRAVEL_PROMPTS: dict[str, str] = {
    "vision_frame": (
        "This frame is from a travel or documentary video.\n"
        "Recording task: '{user_desc}'.\n"
        "Narration or speech: '{audio_context}'.\n"
        "Frame timestamp: {timestamp}\n\n"
        "Describe only what is visible:\n"
        "PLACE/LANDMARK: <name only if legible or visually unambiguous; otherwise "
        "describe it; confidence: high/medium/low>\n"
        "TEXT/SIGNS: <translated to '{lang}'; [none]>\n"
        "TERRAIN/ARCHITECTURE: <visible landscape, buildings, streets>\n"
        "PEOPLE/ACTIVITY: <what people are doing>\n"
        "WEATHER/TIME: <weather and time of day, if clear>\n"
        "MOOD: <the visual mood>\n\n"
        "Do not guess a location. Do not extract prices, routes, opening hours or "
        "booking information. If a landmark is only a guess, label it as a guess "
        "or omit the name. Translate visible signs into '{lang}'.\n"
        "Do NOT output any thinking or reasoning steps. Output ONLY the final "
        "frame description. You MUST write your response entirely in language "
        "'{lang}'.\n"
    ),
    "summary": (
        "Below is the transcript of a travel or documentary video.\n\n"
        "Produce a chronological summary:\n"
        "1. Places and landmarks in order, with the visual evidence for each "
        "identification (sign, landmark shape, spoken name, etc.).\n"
        "2. Activities and people shown.\n"
        "3. Standout moments and the overall mood.\n"
        "4. For a documentary: key facts or claims, and whether each was spoken, "
        "shown, or both.\n\n"
        "Do not include prices, routes, opening hours or bookings. Do not invent a "
        "place name. Write entirely in language '{lang}'. Translate visible signs "
        "into '{lang}'; keep proper nouns in their original spelling. Do NOT "
        "output any thinking or internal monologue, and do not address the user "
        "or the prompt. Start directly with the report. Recording task: '{task}'\n\n"
        "Transcript:\n{transcript}\n\n"
        "Visual context:\n{vision_context}"
    ),
    "summary_combine": _combine("travel or documentary video"),
    "highlights": _highlights(
        "standout places, landmark evidence, activities and key documentary facts"
    ),
    "topic_segmentation": _topics("preferring location or scene changes"),
    "topic_title": _title("prefer the place or section name when the speaker states one"),
}

CONTENT_PACKS: tuple[ContentPack, ...] = (
    ContentPack(
        name="meeting",
        label="Meeting / webinar (default)",
        description=(
            "The built-in meeting-oriented prompts: decisions, actions, shared "
            "screens and questions. Use this to restore the defaults."
        ),
        prompts=dict(DEFAULT_PROMPTS),
        frame_modes=("interval",),
        frame_interval=10,
        frame_resolution="full",
    ),
    ContentPack(
        name="slides",
        label="Slides / presentation",
        description=(
            "PowerPoint, Keynote or other slide-based presentations. Prefers "
            "slide changes for topics and reads the slide rather than the room."
        ),
        prompts=_SLIDES_PROMPTS,
        frame_modes=("scene",),
        frame_interval=30,
        frame_resolution="full",
    ),
    ContentPack(
        name="software_demo",
        label="Software / app demo",
        description=(
            "Screen-recorded software or web app demos: goal, steps, UI states, "
            "features, errors and the final result."
        ),
        prompts=_SOFTWARE_DEMO_PROMPTS,
        frame_modes=("interval",),
        frame_interval=12,
        frame_resolution="mid",
    ),
    ContentPack(
        name="product_demo",
        label="Physical product demo",
        description=(
            "A physical product shown on camera: parts, usage steps, shown "
            "results and caveats; no invented specifications or prices."
        ),
        prompts=_PRODUCT_DEMO_PROMPTS,
        frame_modes=("scene", "interval"),
        frame_interval=20,
        frame_resolution="mid",
    ),
    ContentPack(
        name="narrative",
        label="Narrative video",
        description=(
            "Movies, series, cartoons and scripted video: scene recap, generic "
            "character descriptions and turning points; no invented names."
        ),
        prompts=_NARRATIVE_PROMPTS,
        frame_modes=("scene",),
        frame_interval=25,
        frame_resolution="low",
    ),
    ContentPack(
        name="travel_documentary",
        label="Travel / documentary",
        description=(
            "Travel, scenery and factual footage: places and landmarks with "
            "evidence, activities and key facts; no prices, routes or bookings."
        ),
        prompts=_TRAVEL_PROMPTS,
        frame_modes=("scene",),
        frame_interval=25,
        frame_resolution="low",
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


def pack_descriptions() -> list[str]:
    return [pack.description for pack in CONTENT_PACKS]
