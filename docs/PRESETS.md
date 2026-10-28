# Presets

Phase 4 (WS-B) lets you save a whole job configuration as a named **preset** and
reapply it with one click. Presets bundle:

- Whisper model, transcription language, report language
- AI analysis / vision toggles and the selected models
- Frame extraction modes, interval, sensitivity, resolution
- Transcript segment length and the embedded-frames report toggle
- Prompt templates (full snapshot, or none — see below)

## Prompt modes (Phase 1)

Each preset has a prompt mode:

- `replace` (default): carries a **full snapshot of all nine templates**.
  Applying it replaces the global prompt set, so switching presets never leaks
  prompts from the previous one. A preset saved from defaults restores defaults.
- `inherit`: carries no prompts. Applying it leaves your current prompts
  untouched.
- `legacy-partial`: old presets that only have `prompt_overrides`. Applying
  them merges over the current prompts (pre-Phase-1 behaviour). Re-save the
  preset to convert it to a full snapshot.

## Using presets

In the right-hand **Advanced** panel:

- **Preset** — pick one, then **Apply** to load it into the form. The
  `Prompts:` badge shows `Applied`, `Inherited`, `Legacy`, or `Custom`.
- **Save preset** — type a name, choose **Include prompts (recommended)**, and
  press **Save** to capture the current form. Unchecked stores job settings
  only (`inherit`). Saving with an existing name overwrites that preset.
  Saving with prompts also writes them to the global prompt store, so the
  preset is active right away.
- **Use preset prompts** — shown when the badge is `Custom`. Discards your
  unsaved prompt edits and applies the selected preset's prompts.
- **Delete** — remove the selected preset.

Unsaved prompt edits are used for the next job only and mark the preset
`Custom`. They are never written to `prompts.json` and are never silently
discarded by Apply. `Save` in the prompt editor writes one template to the
global store only — the selected preset is unchanged. Use **Save to 'preset'**
in the prompt dialog (or re-save the preset with prompts included) to store
the edit into that preset's snapshot.

The prompt dialog has its own preset selector, Apply, Create preset and
Save-to-preset actions, so per-preset editing no longer requires going back
to the main screen. Changing the preset in the dialog loads that preset's
prompts into the editor immediately (the caption reads
`Editing 'name' — Prompts: <badge>`); unsaved edits are discarded and the
status line says so. The main screen's Apply instead keeps unsaved edits and
marks the badge `Custom`.

Batch jobs capture the resolved prompts when they are enqueued, so changing a
preset mid-batch cannot change a queued job.

## Storage

`%LOCALAPPDATA%\AfterClip\presets.json` (see `PLATFORMS.md` for other OSes):

```json
{
  "version": 1,
  "presets": [
    {"name": "meeting", "whisper_model": "small", "prompt_overrides": {"summary": "..."}}
  ]
}
```

Malformed entries are skipped on load; a missing or corrupt file simply yields
no presets. Presets persist across restarts. Old files without `prompt_mode`
are inferred: a full `prompts` snapshot loads as `replace`, a non-empty
`prompt_overrides` loads as `legacy-partial`, otherwise `inherit`.
