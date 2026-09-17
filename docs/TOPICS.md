# Topic Segmentation

Phase 4 (WS-I) splits the transcript into topic sections so summaries, the
Master Timeline and the HTML report gain structure.

## Method

The default is a deterministic **lexical-cohesion** baseline (TextTiling-style)
over the merged transcript paragraphs: it scores the vocabulary overlap between
consecutive blocks and cuts at the strongest valleys, honoring a minimum section
length and a maximum section count. No model or network is required.

`topic_method` can be `off` or `cohesion` (an AI title pass is planned and will
always fall back to cohesion; `off` leaves outputs exactly as before).

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
  "topic_method": "cohesion",
  "topic_min_seconds": 120,
  "topic_max_sections": 20
}
```

CLI flags (override settings): `--topics off|cohesion`,
`--topic-min-seconds`, `--topic-max-sections`.

## Degradation

- Method `off` → no topic files and no headings (outputs unchanged).
- No transcript SRT, or a failure while segmenting → the job continues with a
  flat timeline (the step is recorded as failed but tolerated).
