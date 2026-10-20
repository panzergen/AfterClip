# Process Time Forecasting

Phase 4 (WS-H) shows a **pre-start time estimate** so long recordings don't
surprise you. It is computed locally from past job metrics; nothing is sent
anywhere.

## What it shows

In the pinned action area, before you start:

```
Estimated ~34m (26m–51m) · 12 similar job(s)
Rough estimate ~2m (1m–4m)
```

- **Range** is the p10–p90 of the per-minute rate from similar jobs, never a
  single false-precise number.
- **Basis**: `N similar job(s)` when enough comparable history exists, otherwise
  `Rough estimate` for the cold-start heuristic.

## How it works

Each job records features into `job_state.json` (Phase 4 addition):

```json
{
  "media": { "duration": 5886.0, "file_size_mb": 212.2 },
  "run_settings": {
    "model": "turbo",
    "frame_modes": ["scene"],
    "frame_resolution": "full",
    "analyze_text": true,
    "analyze_vision": true
  },
  "steps": { "transcription": { "duration_seconds": 1503.75 }, "...": {} }
}
```

The estimate:

1. Filters history to jobs with the same Whisper model, frame modes and
   analysis toggles; relaxes to same-model, then any job, if too few match.
2. Takes the nearest jobs by media duration and computes each job's rate
   (`total processing seconds / media seconds`).
3. Reports `median(rate) × current duration` as the estimate with the p10–p90
   band.
4. **Cold start** (< 3 comparable jobs): uses a per-model fraction of media
   duration and labels the result a rough estimate.

The estimate also accounts for a selected clip range (clip duration is the
basis) and refreshes when the media, model, frame/analysis settings or clip
change, and after each finished job.

## Caveats

Hardware dominates: CPU vs GPU and unified memory make the same job vary a lot.
The forecast therefore always shows a **range** and is bucketed by
configuration; it never presents a single precise number.

The estimate is local only — no cloud request is made to compute it.

## Self-correction

Each job stores its pre-start estimate (`job_state.json` → `forecast`) alongside
the recorded step durations. On a later estimate, past jobs that stored a
forecast contribute a correction factor: the median ratio of actual total time
to predicted total time, clamped to 0.5–2.0 so one outlier cannot swing the
estimate wildly. The raw rate-based estimate (and its p10–p90 band) is scaled by
that factor. Correction only applies once at least three comparable jobs have
stored a forecast; earlier runs fall back to the uncorrected estimate.
