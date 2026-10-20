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
- Defaults reproduce the previous hard-coded prompts byte-for-byte, so leaving
  prompts unset changes nothing.

## Resetting

Delete `prompts.json`, or save an empty/partial file — any omitted template
falls back to its built-in default.
