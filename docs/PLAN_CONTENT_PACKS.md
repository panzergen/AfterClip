# Plan: Content packs and prompt drafts

Phase 2 of [PLAN_PROMPT_PACKS.md](PLAN_PROMPT_PACKS.md). This document defines
the six content packs, the prompt text to ship as **starter text**, and the
structured output contract. It does **not** add built-in active presets: the
user creates a preset and loads a starter into it.

## 1. Common rules for every pack

Every new prompt must follow these rules:

1. **Visible only.** Describe only what is visible in the frame. Never invent a
   URL, name, place, product, character, chart value or event.
2. **Unreadable text.** Write `[unreadable]` instead of guessing.
3. **Speech may be absent or unrelated.** The `{audio_context}` value can be
   empty or may be the nearest line of dialogue, not speech at the exact frame.
   Use it only when it agrees with the frame.
4. **Language.** Write the answer in `{lang}`. Translate visible slide, UI, sign
   and on-screen text into `{lang}`. Keep proper nouns and brand names in their
   original spelling.
5. **No reasoning.** Output only the final answer; no thinking or internal
   monologue.
6. **Separate observation from inference.** If something is inferred, label it
   as inference or omit it.
7. **Do not force a link.** A slide, scene or product does not need to match the
   quoted speech.

## 2. Placeholder changes

### Existing placeholders

| Template | Existing placeholders |
|---|---|
| `vision_frame` | `{user_desc}`, `{audio_context}`, `{lang}` |
| `summary` | `{lang}`, `{transcript}` |
| `summary_combine` | `{lang}`, `{summaries}` |
| `highlights` | `{lang}`, `{srt_content}` |
| `topic_segmentation` | `{lang}`, `{transcript}` |
| `topic_title` | `{lang}`, `{content}` |

### New placeholders for Phase 2

- `{task}` — the “Target task” text. Optional in `summary`, `highlights`,
  `topic_segmentation`.
- `{timestamp}` — media timestamp of the frame. Optional in `vision_frame`.

### New placeholder for Phase 3

- `{vision_context}` — timestamped scene/section summaries built from frame
  descriptions. Optional in `summary`, `summary_combine`, `highlights`,
  `topic_segmentation`.

### Validator change

`TEMPLATE_PLACEHOLDERS` currently treats every allowed placeholder as required.
Change it to required + optional sets:

```python
TEMPLATE_PLACEHOLDERS = {
    "summary": {"required": {"lang", "transcript"}, "optional": {"task", "vision_context"}},
    ...
}
```

Existing user templates without the new optional placeholders must remain valid.
The editor should show optional placeholders separately and should not reject a
save that omits them.

## 3. Pack definitions

### 3.1 `meeting` — keep the current behaviour

No prompt text change. This remains the fallback for existing users.

- Vision: shared screen, URL, UI elements, cursor.
- Summary: meeting decisions/actions.
- Highlights: decisions, commitments, follow-ups.
- Frames: interval, 10 s default, full/mid resolution.

### 3.2 `slides` — PowerPoint / Keynote / slide-based presentation

**Vision prompt draft**

```text
This frame is from a slide-based presentation.
Recording task: '{user_desc}'
At this timestamp the speaker said: '{audio_context}'
Frame timestamp: {timestamp}

Read the slide itself, not the room. Output exactly these lines:
TITLE: <slide title, or [none]>
SLIDE TEXT: <all legible bullets in reading order, translated to {lang}; separate with " | "; write [unreadable] for unclear text>
VISUALS: <chart, table or diagram type; axes, series, labels and key numbers; [none]>
HIGHLIGHT: <only what the presenter points at or highlights; [none]>

Do not describe the presenter, audience or room unless they are part of the
slide content. Do not infer text that is not visible. Do not guess numbers.
```

**Summary prompt draft**

```text
Below is the transcript of a slide-based presentation, with slide descriptions
where available.

Produce:
1. A slide-by-slide or section-by-section outline in order.
2. The main claim of each section and the evidence or numbers shown on the slides.
3. Exact names, dates, definitions and numbers.
4. Conclusions, recommendations and Q&A points.
5. Mark whether a point came from the slide, the speech, or both.

Write entirely in language '{lang}'. Translate visible slide text into '{lang}';
keep proper nouns and brand names in their original spelling.
Recording task: '{task}'

Transcript and slide descriptions:
{transcript}

Visual context:
{vision_context}
```

**Highlights prompt draft**

```text
Analyze the timestamped transcript and visual timeline of a presentation.
Identify key takeaways: important claims, exact data points, definitions,
recommendations, decisions and open questions. Do not look for meeting action
items.

Score each candidate 0-10 as a presentation highlight. High score for a central
claim, a surprising or decision-relevant number, a clear recommendation, or a
conclusion. Low score for repetition, logistics, or optional detail.

Return only a compact JSON array. Each object has "start" (HH:MM:SS), "end"
(HH:MM:SS), "title", "score" (integer 0-10), "reason" and "source"
("speech", "vision" or "mixed"). Write "title" and "reason" in language
'{lang}'. Do not output prose.

Task: '{task}'

Transcript:
{srt_content}

Visual context:
{vision_context}
```

**Structured data**

```json
{
  "slides": [
    {
      "start": "00:01:10",
      "end": "00:03:20",
      "title": "...",
      "bullets": ["..."],
      "visuals": [{"type": "bar chart", "labels": ["..."], "numbers": ["..."]}],
      "spoken_only": ["..."],
      "slide_only": ["..."]
    }
  ],
  "conclusions": ["..."],
  "open_questions": ["..."]
}
```

**Frame defaults:** scene mode (slide changes), fallback interval 30 s, max 200
frames, resolution full or mid (text legibility matters).

### 3.3 `software_demo` — screen-recorded software or web app demo

**Vision prompt draft**

```text
This frame is from a software demo.
Recording task: '{user_desc}'
At this timestamp the speaker said: '{audio_context}'
Frame timestamp: {timestamp}

Describe the product UI only:
APP/PAGE: <application or page name, if visible>
URL: <the complete URL if visible, otherwise [none]>
UI STATE: <active menu, tab, dialog or panel; visible labels, data and errors>
ACTION: <what changed, or what the cursor/click indicates; [none]>

Do not describe the room or presenter. Translate visible UI text into '{lang}';
keep product names in their original spelling. Do not invent menu items or URLs.
```

**Summary prompt draft**

```text
Below is the transcript and visual timeline of a software demo.

Produce:
1. The goal of the demo and any prerequisites.
2. The steps shown, in order, including the UI state before and after each step.
3. Features demonstrated versus features only mentioned.
4. Errors, limitations or caveats.
5. The final result.

Write entirely in language '{lang}'. Translate visible UI text into '{lang}';
keep product names. Recording task: '{task}'

Transcript:
{transcript}

Visual context:
{vision_context}
```

**Highlights:** key steps, features, workarounds, results and caveats.

**Structured data:**

```json
{
  "goal": "...",
  "steps": [
    {"start": "00:00:20", "title": "...", "ui_state": "...", "action": "...", "result": "..."}
  ],
  "features": [{"name": "...", "demonstrated": true, "notes": "..."}],
  "ui_states": [{"start": "...", "url": "...", "screen": "...", "visible_labels": ["..."]}],
  "caveats": ["..."]
}
```

**Frame defaults:** interval 10-15 s (scene detection can miss small UI
changes), max 150 frames, resolution mid or full for legibility.

### 3.4 `product_demo` — physical product demonstration on camera

This is deliberately separate from `software_demo`.

**Vision prompt draft**

```text
This frame is from a physical product demonstration.
Recording task: '{user_desc}'
At this timestamp the speaker said: '{audio_context}'
Frame timestamp: {timestamp}

Describe only what is visible:
PRODUCT: <the object; use its name only if it is legible or unambiguous, otherwise describe it>
PARTS/MATERIALS: <visible parts, materials, colours, controls>
ACTION: <hands, assembly, usage step or demonstration>
RESULT: <before/after state, effect or output>
TEXT: <on-screen or packaging text, translated to {lang}; [none]>

Do not invent specifications, prices, availability, performance claims or an
off-screen result. Translate visible text into '{lang}'.
```

**Summary prompt draft**

```text
Below is the transcript and visual timeline of a physical product demonstration.

Produce:
1. What the product is, using only visible or spoken evidence.
2. The features and parts demonstrated.
3. How it is used, in order.
4. Results and before/after states that were actually shown.
5. Limitations, caveats or claims that were only spoken and not demonstrated.

Do not add specifications, prices or availability. Write entirely in language
'{lang}'. Translate visible text into '{lang}'. Recording task: '{task}'

Transcript:
{transcript}

Visual context:
{vision_context}
```

**Highlights:** best demonstrations, feature reveals, results and practical
caveats.

**Structured data:**

```json
{
  "product": {"name": "...", "description": "...", "evidence": "visible|spoken|both"},
  "features": [{"name": "...", "demonstrated": true, "notes": "..."}],
  "demo_steps": [{"start": "...", "action": "...", "result": "..."}],
  "results": [{"start": "...", "before": "...", "after": "..."}],
  "caveats": ["..."]
}
```

**Frame defaults:** scene + interval, 15-30 s, max 150 frames, resolution mid.

### 3.5 `narrative` — movie, TV series, cartoon, scripted video

Character sheet and rolling context are Phase 4. In Phase 2, characters are
described generically (“a man in a red jacket”), never named unless a subtitle
or the user supplies a name.

**Vision prompt draft**

```text
This frame is from a narrative video (movie, TV series or cartoon).
Dialogue or speech: '{audio_context}'
Frame timestamp: {timestamp}

Describe only what is visible:
SHOT: <wide, medium, close-up, etc.>
SETTING: <location and time of day, if visible>
CHARACTERS: <count, appearance, clothing and action; do not invent names>
ACTION: <what is happening>
ON-SCREEN TEXT: <translated to {lang}; [none]>
MOOD/LIGHT: <mood and lighting>
STYLE: <live action or animation style, only if clear>

Do not invent plot, names, relationships or off-screen events. Separate what
is visible from what you infer. If a detail is unclear, say so.
```

**Summary prompt draft**

```text
Below is the transcript and visual timeline of a narrative video.

Build a chronological scene recap. For each scene give:
- setting;
- characters using generic descriptions (do not invent names);
- action;
- what the dialogue adds;
- any on-screen text that matters.

Then list the turning points and the strongest moments. Do not invent events,
names or relationships. Mark uncertain inferences. Do not reveal anything that
is outside the supplied clip. Write entirely in language '{lang}'. Recording
task: '{task}'

Transcript:
{transcript}

Visual context:
{vision_context}
```

**Highlights prompt draft**

```text
Analyze the timestamped transcript and visual timeline of a narrative video.
Identify key scenes and turning points: a reveal, a decision, a conflict, a
visual gag, a dramatic change, or an important line. Do not look for meeting
actions or business takeaways.

Score 0-10. Return only a compact JSON array with "start", "end", "title",
"score", "reason" and "source" ("speech", "vision" or "mixed"). Write "title"
and "reason" in language '{lang}'. Do not output prose.

Transcript:
{srt_content}

Visual context:
{vision_context}
```

**Structured data:**

```json
{
  "scenes": [
    {
      "start": "00:01:10",
      "end": "00:03:20",
      "setting": "...",
      "characters": ["a man in a red jacket"],
      "action": "...",
      "dialogue_context": "...",
      "on_screen_text": ["..."]
    }
  ],
  "key_moments": [{"start": "...", "title": "...", "source": "vision|speech|mixed"}],
  "uncertain": ["..."]
}
```

**Frame defaults:** scene mode with a hard cap, or 20-30 s interval, max 240
frames, resolution low or mid. Movies produce many cuts, so a cap is required.

### 3.6 `travel_documentary` — travel, scenery and factual footage

**Vision prompt draft**

```text
This frame is from a travel or documentary video.
Narration or speech: '{audio_context}'
Frame timestamp: {timestamp}

Describe only what is visible:
PLACE/LANDMARK: <name only if legible or visually unambiguous; otherwise describe it; confidence: high/medium/low>
TEXT/SIGNS: <translated to {lang}; [none]>
TERRAIN/ARCHITECTURE: <visible landscape, buildings, streets>
PEOPLE/ACTIVITY: <what people are doing>
WEATHER/TIME: <weather and time of day, if clear>
MOOD: <the visual mood>

Do not guess a location. Do not extract prices, routes, opening hours or
booking information. If a landmark is only a guess, label it as a guess or omit
the name.
```

**Summary prompt draft**

```text
Below is the transcript and visual timeline of a travel or documentary video.

Produce a chronological summary:
1. Places and landmarks in order, with the visual evidence for each
   identification (sign, landmark shape, spoken name, etc.).
2. Activities and people shown.
3. Standout moments and the overall mood.
4. For a documentary: key facts or claims, and whether each was spoken, shown,
   or both.

Do not include prices, routes, opening hours or bookings. Do not invent a place
name. Write entirely in language '{lang}'. Translate visible signs into
'{lang}'; keep proper nouns in their original spelling. Recording task:
'{task}'

Transcript:
{transcript}

Visual context:
{vision_context}
```

**Highlights:** best moments, places, landmarks and key documentary facts.

**Structured data:**

```json
{
  "places": [
    {"name": "...", "evidence": "visible sign|landmark|spoken|both", "confidence": "high|medium|low"}
  ],
  "activities": ["..."],
  "key_moments": [{"start": "...", "title": "...", "source": "vision|speech|mixed"}],
  "key_facts": [{"start": "...", "fact": "...", "evidence": "spoken|shown|both"}],
  "uncertain": ["..."]
}
```

**Frame defaults:** scene + interval, 20-30 s, max 180 frames, resolution low
or mid. Lower resolution is acceptable because the goal is place/scene
identification, not reading small text; the user can raise it per preset.

## 4. Topic segmentation and titles

- `meeting`: keep transcript-based segmentation.
- `slides`: prefer slide changes/titles; fall back to transcript.
- `software_demo`: prefer steps/feature changes; fall back to transcript.
- `product_demo`: prefer demonstration steps; fall back to transcript.
- `narrative`: prefer scene boundaries from vision; fall back to transcript.
- `travel_documentary`: prefer location/scene changes; fall back to transcript.

`topic_segmentation` gets an optional `{vision_context}`. `topic_title` stays
short and uses the section content; for slides, prefer the slide title.

## 5. “Both” output: Markdown + JSON

Every pack writes:

- `AI_Analysis.md` — readable report with summary, highlights and pack-specific
  sections.
- `AI_Analysis.json` — one object, tolerant-parsed, with this shared envelope:

```json
{
  "schema_version": 1,
  "pack": "slides",
  "language": "tr",
  "summary": "...",
  "sections": [{"start": "...", "end": "...", "title": "...", "summary": "..."}],
  "highlights": [{"start": "...", "end": "...", "title": "...", "score": 8, "reason": "...", "source": "mixed"}],
  "data": {},
  "caveats": []
}
```

`data` is pack-specific as shown above. If JSON parsing fails, keep the Markdown
report and write a small `AI_Analysis.json` with `"error": "unparseable model
output"` rather than failing the job.

## 6. Starter text, not built-in presets

- No active presets are shipped.
- The prompt texts above are **starter text**. The prompt editor gets a
  “Load starter…” action listing the six packs.
- The user reviews/edits the text and saves it as their own preset.
- The default prompt set remains the current meeting-oriented text, so existing
  users see no change until they create a preset.

## 7. Frame and resolution defaults

These are recommended defaults; every value stays user-selectable and is stored
in the preset.

| Pack | Extraction | Analysis sampling | Resolution |
|---|---|---|---|
| meeting | interval 10 s | all extracted frames | full/mid |
| slides | scene, fallback interval 30 s | every slide change, max 200 | full/mid |
| software_demo | interval 10-15 s | every frame, max 150 | mid/full |
| product_demo | scene + interval 15-30 s | every frame, max 150 | mid |
| narrative | scene + cap, or interval 20-30 s | max 240 | low/mid |
| travel_documentary | scene + interval 20-30 s | max 180 | low/mid |

Phase 3 adds the actual sampling controls (`max frames`, `min gap`, `stride`)
and the per-preset resolution selector. See
[PLAN_VISION_SYNTHESIS.md](PLAN_VISION_SYNTHESIS.md).

## 8. Acceptance criteria

1. Each pack produces a readable Markdown report and a valid JSON sidecar.
2. Slides preserve slide order, exact numbers and visible text translated to
   the report language.
3. Software and physical product demos produce different structured data.
4. Narrative output never invents character names or plot events.
5. Travel output identifies landmarks with evidence/confidence and never emits
   prices, routes or opening hours.
6. An empty or unrelated `{audio_context}` does not break any pack.
7. Existing meeting prompts remain unchanged unless the user loads a starter.
