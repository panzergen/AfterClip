# Topic Segmentation

Phase 4 (WS-I) splits the transcript into topic sections so summaries, the
Master Timeline and the HTML report gain structure.

## Method

The default is **`ai`**: deterministic **lexical-cohesion** boundaries
(TextTiling-style) over the merged transcript paragraphs, then one short
AI-generated title per section using the `topic_title` prompt. Boundaries are
always deterministic, so a failed or unavailable model only costs the titles,
never the sectioning — those fall back to the first sentence.

`topic_method` can be:

| Method | Behaviour |
| --- | --- |
| `ai` (default) | cohesion boundaries + AI titles; heuristic titles if no provider |
| `cohesion` | cohesion boundaries + first-sentence titles (offline) |
| `off` | no topic files and no headings (outputs unchanged) |

Section count is **auto-scaled** to the media duration (about one section per
minute, bounded 4–120); `topic_max_sections` can override it (0 = auto) and
`topic_min_seconds` is the minimum section length (default 60s).

AI titles need a text provider (they use the same one as AI text analysis, and
respect the prompt templates). With no provider, `ai` degrades to `cohesion`.

Titles always follow the report language: the explicit selection, or **English**
when none is selected. The Whisper-detected and transcription languages are not
used for the report. Models sometimes copy the language of the section instead;
a small deterministic guard (`application/language.py`) then rewrites the
affected titles in one batch in the target language and retries any stragglers
individually. Product names and brand names are kept.

## Outputs

For each job:

- `Topics.md` — numbered sections with `[start --> end]` timestamps and titles.
- `Topics.json` — the same sections, machine-readable.
- `Master_Timeline.md` — a `## <title>` heading before each section.
- `AI_Analysis.md` — a `## Topics` section listing the sections.
- `FullReportAndTimeline.htm` — a **Topics** section plus an inline `<h2>`
  heading for every section boundary.
- `job_state.json` — the sections under `topics`.

## Settings and CLI

`settings.json`:

```json
{
  "topic_method": "ai",
  "topic_min_seconds": 60,
  "topic_max_sections": 0
}
```

CLI flags (override settings): `--topics off|cohesion|ai`,
`--topic-min-seconds`, `--topic-max-sections`.

## Degradation

- Method `off` → no topic files and no headings (outputs unchanged).
- No transcript SRT, or a failure while segmenting → the job continues with a
  flat timeline (the step is recorded as failed but tolerated).
