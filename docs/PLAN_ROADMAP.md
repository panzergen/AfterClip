# Plan: Version roadmap

This is the release map for AfterClip. It turns the phase plan in
[PLAN_PROMPT_PACKS.md](PLAN_PROMPT_PACKS.md) into concrete version numbers, so
"what is next" has one answer and each phase has an exit gate.

Status: **planning only**. The dates are deliberately absent; a version ships
when its exit criteria pass, not when a calendar says so.

## 1. Where we are

| Release | State | Contents |
|---|---|---|
| **0.3.0** | tagged `v0.3.0` (2026-10-20) | First public release: transcription, reports, topics, vision, voiceprints, batch, CLI/MCP. |
| **0.4.0** | in progress | Phase 1 (prompt scope/preset semantics) is on `main`; report-quality fixes and `--reuse-transcription` are on `prompt-fix`. |
| **0.5.0** | planned | Phase 2 — content packs and starter prompts. |
| **0.6.0** | planned | Phase 3 — vision synthesis, structured output, frame budget. |
| **0.7.0** | planned | Phase 4 — narrative continuity. |
| **0.8.0** | proposed | Stabilization only; no new features. |
| **1.0.0** | proposed | First stable release and compatibility promise. |

## 2. Release rules

- **SemVer.** While the major version is `0`, a **minor** release (`0.4.0`,
  `0.5.0`, …) carries a phase or a user-visible feature set; a **patch**
  (`0.4.1`, …) carries fixes only. Breaking changes are allowed in a minor
  release during `0.x`, but they must be called out in the changelog.
- **One source of truth.** `src/app/version.py` is the version; the package
  metadata, Windows executable metadata and the GUI read it. Never edit the
  generated build files by hand.
- **Tag after the checklist.** A version is tagged `vX.Y.Z` only after
  [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md), the phase acceptance criteria
  below, and an end-to-end job on real media pass.
- **Changelog first.** Move the `[Unreleased]` section of
  [../CHANGELOG.md](../CHANGELOG.md) to `[X.Y.Z] — YYYY-MM-DD` in the release
  commit. The version bump and the changelog move land together.
- **No phase on an unverified phase.** Phase N+1 does not start until Phase N's
  exit criteria pass on a real job, not only in unit tests.
- **Patches stay in their phase.** A `0.4.x` patch does not sneak in a Phase 2
  feature. If a fix is large enough to need a new prompt pack, it waits.

## 3. 0.4.0 — Report quality and prompt scope

**Theme:** make the current reports trustworthy before adding new content types.

**Included**

- Phase 1: full prompt snapshots per preset, replace/inherit/legacy modes,
  session-custom prompts, the `Applied`/`Inherited`/`Custom`/`Legacy` badge,
  and batch/CLI/MCP using the resolved prompt set.
  See [PLAN_PRESET_PROMPT_SCOPE.md](PLAN_PRESET_PROMPT_SCOPE.md).
- Report-quality fixes:
  - multi-paragraph chat preambles are removed from summaries, including the
    HTML report when it reuses a cached summary;
  - `## Topics` is no longer folded into **Key Highlights**;
  - topic titles follow the selected report language, or the transcript
    language when no language is selected;
  - a resumed job re-runs text analysis once instead of reusing a report with
    the old preamble;
  - vision descriptions that come back as only `[none]` are retried once with
    the built-in screen prompt, explicit blank frames are marked, and the
    built-in prompt covers slides, browser/app pages and meeting windows;
  - report language is a separate per-job selection. With no selection the
    report is English; a selected language applies to summary, highlights,
    vision text and topics, with a rewrite guard for summaries/highlights and
    the topic-title guard.
- CLI `--reuse-transcription` (`--reuse`): reuse the latest completed
  transcription for the same input, skip Whisper, and restore speaker labels
  from `Voiceprints.json`.
- Long-report output: raise or expose the Ollama `num_predict` cap so a long
  summary is not cut mid-sentence. **Open item; release blocker.**

**Exit criteria**

1. The four report issues are verified on the real `ViPanel V2.0` job using the
   reuse command: clean summary, highlights without topics, topics once, all
   titles in the report language.
2. A resumed job keeps its speaker names.
3. A long summary is complete (not truncated) with the default local model.
4. `pytest`, the Qt UI suite and `ruff check` pass.
5. The release checklist and a clean-machine smoke test pass.

## 4. 0.5.0 — Content packs (Phase 2)

**Theme:** the user can pick what kind of media they are processing.

**Included**

- Six starter packs: `meeting` (unchanged behaviour), `slides`,
  `software_demo`, `product_demo`, `narrative`, `travel_documentary`.
- Starter prompt text only; **no built-in active presets** and no automatic
  content-type detection.
- Pack-specific `vision_frame`, `summary`, `summary_combine`, `highlights`,
  `topic_segmentation` and `topic_title` drafts.
- Optional placeholders `{task}` and `{timestamp}`, with a required/optional
  validator split so existing templates stay valid.
- A defined structured JSON schema per pack; Markdown remains the primary
  report (`AI_Analysis.json` writing is Phase 3).
- See [PLAN_CONTENT_PACKS.md](PLAN_CONTENT_PACKS.md).

**Exit criteria**

- `meeting` output is unchanged for an existing job.
- Every pack has one real sample job and the prompt text is tuned against it.
- Old templates without the new optional placeholders still validate and run.
- Loading a starter into a preset, saving it, and applying it works in the GUI,
  CLI and batch.

## 5. 0.6.0 — Vision synthesis and structured output (Phase 3)

**Theme:** a video with little speech still gets a useful report.

**Included**

- `vision_synthesis`: per-frame descriptions become timestamped scene/section
  summaries.
- `{vision_context}` fed into summary, highlights and topic segmentation.
- `AI_Analysis.json` next to `AI_Analysis.md`.
- Visual highlights and scene-based topics.
- Frame budget: selectable vision sampling density, a maximum frame count and a
  vision resolution, with lower defaults for narrative/travel.
- See [PLAN_VISION_SYNTHESIS.md](PLAN_VISION_SYNTHESIS.md).

**Exit criteria**

- A low-speech sample gets a summary grounded in the frames.
- The frame budget is respected; the job does not analyze every extracted
  frame.
- `AI_Analysis.json` validates against the Phase 2 schema.
- The Phase 2 packs still run with the new context and without it.

## 6. 0.7.0 — Narrative continuity (Phase 4)

**Theme:** stable characters across a long narrative video.

**Included**

- Character sheet and rolling scene context, only for the `narrative` pack.
- User-editable character names after the first pass.
- No face recognition or biometric identity database.
- See [PLAN_NARRATIVE_CONTINUITY.md](PLAN_NARRATIVE_CONTINUITY.md).

**Exit criteria**

- The same character is described consistently across distant scenes.
- Renaming a character updates the final report.
- A job without a character sheet produces the Phase 3 output unchanged.

## 7. 0.8.0 — Stabilization (proposed)

**Theme:** no new features; make the `0.x` line safe to depend on.

Candidate work, to confirm before this version is scheduled:

- long-job memory and disk behaviour, cancellation at every step;
- packaging, installer metadata and a clean-machine matrix;
- settings/preset migration from `0.3.0` and from legacy prompt overrides;
- accessibility and keyboard navigation;
- documentation pass and a complete sample gallery.

## 8. 1.0.0 — Stable release (proposed)

The first compatibility promise:

- settings, presets, prompt templates and output file names are stable;
- a documented migration path from `0.3.0` onward;
- no silent prompt or schema changes within `1.x`;
- the full acceptance matrix from Phases 1-4 passes on Windows;
- release notes describe every breaking change since `0.3.0`.

## 9. Immediate next three actions

1. Finish the `0.4.0` acceptance run on `ViPanel V2.0` and fix the long-report
   truncation.
2. Merge `prompt-fix`, bump `src/app/version.py` to `0.4.0`, move
   `[Unreleased]` to `[0.4.0]`, tag `v0.4.0`.
3. Start Phase 2 with the `slides` pack first, because it already has a
   hand-made prompt set in use and is the quickest real sample to validate.

## 10. Phase-to-version map

| Phase | Version | Document |
|---|---|---|
| 1 — Prompt scope and preset semantics | `0.4.0` | [PLAN_PRESET_PROMPT_SCOPE.md](PLAN_PRESET_PROMPT_SCOPE.md) |
| 2 — Content packs | `0.5.0` | [PLAN_CONTENT_PACKS.md](PLAN_CONTENT_PACKS.md) |
| 3 — Vision synthesis and structured output | `0.6.0` | [PLAN_VISION_SYNTHESIS.md](PLAN_VISION_SYNTHESIS.md) |
| 4 — Narrative continuity | `0.7.0` | [PLAN_NARRATIVE_CONTINUITY.md](PLAN_NARRATIVE_CONTINUITY.md) |
| Stabilization | `0.8.0` (proposed) | this document |
| Stable release | `1.0.0` (proposed) | this document |
