# Plan: Prompt packs, presets and vision-heavy videos

Status: **planning only**. No application code or prompt text has changed yet.

This is the master index for the next phases. It records the decisions from the
2026-10-26 planning chat and links the detailed planning documents.

## Decisions locked in

| # | Topic | Decision |
|---|---|---|
| 1 | Output shape | Produce **both** a readable Markdown report and a structured JSON sidecar. |
| 2 | Demo videos | **Software demo** and **physical product demo** are separate content types/settings. |
| 3 | Narrative continuity | Character sheet + rolling context are wanted, but go in the **last phase**. |
| 4 | Travel/documentary | Identify landmarks/places when visually supported. Do **not** extract prices, routes, opening hours or bookings. |
| 5 | Language | Translate visible slide/sign/UI text into the selected report language. Keep proper nouns and brand names in their original spelling. |
| 6 | Frame budget | Do not analyze every extracted frame. Add selectable **vision sampling density** and **vision frame resolution**; lower defaults for narrative/travel. |
| 7 | Models | Keep the current behaviour: the user chooses local vs cloud provider/model. No change to model routing. |
| 8 | Prompt scope | Saved prompts update the global prompt store. Unsaved prompt edits are used for the next job only and mark the preset **Custom**. |
| 9 | Auto-detection | Leave auto-detection out for now. The user chooses the preset/content type manually. |
| 10 | Presets | Ship **no built-in active presets**. New content-type texts are starter prompt texts for user-created presets only. |
| 11 | Samples | The user has examples and can supply more; prompt tuning against real samples is part of the plan. |

## Content types (packs)

The plan uses six user-selectable packs:

1. `meeting` — existing behaviour, kept as-is.
2. `slides` — PowerPoint / Keynote / slide-based presentations.
3. `software_demo` — screen-recorded software or web app demo.
4. `product_demo` — physical product demonstration on camera.
5. `narrative` — movie, TV series, cartoon, scripted video.
6. `travel_documentary` — travel, scenery, landmark, factual documentary footage.

`travel_documentary` shares one base vision prompt. A narration-heavy
documentary may instead use the `narrative` pack; the user chooses.

## Phase map

- [x] **Phase 1 — Prompt scope and preset semantics** (foundation; no prompt text changes)
  - Full prompt snapshots per preset, replace-on-apply, defaults restorable.
  - Global-saved vs session-custom prompt behaviour and the `Custom` badge.
  - Batch, CLI and MCP use the resolved prompt set.
  - Optional-placeholder support in the validator.
  - See [PLAN_PRESET_PROMPT_SCOPE.md](PLAN_PRESET_PROMPT_SCOPE.md).

- [ ] **Phase 2 — Manual content-type presets and prompt packs**
  - Six starter prompt packs; no built-in active presets.
  - Manual preset/content-type selection only (no auto-detect).
  - Vision prompt rewritten per pack; summary/highlights/topic prompts rewritten.
  - New optional placeholders: `{task}`, `{timestamp}`.
  - Structured JSON schema defined for every pack; Markdown remains the primary report.
  - See [PLAN_CONTENT_PACKS.md](PLAN_CONTENT_PACKS.md).

- [ ] **Phase 3 — Vision synthesis, structured output and frame budget**
  - Add `vision_synthesis`: turn per-frame descriptions into scene/section summaries.
  - Feed vision context into summary, highlights and topic segmentation.
  - Write `AI_Analysis.json` next to `AI_Analysis.md`.
  - Visual highlights and scene-based topics.
  - Selectable vision sampling density, max frames and frame resolution per preset.
  - Add optional `{vision_context}` placeholder.
  - See [PLAN_VISION_SYNTHESIS.md](PLAN_VISION_SYNTHESIS.md).

- [ ] **Phase 4 — Narrative character sheet and rolling context** (last)
  - Only for the `narrative` pack.
  - Stable character references, user-editable names, rolling scene context.
  - See [PLAN_NARRATIVE_CONTINUITY.md](PLAN_NARRATIVE_CONTINUITY.md).

## Explicitly deferred

- Automatic media-type classification, Tier-3 LLM refinement and automatic
  preset application.
- Built-in presets.
- Cross-episode character sheets for TV series (possible later; not in Phase 4
  unless requested).
- Extracting prices, routes, opening hours or booking information from travel
  videos.

## Assumptions to confirm before implementation

1. `AI_Analysis.json` is the sidecar name; one JSON object per job with a
   `pack` field and pack-specific `data`.
2. Unsaved prompt edits are **session-only** and are lost on app restart.
3. `Save preset` with “Include prompts” checked writes the full prompt set to
   the global store immediately, so the preset is active right away.
4. Old presets that only contain `prompt_overrides` keep their legacy partial
   merge behaviour until re-saved as full snapshots.
5. No new model/provider routing is introduced; only prompt and frame controls.
