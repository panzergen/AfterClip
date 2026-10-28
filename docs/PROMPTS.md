# Prompt Templates

Phase 4 (WS-B) moves every analysis prompt out of code into editable data.
Providers receive a resolved `PromptSet`; editing a prompt changes the next
job's output without rebuilding or restarting.

## Where prompts live

`%LOCALAPPDATA%\AfterClip\prompts.json` (see `PLATFORMS.md` for other OSes).
If the file is missing or corrupt, built-in defaults from
`src/app/domain/prompts.py` are used, so the app always works.

Example:

```json
{
  "version": 1,
  "summary": "Below is a transcript... language code '{lang}'.\n\nTranscript:\n{transcript}",
  "highlights": "... {lang} ... {srt_content}"
}
```

Only known template keys are read; unknown keys and empty values are ignored.

## Language resolution (`{lang}`)

`{lang}` is filled per job as: explicit **report language** → Whisper-detected
video language (from the transcript `.json`) → transcription language hint →
English. So leaving report language empty keeps responses in the video's own
language instead of silently defaulting to English. If the media mixes
languages, the built-in templates require a single-language response in
`{lang}`.

## Templates and placeholders

| Template | Placeholders | Used by |
| --- | --- | --- |
| `summary` | `{lang}`, `{transcript}` | text analysis (one chunk) |
| `summary_combine` | `{lang}`, `{summaries}` | text analysis (multi-chunk combine) |
| `highlights` | `{lang}`, `{srt_content}` | highlights extraction |
| `vision_frame` | `{user_desc}`, `{audio_context}`, `{lang}` | vision frame description |
| `media_type_classification` | `{signals}` | media-type classification (WS-D) |
| `topic_segmentation` | `{lang}`, `{transcript}` | topic segmentation (WS-I) |
| `topic_title` | `{lang}`, `{content}` | per-topic title generation (WS-I) |
| `transcript_cleanup` | `{lang}`, `{transcript}` | **not currently called** — template only |
| `review_revision` | `{lang}`, `{instructions}`, `{content}` | **not currently called** — template only |

The last two ship so the text can be inspected and edited in the prompt editor,
but no code path invokes them yet. Editing them has no effect on the current
release.

## Safety and validation

- Rendering uses explicit token replacement, never `str.format`, so a stray `{`
  in a template or in media text can never raise or leak object attributes
  (`app/domain/prompts.py`).
- `validate_template()` / `validate_prompt_set()` report **unknown** and
  **missing** placeholders for a template. The editor rejects a save that would
  drop a required placeholder.
- Built-in defaults carry output-only, no-preamble and single-language
  requirements; custom templates are used verbatim, so weakening them can bring
  back chatter or mixed-language output.
- Summary outputs pass through a preamble stripper
  (`application/summary.py`): a leftover leading acknowledgement ("Anladım…",
  "Here is…") is removed before the report is written; the rest of the text is
  never touched.

## Resetting

Delete `prompts.json`, or save an empty/partial file — any omitted template
falls back to its built-in default.

## Saved vs unsaved edits (Phase 1)

`Save` in the prompt editor writes to `prompts.json` (global, used by the next
job). Edits you have not saved yet are **session-custom**: they are still used
for the next job, and the preset badge shows `Custom`, but they are lost on app
restart and never overwrite `prompts.json`. The prompt dialog shows
“Unsaved changes — used for the next job” while dirty.

## Planned prompt packs

The current templates are meeting-oriented. The next phases add editable starter
prompts for slide presentations, software demos, physical product demos,
narrative video and travel/documentary footage, plus vision synthesis for
low-speech videos. See [PLAN_PROMPT_PACKS.md](PLAN_PROMPT_PACKS.md) and
[PLAN_CONTENT_PACKS.md](PLAN_CONTENT_PACKS.md). These are plans, not current
behaviour.
