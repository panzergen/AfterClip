# Plan: Prompt scope and preset semantics

Phase 1 of [PLAN_PROMPT_PACKS.md](PLAN_PROMPT_PACKS.md). Foundation only; no
prompt text changes in this phase.

Status: **implemented** (2026-10-26). The sections below describe the shipped
behaviour; the unit-test list in §7 is the acceptance record.

## 1. Current behaviour (verified)

- `PromptSet` is one global set of nine templates, loaded from `prompts.json`.
- `PresetsController._current_prompt_overrides()` saves **only templates that
  differ from `DEFAULT_PROMPTS`**.
- `PresetsController.applySelected()` does
  `base.with_overrides(preset.prompt_overrides)` — a **merge**, not a replace.
- A preset with no prompt overrides leaves the current prompts untouched.
- A preset cannot restore a built-in default, because defaults are filtered out
  when saving.
- Applying a preset writes the merged result to the global prompt store, so it
  affects every later job.
- `batch_worker.py` builds providers without passing prompts, so batch jobs use
  the built-in defaults and ignore custom prompts entirely.
- CLI/MCP apply preset overrides on top of the global prompts, so they have the
  same leak/merge behaviour.

Consequences:

- Switching from a “Travel” preset to a “Slides” preset can leave travel prompts
  active for templates the slides preset did not customize.
- A preset that is supposed to mean “use defaults” cannot do so.
- Batch output can silently differ from single-job output.

## 2. Target semantics

### 2.1 Three prompt states

| State | Stored where | Used by next job | Badge |
|---|---|---|---|
| **Saved / global** | `prompts.json` | yes | `Saved` |
| **Preset snapshot** | inside the selected preset | yes, after applying | `Applied` |
| **Session custom** | in memory only | yes, for the next job | `Custom` |

The prompt editor can be in one of these states. Unsaved edits are session
custom and are **not** written to `prompts.json`.

### 2.2 Preset prompt modes

Add a prompt mode to each preset:

- `replace` (default): the preset carries a full snapshot of all nine templates
  and, when applied, replaces the global prompt set.
- `inherit`: the preset carries no prompt snapshot and leaves the global prompt
  set untouched.
- `legacy-partial`: only for old presets that have `prompt_overrides`. Keep the
  old merge behaviour and show a “Legacy prompts” note until the user re-saves.

A full snapshot must contain **all nine resolved templates**, including values
equal to the built-in defaults. This is what makes default restoration possible.

### 2.3 Apply flow

1. If the preset has a `replace` snapshot and the editor has **no** unsaved
   changes:
   - write the full snapshot to the global prompt store;
   - clear the session-custom flag;
   - badge `Applied`.
2. If the preset has a `replace` snapshot but the editor **has** unsaved changes:
   - keep the unsaved prompts as session custom by default;
   - apply the preset’s job settings;
   - badge `Custom`;
   - show an inline action “Use preset prompts” that discards the unsaved edits
     and applies the snapshot.
3. If the preset is `inherit`:
   - apply job settings only;
   - leave prompts as they are;
   - badge `Inherited` (or `Custom` if there are unsaved edits).
4. Never silently discard unsaved prompt edits.

### 2.4 Save flow

- `Save prompts` in the prompt editor writes the current resolved set to
  `prompts.json` and clears the session-custom flag.
- `Save preset` gets an **Include prompts (recommended)** checkbox, default on:
  - checked: store a full snapshot in the preset **and** write the same full set
    to the global prompt store;
  - unchecked: set `prompt_mode: inherit` and store no snapshot.
- Saving a preset over an existing name replaces the snapshot and settings.
- “Reset to default” loads built-in defaults into the editor but still requires
  `Save prompts` (or `Save preset`) to persist them, as today.

### 2.5 What “Custom” means

The preset badge shows `Custom` when the prompt set used for the next job is not
the selected preset’s saved snapshot. Typical cases:

- the user edited a prompt and did not save it;
- the user applied a preset after editing prompts and chose to keep the edits;
- the selected preset is `inherit` and the global prompts differ from the
  built-in defaults.

`Custom` is a warning, not an error. The job still runs with the current prompts.

## 3. Data model changes

### 3.1 `Preset`

```python
@dataclass(frozen=True)
class Preset:
    ...
    prompt_mode: str = "replace"          # replace | inherit | legacy-partial
    prompts: dict[str, str] | None = None # full snapshot when mode == replace
    prompt_overrides: dict[str, str] = field(default_factory=dict)  # legacy only
```

- New presets use `prompt_mode="replace"` and a full `prompts` dict.
- Old presets without `prompts` but with `prompt_overrides` load as
  `legacy-partial`.
- `to_dict()` / `from_dict()` ignore unknown keys as today.
- Add a schema version bump only if needed; otherwise keep `version: 1` and treat
  the new fields as optional.

### 3.2 Prompt resolution

Add a small resolver, e.g. `application/prompt_scope.py`:

```python
@dataclass
class ResolvedPrompts:
    prompt_set: PromptSet
    source: str        # global | preset | custom
    preset_name: str = ""
```

Rules:

- session custom wins for the next job;
- otherwise preset snapshot after apply;
- otherwise global store;
- otherwise built-in defaults.

The request/job should carry the resolved prompts or a reference that is stable
for the duration of the job. Prompts must not be re-read mid-job.

## 4. Batch, CLI and MCP

### 4.1 Batch

- `BatchJob` gains a serialized full `PromptSet` (or `prompts` dict) captured at
  enqueue time.
- `batch_worker._run_job()` passes that prompt set to
  `build_text_provider(..., prompts)` and `build_vision_provider(..., prompts)`.
- This fixes the current bug where batch ignores custom prompts.
- Because prompts are captured at enqueue, changing a preset mid-batch cannot
  change a queued job.

### 4.2 CLI

- `--preset NAME` applies the preset’s full snapshot with **replace** semantics.
- A `legacy-partial` preset keeps the old merge behaviour.
- `--no-preset` uses the global prompt store.
- Add `--prompts PATH` only if a separate prompt file is useful; not required.

### 4.3 MCP

- Same resolver as the CLI.
- `list_presets` should expose `prompt_mode` and whether prompts are included.

## 5. UI changes

- `AdvancedPanel.qml`: show a small badge next to the preset selector:
  `Applied`, `Inherited`, `Custom`, `Legacy`.
- `PromptsDialog.qml`: show “Unsaved changes — used for the next job” when the
  editor is dirty.
- `Save preset`: add the “Include prompts” checkbox and a short help text.
- Applying a preset while dirty: keep edits by default; offer “Use preset
  prompts” in the status line.
- Prompt editor should show which template is currently customised vs default
  (optional, useful for debugging).

## 6. Migration

- Existing `prompts.json` is still the global store; no migration needed.
- Existing presets with `prompt_overrides` become `legacy-partial`.
- When a legacy preset is re-saved, offer to convert it to a full snapshot.
- No prompt text changes in Phase 1, so existing output stays byte-identical
  unless the user applies a preset.

## 7. Tests and acceptance

Unit tests:

- `Preset.capture` stores all nine templates when prompts are included.
- Applying a `replace` preset overwrites every template, including defaults.
- Applying an `inherit` preset leaves prompts unchanged.
- Applying a legacy preset keeps old merge behaviour.
- Unsaved custom survives apply and is used for the next job.
- `Save preset` with prompts included updates the global store.
- Reset-to-default + save restores the built-in text.
- Batch job captures prompts at enqueue and passes them to providers.
- CLI/MCP preset application uses replace semantics.

Acceptance criteria:

1. Two presets with different full prompt sets switch cleanly in both directions.
2. A preset saved from defaults can restore all defaults.
3. Unsaved edits are used for the next job and never overwrite `prompts.json`.
4. A batch of three jobs uses the prompt set captured when each was enqueued.
5. Existing legacy presets still work without a manual migration step.

## 8. Out of scope

- Prompt text changes (Phase 2).
- Vision synthesis, JSON output and frame sampling (Phase 3).
- Character sheet and rolling context (Phase 4).
- Automatic preset selection (deferred).
