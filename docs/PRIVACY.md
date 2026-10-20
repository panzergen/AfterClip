# Privacy and Cloud Consent

AfterClip is local-first. Nothing leaves the machine unless you explicitly
select a cloud provider, store a key for it, grant consent, and start a job.

## What stays local

- Input video/audio files (video is **never** uploaded by policy; see
  `infrastructure/cloud_policy.py`).
- Local Whisper transcription (the audio is transcribed on this machine).
- Ollama text/vision analysis (local provider; no network request).
- Recordings, previews, frames and job outputs.
- Voiceprints (speaker embeddings) are local-only: stored as float vectors in a
  local `voiceprints.json`, never uploaded, and never included in reports.

## What a cloud job sends

Only when a **cloud** provider is selected and consent has been granted. The
cloud providers are:

| Provider | Id | Data that can leave the machine |
| --- | --- | --- |
| Gemini | `gemini` | transcript text, single frame images |
| OpenRouter | `openrouter` | transcript text, single frame images |
| OpenCode Go | `opencode_go` | transcript text, single frame images |
| OpenCode Zen | `opencode_zen` | transcript text, single frame images |

Ollama (`ollama`) is a **local** provider and never makes a network request.

What is sent, in detail:

- **Text analysis:** the transcript text segments.
- **Vision analysis:** single extracted frame images (PNG/JPEG), never the video.

The pre-job confirmation dialog states exactly what will be sent, naming the
provider and model, and warns that cloud API usage may incur charges. The
request is blocked until you accept.

### Per-provider differences

- **OpenCode Go** and **OpenCode Zen** share one platform key
  (`opencode_go_api_key`); saving it under either provider unlocks both
  catalogs.
- Each provider is a separate consent entry (`cloud_consent_<provider>`), so
  granting consent for one does not grant it for another.
- Each provider uses its own endpoint. The endpoint a key is sent to is the one
  listed in `docs/PROVIDERS.md`.

## Consent storage and revocation

- Consent is stored in `settings.json` under `cloud_consent_<provider>` with the
  grant timestamp. It is a non-secret preference.
- Grant or revoke it any time in **Settings → Cloud provider**. Revoking makes
  the next cloud job ask for confirmation again.
- Deleting the API key stops all cloud requests entirely.

## Keys

- API keys live in the OS credential manager (`keyring`), never in
  `settings.json` or logs.
- Key values are registered with the log redaction filter and replaced with
  `[REDACTED]` in log messages and tracebacks.
- Rotating a key unregisters the previous value from the redaction set.

The credential names are `gemini_api_key`, `openrouter_api_key` and
`opencode_go_api_key` (shared by OpenCode Go and Zen), under the `afterclip`
keyring service.

## Voiceprint data on disk

Enrolling a voiceprint derives a **biometric embedding** from a voice sample.
These are stored locally and are never uploaded, but they are written into the
job output folder as `Voiceprints.json` alongside the reports. Treat that file
as sensitive: do not share an output folder that contains it without saying
so. Delete the output folder to remove the embeddings.

## Diagnostics

`collect_diagnostics()` reports tool availability, Python/platform versions,
GPU name/VRAM and free disk space. It never includes API keys, settings values
or media content.
