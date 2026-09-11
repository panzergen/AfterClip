# Privacy and Cloud Consent

AfterClip is local-first. Nothing leaves the machine unless you explicitly
select a cloud provider, store a key for it, grant consent, and start a job.

## What stays local

- Input video/audio files (video is **never** uploaded by policy; see
  `infrastructure/gemini/permissions.py`).
- Local Whisper transcription (the audio is transcribed on this machine).
- Ollama text/vision analysis (local provider; no network request).
- Recordings, previews, frames and job outputs.
- Voiceprints are not implemented yet; when added they are local-only.

## What a cloud job sends

Only when a cloud provider (currently Google Gemini) is selected and consent
has been granted:

- **Text analysis:** the transcript text segments.
- **Vision analysis:** single extracted frame images (PNG), never the video.

The pre-job confirmation dialog states exactly what will be sent, naming the
provider and model, and warns that cloud API usage may incur charges. The
request is blocked until you accept.

## Consent storage and revocation

- Consent is stored in `settings.json` under `cloud_consent_<provider>` with the
  grant timestamp. It is a non-secret preference.
- Grant or revoke it any time in **Settings → Gemini (cloud provider)**.
  Revoking makes the next cloud job ask for confirmation again.
- Deleting the API key stops all cloud requests entirely.

## Keys

- API keys live in the OS credential manager (`keyring`), never in
  `settings.json` or logs.
- Key values are registered with the log redaction filter and replaced with
  `[REDACTED]` in log messages and tracebacks.
- Rotating a key unregisters the previous value from the redaction set.

## Diagnostics

`collect_diagnostics()` reports tool availability, Python/platform versions,
GPU name/VRAM and free disk space. It never includes API keys, settings values
or media content.
