# Plan: Narrative character sheet and rolling context

Phase 4, **last**, of [PLAN_PROMPT_PACKS.md](PLAN_PROMPT_PACKS.md). Only the
`narrative` pack. Everything in Phases 2-3 must work without this feature; a job
with no character sheet behaves exactly like the Phase 3 output.

## 1. Goal

Keep character references stable across a long movie/TV episode/cartoon without
re-running the vision model on every frame:

- “a man in a red jacket” in scene 1 and “the same man” in scene 9 become one
  stable reference.
- The user can rename `Character A` to a real name after the first pass.
- The final report uses those names consistently.
- Rolling context gives the model the previous scene, not the whole transcript
  or all previous frames.

No face recognition, no biometric embeddings, no identity database. This is
text-only continuity from visible descriptions.

## 2. Why this is last

Character continuity changes the prompt inputs and the report structure. It is
only useful after:

- presets can carry full prompt sets (Phase 1);
- the narrative vision/synthesis prompts exist (Phase 2);
- scene summaries feed the report (Phase 3).

Doing it earlier would mean tuning against outputs that are still changing.

## 3. Character sheet

### 3.1 Build

After the first `vision_synthesis` pass:

1. Collect scene summaries and character descriptions.
2. Ask the text model to cluster recurring descriptions into characters.
3. Assign neutral IDs: `Character A`, `Character B`, ...
4. Record:
   - generic label (“a man in a red jacket”);
   - appearance/clothing;
   - first and last seen timestamps;
   - confidence (`high`, `medium`, `low`);
   - optional name if a subtitle, on-screen text, or the user supplied one.

Do **not** invent names from appearance. A name is only used when it is present
in the transcript/subtitles, on-screen text, the user’s task, or the user’s
manual rename.

### 3.2 Schema

`Vision/character_sheet.json`:

```json
{
  "schema_version": 1,
  "characters": [
    {
      "id": "A",
      "label": "a man in a red jacket",
      "name": "",
      "appearance": "short dark hair, red jacket, blue jeans",
      "first_seen": "00:01:10",
      "last_seen": "00:42:05",
      "confidence": "high"
    }
  ]
}
```

### 3.3 User editing

- After the job, show a simple “Characters” dialog (similar in spirit to the
  voiceprint naming dialog).
- Each row shows the generic label, a preview timestamp/frame, and an editable
  name field.
- Renaming triggers a **text-only re-synthesis** of the report; it does not
  re-run the vision model.
- An optional “Deep pass” button can re-run vision for ambiguous frames with the
  character sheet attached. This is opt-in because it costs another vision pass.
- Names are stored per job. A series-level reusable sheet is out of scope for
  Phase 4 (possible later).

## 4. Rolling context

### 4.1 What is passed

For each narrative frame or scene prompt, pass:

- `{character_sheet}` — the current sheet, compacted to names + key appearance.
- `{rolling_context}` — the previous 1-2 scene summaries, not raw frames.

Do **not** pass the whole history. Keep the block under a fixed budget (for
example 1,500 characters) and truncate the oldest content first.

### 4.2 Where it is used

- `vision_synthesis` (primary): scene grouping and character matching.
- `vision_frame` (optional): only when a frame is ambiguous or a character
  first appears; the base pass can stay context-free.
- `summary` and `structured_analysis`: use the final sheet for consistent names.

### 4.3 Update cadence

- Update the character sheet after each **scene**, not each frame. Per-frame
  updates cause drift and extra calls.
- The sheet only grows when a new recurring description appears; a one-off
  background person is not added.
- On a scene boundary, include the previous scene summary as rolling context.
- Never include future scenes. The report must not spoil events beyond the
  processed clip.

## 5. New placeholders

Optional placeholders:

- `{character_sheet}` — in `vision_frame`, `vision_synthesis`, `summary`,
  `structured_analysis`.
- `{rolling_context}` — in `vision_synthesis`.

Existing prompts without them stay valid; the validator treats them as optional.

## 6. Pipeline

```text
frames ──> generic per-frame descriptions
              │
              v
        vision synthesis (scenes)
              │
              v
     character sheet extraction (text model)
              │
              v
     user renames characters (optional)
              │
              v
     text-only re-synthesis with names
              │
              v
     report + structured JSON
```

Optional deep pass:

```text
character sheet + ambiguous frames ──> vision model ──> corrected descriptions
```

## 7. Prompt additions

### 7.1 `vision_synthesis` addition

```text
Known characters (use these labels consistently; do not invent names):
{character_sheet}

Previous scene:
{rolling_context}

If a character matches a known entry, use its label. If a new recurring
character appears, describe it and mark it as new. Do not guess a name.
```

### 7.2 `summary` / `structured_analysis` addition

```text
Use the character labels from the character sheet. If a character has a user
name, use that name. Do not introduce character names that are not in the sheet
or the transcript.
```

## 8. UI

- Add a “Characters” action on a finished narrative job.
- Show the character list with first/last seen, confidence and an editable name.
- Renaming runs the text-only re-synthesis and refreshes the report.
- Show a note that the sheet is derived from visual descriptions, not face
  recognition.
- Optional: a “Deep pass” button with a cost warning.

## 9. Tests and acceptance

Unit tests:

- Two descriptions of the same appearance cluster into one character.
- Different characters with similar clothing remain separate when context
  disagrees.
- User rename propagates through summary and JSON.
- No character sheet -> output identical to Phase 3.
- Rolling context is truncated at the token/character budget.
- Future scenes are never included in rolling context.
- A one-off background person is not added to the sheet.
- `{character_sheet}` and `{rolling_context}` are optional in validation.

Acceptance criteria:

1. A 30-60 minute narrative sample uses one stable label per recurring
   character.
2. Manual names appear consistently in the report and JSON.
3. The base pass does not require a second vision pass.
4. A deep pass is opt-in and clearly priced/estimated.
5. No biometric data or face embeddings are stored.

## 10. Out of scope

- Face recognition or biometric identification.
- Cross-episode/series-wide character memory (possible later).
- Automatic cast lists from external databases.
- Character continuity for non-narrative packs.
