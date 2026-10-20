# Troubleshooting

## The app does not start (packaged build)

- The release is a **one-directory bundle**. `AfterClip.exe` needs the
  `_internal\` folder beside it — do not move the exe alone.
- Run `AfterClip.exe` from an Explorer/console window once if antivirus blocks
  it; unsigned executables commonly trigger SmartScreen. Whitelist the folder
  or sign the build (see `PACKAGING.md`).
- A native crash writes a Python stack trace to
  `<data dir>/logs/crash.log` (see `PLATFORMS.md` for the path).

## "FFmpeg is missing" / "FFprobe is missing"

Install FFmpeg and add it to `PATH`, then reopen the app. The status LED tooltip
shows which tools are found. Verify in a terminal with `ffmpeg -version`.

## "Whisper is missing"

```powershell
pip install openai-whisper
```
`whisper.exe` must be in the same environment's `Scripts` folder or on `PATH`.

## Ollama is offline / AI controls are disabled

Local AI requires Ollama running at its default endpoint. Start it
(`ollama serve`) and press the status LED to refresh. When Ollama is offline the
Whisper transcription flow still works; only local AI analysis is skipped.

## "Cloud AI consent required" keeps appearing

Consent is stored per provider in `settings.json`. Accept it in the dialog, or
grant it up-front in **Settings → Cloud provider → Grant consent**. If it
reappears, the settings file may be read-only or a newer schema (see below).

## "No API key stored" / "credential manager" error

- Save the key in **Settings**; it is stored in the OS credential manager.
- The key name depends on the provider: `gemini_api_key`, `openrouter_api_key`
  or `opencode_go_api_key` (OpenCode Go and Zen share one platform key).
- A headless Linux session without Secret Service/KWallet cannot store keys;
  the Settings screen reports this instead of crashing.
- After **Delete key**, cloud jobs stop until a new key is saved.

## The provider rejects the request

- **401** means the key is wrong or expired — re-enter it in Settings.
- **403** usually means the account or model is not entitled to use that
  provider.
- **404** means the selected model does not exist for that provider. Press
  **Load models** in Settings to fetch the live list and pick one.
- AfterClip does not silently fall back to another provider: if a selected
  model is unavailable the job fails with that error rather than sending your
  transcript somewhere you did not choose.

## Output directory problems

Before a job starts AfterClip checks that the output directory is writable and
has enough free space. Fix the reported path/permissions or free up space and
retry. Long Windows paths (> 260 chars) may also need long-path support enabled.

## Preview does not load

- Audio files have no video preview by design.
- If preview fails, the message appears in the status line; transcription can
  still be started.
- Preview frames are cached under `<workspace>\.cache\previews`; deleting that
  folder forces a rebuild.

## "No previous transcription" when I expected a resume

Reuse/resume searches for job folders **under** the selected output directory.
If the output directory is itself a job folder (it contains `job_state.json`),
AfterClip detects this, switches to its parent and tells you. Always select the
folder that contains job folders (e.g. `...\Output-Folder`), not a job folder
like `...\Output-Folder\<job>`.

On resume, completed **media preparation, transcription, frame extraction,
text analysis and vision analysis** are reused; other steps re-run.

## Job failed / cancelled

- Check `Summary_Report.md` and the `Processing Steps` table for the failing
  step, and the app log for details.
- Cancelled/interrupted jobs keep their `job_state.json`; re-running the same
  file resumes completed steps instead of repeating them.
- If Whisper or FFmpeg failed, the partial outputs and the error are preserved.

## A job seems stuck

Long Whisper runs on CPU can take minutes and show no progress percentage for a
while. Confirm the process is alive in Task Manager. Cancel with `Ctrl+.` to
stop it safely.

## "settings schema is newer than supported"

The `settings.json` was written by a newer AfterClip version. AfterClip refuses
to downgrade it (to avoid dropping unknown settings). Update AfterClip, or back
up and remove the file to start fresh.

## Where are the logs?

`<data dir>/logs/app.log` (`PLATFORMS.md` has the per-OS path). Secrets are
redacted automatically. The status tooltip and `Summary_Report.md` cover most
environment/usage questions.

## Still stuck?

Collect: AfterClip version (`Settings`/`version.py`), OS, Python version,
FFmpeg/Whisper versions, `Summary_Report.md`, `job_state.json`, and the tail of
`app.log` (no API keys — they are redacted).
