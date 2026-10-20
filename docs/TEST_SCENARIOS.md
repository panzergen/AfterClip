# Test Scenarios

Manual checks for features shipped in the last two days of work: the highlights
rework, forecast self-correction and local voiceprints. Run the automated suite
first, then walk each scenario on a real recording.

## Automated baseline

```powershell
python -m pytest -q
python -m pytest tests/application/test_highlights.py tests/application/test_forecast.py tests/application/test_voiceprints.py tests/application/test_service_voiceprint.py tests/infrastructure/test_audio.py tests/infrastructure/test_voiceprints_store.py -q
```

Expected: all green.

---

## 1. Highlights rework

Highlights are now a short, globally ranked list (≤ 3, ≥ score 7, one per 5
minutes) instead of one list per transcription chunk.

**Setup:** enable AI text analysis (any local/cloud provider) and process a
meeting-style recording that contains a decision, an assigned action, a
follow-up, and at least one "nice to have".

**Verify:**
- `AI_Analysis.md` → `## Key Highlights` has **3 or fewer** bullets, each with a
  leading timestamp (e.g. `- 00:03:10 Launch date moved to May`).
- Highlights are decisions/actions/commitments, not optional or "nice to have"
  items.
- `FullReportAndTimeline.htm` → `Key Highlights` shows the same short list.
- `Summary_Report.md` still contains the summary even when no highlight passes
  the score cut-off.

**Edge:** a recording with no strong highlights shows
`No highlights were extracted.` while the summary survives.

---

## 2. Forecast self-correction

The pre-start estimate now records itself and corrects against past outcomes.

**Setup:** process **3+ jobs with the same Whisper model, frame modes and
analysis toggles** so a comparable history builds up.

**Verify:**
- Each finished job's `job_state.json` now contains a `forecast` block with
  `expected_seconds`, `basis` and `sample_count`.
- Before starting a new job, the pinned estimate reads
  `Estimated ~Xm (low–high) · N similar job(s)`.
- On subsequent runs the estimate tracks the real duration (the median
  actual/predicted ratio is applied; it stops being systematically high or low).

**Edge:** cold start (no history) still shows `Rough estimate …`; a job with
`duration == 0` shows no estimate.

---

## 3. Voiceprints (local speaker identification)

Voiceprints complement the speaker VTT: VTT labels win, and only unlabeled
segments are identified against enrolled voiceprints or clustered into
`Speaker N`.

**Setup:**
1. Install the optional extra: `pip install -e ".[voiceprint]"` (pulls
   `onnxruntime` + `speakeronnx`; the model downloads into the local cache on
   first use).
2. Settings → Voiceprints: enroll a speaker by entering a name and the path to a
   short clean audio sample of that person, then **Enroll**. Enroll a second
   speaker too.

**Verify:**
- Environment status tooltip shows `Voiceprint: OK`.
- Settings lists the enrolled names; **Remove** deletes one.
- Process a file with **"Identify speakers by voice"** checked and, ideally, a
  speaker VTT supplied.
- `Master_Timeline.md` / `multimodal_timeline.jsonl` speaker badges: segments
  covered by the VTT keep the VTT name; unlabeled segments get an enrolled name
  or `Speaker 1/2/…`.

**Edges:**
- No voiceprint extra installed → the toggle has no effect, status shows
  `Voiceprint: MISSING`, and the job still completes normally.
- No enrolled voiceprints → unlabeled segments are clustered into `Speaker N`.
- A corrupted audio sample during enrollment shows a clear error and does not
  crash the app.

### 3b. Post-job enrollment + reprocess

After a job runs with voiceprints enabled and finds unlabeled speakers:

1. A **"Name the detected speakers"** dialog lists each `Speaker N` cluster with
   a **▶ play** button (plays a sample segment from the original recording) and
   a **■ stop** button, plus a name field and an **Enroll** button. The list
   scrolls so any number of speakers is reachable.

**Threshold tuning:** embeddings are computed over merged ~20s blocks, and the
dialog has a live **Merge similarity** slider (0.30–0.70) that re-clusters as
you drag — lower merges more, higher keeps voices separate. Listen to a few
clips, tag, then reprocess.
2. Naming a speaker enrolls that cluster's **average (centroid)** as a global
   voiceprint.
3. **Save names & reprocess** enrolls every row with a typed name, re-labels the
   finished job from the stored embeddings (no Whisper/AI re-run), rewrites
   `Master_Timeline.md` / `multimodal_timeline.jsonl` with the names, and closes
   the dialog. The per-row **Enroll** button still works for enrolling without
   reprocessing.

**Verify:**
- The job folder now contains `Voiceprints.json` (segments + cluster centroids).
- After naming `Speaker 1` → `Alice` and reprocessing, the timeline shows
  `[SPEAKER: Alice]` where it previously showed `[SPEAKER: Speaker 1]`.
- A future job identifies that voice as `Alice` automatically.

### 3c. Voiceprint management screen

Settings → **Manage voiceprints…**:

- Lists every saved speaker with **Re-enroll** (pick a new sample to overwrite a
  poor voiceprint) and **Reset** (remove it).
- Thresholds (identify/cluster) are adjustable here and saved with Settings.

**Verify:**
- Re-enrolling a speaker with a better sample changes matching on the next job.
- Resetting a speaker removes it; future jobs no longer name it.

---

## 4. Completion sound notification

A short chime plays when a job finishes or fails (single and batch). Enabled by
default; configurable in **Settings → Notifications**.

**Verify:**
- Processing a file plays the chime when the job completes (and again if it fails).
- Running a batch plays the chime when the queue finishes.
- Settings → Notifications → **Test** plays the currently selected clip.
- Turning the toggle off silences it; turning it back on restores it.
- **Browse…** selects a custom WAV; leaving the path blank falls back to the
  built-in sound.

**Edge:**
- A custom path that is later deleted falls back to the built-in sound without error.

## Regression (unchanged behaviour)

- Speaker VTT alone still works exactly as before (no voiceprints enabled).
- Batch, resume, cloud consent and the transcript filter are unaffected by the
  highlights/forecast/voiceprint changes.
