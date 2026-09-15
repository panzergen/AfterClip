# Presets

Phase 4 (WS-B) lets you save a whole job configuration as a named **preset** and
reapply it with one click. Presets bundle:

- Whisper model, transcription language, report language
- AI analysis / vision toggles and the selected models
- Frame extraction modes, interval, sensitivity, resolution
- Transcript segment length and the embedded-frames report toggle
- Any customized prompt templates (only the ones changed from the defaults)

## Using presets

In the right-hand **Advanced** panel:

- **Preset** — pick one, then **Apply** to load it into the form.
- **Save preset** — type a name and press **Save** to capture the current form.
  Saving with an existing name overwrites that preset.
- **Delete** — remove the selected preset.

Applying a preset writes its prompt overrides into the prompt store, so the
next job uses the preset's templates too. Presets without prompt overrides leave
your current templates untouched.

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
no presets. Presets persist across restarts.
