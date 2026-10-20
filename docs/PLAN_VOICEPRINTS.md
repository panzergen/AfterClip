# Plan: Local voiceprints (speaker identification)

Decisions made with the user; carry forward in later chats. Status markers at the
end of each section.

## 1. Capability — BOTH (clustering + named identification)

Voiceprints do two things, both local-only:

1. **Speaker clustering** — when no speaker labels are available, group
   transcript segments into `Speaker 1` / `Speaker 2` / … by voice similarity
   (built-in diarization).
2. **Named identification** — after a user enrolls a short audio sample per
   person, label matching segments with that person's name.

## 2. Relationship to the existing speaker VTT — COMPLEMENT

The speaker VTT (user-provided, `<v Speaker>`-tagged) stays primary. Voiceprints
only fill gaps:

- A segment already labeled by the VTT keeps its VTT label.
- A segment with no VTT label is identified against enrolled voiceprints; if no
  match, it is assigned to an unknown-speaker cluster (`Speaker N`).
- VTT labels are never overridden.

## 3. Embedding stack — speakeronnx + onnxruntime (no PyTorch)

**Recommendation:** [`speakeronnx`](https://github.com/TigreGotico/speakeronnx)
on top of `onnxruntime`, no PyTorch at runtime.

Rationale:
- The app is otherwise pure-stdlib/urllib; pulling in `torch` (~200 MB+ CPU wheel)
  would bloat the release and slow cold start. `onnxruntime` is a single small
  wheel and runs on Windows CPU.
- `speakeronnx` bundles audio preprocessing and cosine similarity, and offers
  small models. Preferred model: **`redimnet-b2`** (192-dim embedding, ~1.8 M
  params, raw-waveform frontend, Apache-2.0) — the raw frontend means no mel
  filterbank preprocessing, so segment audio can be sliced in-memory and fed
  directly. Fallback: `wespeaker-ecapa512` / `campplus-zh-en` (fbank frontend).

**Optional dependency** (like Whisper/FFmpeg): add a `voiceprint` extra
(`onnxruntime`, `speakeronnx`) and probe availability at runtime. The app keeps
running without it; voiceprint features are hidden/disabled, and the status LED
shows `Voiceprint: MISSING`. Model weights download on first use into the local
cache.

## 4. Storage

- Voiceprint store: JSON file under the app data directory (e.g.
  `voiceprints.json`), mapping `name -> embedding` (192 floats). Never contains
  audio. Local-only.
- No cloud upload, no keyring (not a secret — embeddings are biometric but
  non-reversible; keep them out of logs/reports).

## 5. Audio source

Reuse the prepared 16 kHz mono WAV already produced for Whisper
(`media_preparation`). Segment audio is sliced from it by Whisper segment
timestamps (in-memory PCM via the `wave` module, or FFmpeg `-ss/-to` when the
source is not 16 k mono).

## 6. Pipeline (complement VTT)

1. After transcription, load the speaker VTT (existing).
2. For each merged timeline block *without* a VTT speaker, compute its embedding.
3. Identify against enrolled voiceprints (cosine similarity, above threshold →
   name); otherwise cluster unknowns into `Speaker N`.
4. Merge: VTT labels win; voiceprint labels fill the rest; write speaker badges
   into the timeline and a `Voiceprints.json`/report note.

## 7. Open items

- Exact identification threshold (tune ~0.7 cosine for `redimnet-b2`; expose as
  a setting).
- Enrollment UX: record a sample via the Record tab vs. point at an existing
  audio clip; a "Manage voiceprints" list in Settings.
- Whether clustering runs per-job by default or only when requested.

Status: **IMPLEMENTED** (post-job enrollment + reprocess + settings screen included).

Implemented:
- `application/ports/voiceprint.py` — `SpeakerEmbedder` / `VoiceprintStore` protocols.
- `application/voiceprints.py` — `cosine_similarity`, `identify_speaker`,
  `cluster_speakers` (greedy centroid pass + centroid-linkage merge pass to avoid
  fragmentation), `speaker_label`, `analyse_speakers` (intervals + clusters with
  **centroids**), plus `SpeakerSegment`/`SpeakerCluster`/`SpeakerAnalysis` and the
  `Voiceprints.json` sidecar (`write_voiceprint_sidecar` / `load_voiceprint_sidecar`).
  Default identify/cluster thresholds are **0.5** (tunable in Settings).
- `infrastructure/voiceprints.py` — `JsonVoiceprintStore` + `InMemoryVoiceprintStore`.
- `infrastructure/audio.py` — WAV read/downmix/resample/slice/write (16 kHz mono).
- `infrastructure/voiceprint_embedder.py` — `SpeakerOnnxEmbedder` +
  `voiceprints_available()` (lazy `speakeronnx`, no PyTorch).
- Service: `_run_voiceprint_labelling` fills VTT gaps and persists the sidecar;
  `reprocess_voiceprints` re-labels a finished job from the stored embeddings
  (no audio re-read) and rewrites the master timeline. Embeddings are computed
  over **merged ~20s transcript blocks** (`VOICEPRINT_BLOCK_SECONDS`), not raw
  Whisper cues, so each embedding is robust and clustering yields a handful of
  speakers instead of hundreds.
- Settings: identify/cluster thresholds; a dedicated **Voiceprints screen**
  (`VoiceprintsDialog.qml`) to enroll, re-enroll and reset saved speakers.
- Post-job: `VoiceprintEnrollmentController` + `VoiceprintEnrollmentDialog.qml`
  let the user tune a **merge-similarity slider** (live re-cluster), name each
  detected `Speaker N` (enrolls its **average centroid** globally) and then
  **reprocess** the timeline with the new names. Each row has **▶ play** (a
  sample segment from the original recording) and **■ stop**.

Remaining (open items §7): tune thresholds on real audio.

Batch jobs run voiceprints too — the batch worker wires the same voiceprint
store and embedder as a single job, using each queued job's own
`voiceprint_enabled` flag.
