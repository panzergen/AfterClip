# Transcript Hallucination Filter

Phase 4 (WS-C) adds a **deterministic** filter for Whisper hallucinations:
boilerplate over silence/music ("thanks for watching", subtitle credits),
repeated loops and empty/very low-confidence segments.

## Evidence is preserved

The filter never silently deletes. For each run it:

- keeps the untouched Whisper output as `<stem>.raw.json`, `<stem>.raw.srt`,
  `<stem>.raw.txt` (written once; re-runs stay idempotent);
- writes the cleaned transcript to `<stem>.srt` / `<stem>.txt`;
- writes `transcript_filter_report.json` listing every removed and flagged
  segment with its timestamps, text and reason, plus the config used.

`Summary_Report.md` is unaffected; `job_state.json` records the step counts.

## Decision rules

Using the segment metadata Whisper already emits in `<stem>.json`:

| Signal | Action |
| --- | --- |
| empty / shorter than `min_chars` | removed (`empty`) |
| matches a blocklist phrase | removed (`blocklist`) |
| `no_speech_prob` ≥ `no_speech_threshold` | removed (`no_speech`) |
| `compression_ratio` ≥ `compression_ratio_threshold` | removed (`compression`) |
| repeated ≥ `max_repetition` times in a row | removed (`repetition`) |
| `avg_logprob` ≤ `avg_logprob_threshold` | kept but **flagged** (`low_logprob`) |

When the filter is enabled AfterClip also runs Whisper with
`--condition_on_previous_text False` to reduce loop hallucinations. When the
filter is disabled the Whisper invocation and output are unchanged.

## Enabling and configuring

- Per job: **Advanced → Transcript (Whisper) → "Filter Whisper hallucinations"**
  (on by default).
- Global config lives in `settings.json` under `transcript_filter`:

```json
{
  "transcript_filter": {
    "enabled": true,
    "no_speech_threshold": 0.6,
    "avg_logprob_threshold": -1.0,
    "compression_ratio_threshold": 2.4,
    "max_repetition": 3,
    "min_chars": 1,
    "blocklist": ["thanks for watching", "amara.org"]
  }
}
```

Any missing/invalid value falls back to the built-in default. The batch queue
uses the default configuration.

An optional AI cleanup pass (using the `transcript_cleanup` prompt) is planned
and will stay off by default.
