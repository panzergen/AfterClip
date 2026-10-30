# Plan: Vision synthesis, structured output and frame budget

Phase 3 of [PLAN_PROMPT_PACKS.md](PLAN_PROMPT_PACKS.md). This is the phase that
makes vision-heavy videos actually summarizable.

**Target release:** `0.6.0` (see [PLAN_ROADMAP.md](PLAN_ROADMAP.md)).

## 1. The current gap

Today the pipeline is effectively:

```text
Whisper transcript ──> summary / highlights / topics
frames ──> vision_frame per frame ──> vision_analysis.srt
```

The two branches meet only in `Master_Timeline.md` and
`multimodal_timeline.jsonl`. They never meet in `AI_Analysis.md`:

- `summary` receives only `{transcript}`.
- `highlights` receives only the subtitle SRT.
- `topic_segmentation` receives only the transcript.
- `vision_analysis.srt` is written but not summarized.

So a video with little speech gets a thin or empty AI summary, even if the
frames are described well. This phase adds the missing synthesis step.

## 2. Target pipeline

```text
frames ──> per-frame vision descriptions ──> vision_analysis.srt
                                              │
transcript ───────────────────────────────────┼──> vision synthesis
                                              │       (text model)
                                              v
                                   scene/section summaries
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    v                         v                         v
                 summary                  highlights                 topics
                    │                         │                         │
                    └──────────> AI_Analysis.md + AI_Analysis.json <────┘
```

The vision model is still used only for frames. The text model turns frame
descriptions into readable scenes. No video is uploaded.

## 3. New template: `vision_synthesis`

Add one new prompt template:

```text
You are building a scene/section outline from timestamped frame descriptions of
a video. The content type is: '{pack}'. Recording task: '{task}'.

Frame descriptions:
{frames}

Transcript for the same time range (may be empty or unrelated):
{transcript}

Group consecutive frames into scenes or sections. For each group return:
- start (HH:MM:SS)
- end (HH:MM:SS)
- title
- summary (what happens / what is shown)
- observations (the important visible details)
- transcript_note (what the speech adds, if anything)

Do not invent anything that is not in the frame descriptions or transcript.
If the transcript is empty or unrelated, rely on the frames. Write titles and
summaries in language '{lang}'. Return only a compact JSON array. No prose.
```

Placeholders: `{pack}`, `{task}`, `{frames}`, `{transcript}`, `{lang}`.

Processing:

1. Chunk `vision_analysis.srt` by time (for example 5-10 minutes, or by scene
   count).
2. Call `vision_synthesis` per chunk.
3. If there are multiple chunks, call a small combine template
   (`vision_synthesis_combine`) that merges them in order.
4. Write `Vision/vision_synthesis.json` and a human-readable
   `Vision/vision_synthesis.md`.
5. Cache the result; re-run only if the frame set, prompt, or transcript
   changed.

For slides, a “scene” is a slide or slide group. For software/product demos, it
is a step. For narrative, it is a scene. For travel, it is a location/scene.

## 4. Feed vision context into analysis

Add `{vision_context}` as an optional placeholder to:

- `summary`
- `summary_combine`
- `highlights`
- `topic_segmentation`

`{vision_context}` is the rendered `vision_synthesis` output for the relevant
time range:

```text
[00:01:10-00:03:20] Title
Summary: ...
Observations: ...
Speech: ...
```

Rules:

- Always pass a string; use an empty string when vision is off or no frames
  exist. Prompts must tolerate an empty section.
- Do not append vision text to `{transcript}`; keep the two inputs separate so
  the model can distinguish speech from observation.
- For long videos, chunk both transcript and vision context together by time, so
  a summary chunk sees the matching frames.
- `summary_combine` must preserve the chronological order of scenes.

If there is **no transcript**, the summary prompt should still run with an empty
`{transcript}` and vision context only. If there is **no vision**, behaviour is
exactly as today.

## 5. Vision sampling and resolution controls

### 5.1 Existing controls

- `frame_interval` (seconds) for interval extraction.
- `scene_sensitivity` for scene extraction.
- `frame_resolution` (`full`, `mid`, `low`).
- `frame_modes` (`interval`, `scene`, `highlight`).

### 5.2 New per-preset controls

Add:

| Field | Meaning | Example |
|---|---|---|
| `vision_frame_stride` | Analyze every Nth extracted frame | `2` = every second frame |
| `vision_min_gap_seconds` | Drop frames closer than this in time | `20` |
| `vision_max_frames` | Hard cap on frames sent to the vision model | `240` |
| `vision_frame_resolution` | Resolution for extracted/analyzed frames | `low`, `mid`, `full` |
| `vision_sampling_mode` | `all`, `even`, `scene` | `even` |

`vision_frame_resolution` can reuse the existing `frame_resolution` value, but
make it visible and saved per preset. The user asked for both sampling density
and resolution to be selectable; these fields provide that.

### 5.3 Selection algorithm

1. Keep user bookmark/highlight frames.
2. Apply `vision_min_gap_seconds` (drop the later frame of a too-close pair).
3. If `vision_sampling_mode == "even"`, pick evenly spaced frames across the
   duration, including the first and last.
4. If `"scene"`, prefer scene-boundary frames and use even sampling to fill the
   cap.
5. Apply `vision_frame_stride`.
6. Apply `vision_max_frames`; if still over, downsample evenly.
7. Write the selected list to `Vision/frame_selection.json` with the reason for
   each frame (kept bookmark, scene change, even sample, capped).

The analysis should not silently drop all frames of a long static section. Keep
at least one frame per N minutes even when scene detection finds no cuts.

### 5.4 Recommended defaults

| Pack | Sampling | Max frames | Resolution |
|---|---|---|---|
| meeting | all | 0 (unlimited) | full/mid |
| slides | scene + fallback | 200 | full/mid |
| software_demo | even | 150 | mid/full |
| product_demo | even + scene | 150 | mid |
| narrative | even + scene | 240 | low/mid |
| travel_documentary | even + scene | 180 | low/mid |

These are defaults only; every preset stores the user’s choice.

### 5.5 Forecast

Update the pre-start forecast to show the estimated number of vision calls and
a rough time/cost estimate. This prevents a 2-hour movie from silently producing
hundreds of calls.

## 6. Visual highlights and scene-based topics

### 6.1 Highlights

- Run highlights when **either** an SRT **or** a vision context exists. Today it
  is skipped when there is no SRT.
- Feed `{srt_content}` and `{vision_context}`.
- Allow `"source": "speech" | "vision" | "mixed"` in each candidate.
- Update `application/highlights.py` to keep `source` and to deduplicate a
  speech highlight and a vision highlight that describe the same moment.
- The Markdown report can render a small `[vision]` / `[speech]` / `[mixed]`
  marker when useful.

### 6.2 Topics

- Feed `{vision_context}` into `topic_segmentation`.
- If the transcript is empty, use the `vision_synthesis` sections directly
  instead of calling the text model again.
- If both exist, let the model merge them and keep boundaries monotonic.
- `topic_title` can use the scene title when one exists.

## 7. Structured output (`AI_Analysis.json`)

Add a `structured_analysis` prompt template, one per preset (the user can edit
it), with placeholders:

- `{lang}`, `{task}`, `{pack}`, `{transcript}`, `{vision_context}`,
  `{highlights}`.

It returns the shared envelope described in
[PLAN_CONTENT_PACKS.md](PLAN_CONTENT_PACKS.md):

```json
{
  "schema_version": 1,
  "pack": "slides",
  "language": "tr",
  "summary": "...",
  "sections": [],
  "highlights": [],
  "data": {},
  "caveats": []
}
```

Implementation:

- Parse tolerantly (reuse the JSON extraction approach used by highlights).
- On parse failure, keep `AI_Analysis.md` and write
  `AI_Analysis.json` with `{"error": "unparseable model output", "raw": "..."}`
  rather than failing the job.
- `AI_Analysis.md` can be rendered from the JSON plus the existing Markdown
  summary; keep the existing headings for compatibility.
- Do not require JSON from small local models for basic summaries; JSON is an
  extra artifact, not a replacement for the report.
- Add the `data` schema per pack as defined in the content-packs plan.

Cost note: this is one extra text call per job. If cost is a problem, merge it
with the summary call in a later optimization; do not block Phase 3 on it.

## 8. Code touchpoints

- `domain/prompts.py`: add `vision_synthesis`, `vision_synthesis_combine`,
  `structured_analysis`; add optional placeholders.
- `application/service.py`:
  - new `_run_vision_synthesis` step after `_run_vision_analysis`;
  - pass vision context into `_run_text_analysis` and `_run_topic_segmentation`;
  - run highlights when SRT or vision exists;
  - write `AI_Analysis.json`.
- `application/service_io.py`: read/write synthesis JSON, frame selection,
  timestamp helpers.
- `application/timeline.py`: optionally include scene summaries in the master
  timeline.
- `application/highlights.py`: preserve `source`; dedupe mixed sources.
- `infrastructure/process.py`: frame extraction already supports
  `frame_resolution`; add or reuse the selection step.
- `ui/controllers/job_form_controller.py` and `domain/presets.py`: new sampling
  fields.
- `ui/qml/AdvancedPanel.qml`: sampling mode, max frames, min gap, resolution.
- `application/forecast.py`: frame-count estimate.

## 9. Tests and acceptance

Unit tests:

- `vision_synthesis` parses a JSON array; tolerant parser handles prose around it.
- Synthesis chunks are combined in order.
- Summary receives vision context when present and an empty string when not.
- Summary still works with an empty transcript and vision only.
- Highlights run with vision-only input.
- Topic segmentation falls back to vision sections when there is no transcript.
- Frame selection honors min gap, stride, max cap, bookmarks and even sampling.
- Frame selection never returns zero frames for a long static video.
- `AI_Analysis.json` is valid on success and contains `"error"` on parse failure.
- Vision cache invalidates when the frame set or prompt changes.

Acceptance criteria:

1. A silent travel clip produces a readable scene summary from frames alone.
2. A 2-hour movie with a 240-frame cap produces a scene list, not thousands of
   vision calls.
3. A slide deck produces a slide-ordered outline even when speech is sparse.
4. A software demo produces steps and UI states; a product demo does not reuse
   the UI schema.
5. Highlights can be visual-only and carry a source marker.
6. The job never fails because JSON parsing or vision synthesis failed.

## 10. Out of scope

- Character sheet and rolling context (Phase 4).
- Automatic content-type detection (deferred).
- Cross-episode character continuity (later, if requested).
