# AfterClip

Windows-first desktop application for local media transcription. This repository is the new modular implementation; the legacy `whisper_gui2.py` remains outside it.

Repository: <https://github.com/panzergen/AfterClip>

## Clone

```powershell
git clone https://github.com/panzergen/AfterClip.git
```

## Phase 1

The first vertical slice supports selecting one media file, selecting an output directory, running FFmpeg conversion when needed, and producing Whisper transcript files without blocking the UI. The provider boundary is mockable and cancellation is supported for the active job.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Install FFmpeg/FFprobe and `openai-whisper` separately, then start the app:

```powershell
pip install openai-whisper
```

```powershell
afterclip
```

On Windows, `run_afterclip.bat` can also be double-clicked after installing the dependencies.

## Commands

```powershell
pytest                  # unit/regression suite (UI tests deselected by default)
pytest -m ui            # opt-in Qt UI tests (set QT_QPA_PLATFORM=offscreen for headless runs)
pytest --cov=app.application --cov=app.infrastructure   # coverage
```

## Documentation

- `docs/USER_GUIDE.md` — setup, tabs, outputs and workflow
- `docs/PROMPTS.md` — editable prompt templates and placeholders
- `docs/PRESETS.md` — save/apply named job presets
- `docs/TRANSCRIPT_FILTER.md` — Whisper hallucination filtering
- `docs/FORECAST.md` — pre-start time estimates from past jobs
- `docs/TROUBLESHOOTING.md` — common problems and fixes
- `docs/PACKAGING.md` — Windows release build
- `docs/PLATFORMS.md` — platform support, paths and secret backends
- `docs/PRIVACY.md` — what stays local and what a cloud job sends
- `docs/RELEASE_CHECKLIST.md` — pre-release automated + manual checks

## Keyboard shortcuts

| Shortcut | Action |
| --- | --- |
| `Ctrl+O` | Browse for a media file |
| `Ctrl+Enter` | Start processing |
| `Ctrl+.` | Cancel the running job |
| `Ctrl+1`..`Ctrl+4` | Switch to Media / Record / Batch / History |
| `Ctrl+,` | Open Settings |
| `Tab` / arrows | Move focus between controls |

## Build a Windows release

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1 -Clean -Zip
```

This produces `release\AfterClip\AfterClip.exe` (one-directory bundle) and, with
`-Zip`, `release\AfterClip-<version>-win64.zip`. The application version lives in
`src/app/version.py` and is the single source of truth for package metadata and
the executable version resource. See `docs/PACKAGING.md` for the full build,
clean-machine smoke test and current release gaps (code signing, installer,
FFmpeg/Whisper bundling).

## Current Features

- PySide6 Qt Quick (QML) two-column Windows-first desktop UI; all UI state lives in
  testable Python controllers (`app/ui/controllers/`) exposed to the QML views
  (`app/ui/qml/`) as context properties
- Native QMediaPlayer playback inside the QML scene (shared QVideoSink) with a
  WMF/FFmpeg-safe source-switch guard
- Video preview caching and frame navigation
- Media / Record / Batch / History tabs
- Whisper transcription through a background worker
- FFmpeg WAV preparation and clip range processing
- Interval and scene-change frame extraction (full / 1024px / 768px resolution)
- Microphone recording to the selected output directory
- Speaker VTT parsing with graceful fallback when the file is missing or malformed
- Master Timeline Markdown and multimodal JSONL outputs with speaker badges
- Transcript segments merged into readable paragraphs (30s default, speaker-aware breaks)
- Optional AI text analysis (summary and timestamped highlights) via **Ollama (local)** or **Gemini (cloud)** behind a `TextAnalysisProvider` port
- Optional AI vision analysis (frame descriptions) via the same providers behind a `VisionProvider` port; video uploads are impossible by policy
- Explicit, revocable cloud consent: a pre-job confirmation names the provider/model and what leaves the machine, blocks the job until accepted, and warns about API charges (see `docs/PRIVACY.md`)
- Per-job cloud usage (requests, tokens, images) and an approximate cost estimate are recorded in `job_state.json` and the report
- Provider-grouped model dropdowns with live model lists and capability filtering (vision dropdown only shows image-capable models)
- Separate transcription language and report language (summaries, highlights, vision text)
- `FullReportAndTimeline.htm` human-readable report with summary, highlights, full transcript and embedded frames; `Master_Timeline.md` stays lean for AI consumption
- `VisionProvider` port ready for additional cloud providers (OpenRouter planned)
- Metadata, report versioning, checkpoint state, progress, and step timings

## Where things are stored

- **Settings:** per-user data directory — `%LOCALAPPDATA%\AfterClip\settings.json`
  on Windows, `~/Library/Application Support/AfterClip/settings.json` on macOS and
  `$XDG_DATA_HOME/AfterClip/settings.json` (or `~/.local/share/...`) on Linux.
  Non-secret preferences only; `settings.json` is schema-versioned and migrated
  automatically.
- **API keys:** OS credential manager via `keyring` (Windows Credential Manager,
  macOS Keychain, Linux Secret Service) — service `afterclip`, name `gemini_api_key`.
  Never written to disk in plaintext, redacted from logs.
- **Application log:** `<data directory>/logs/app.log`

See `docs/PLATFORMS.md` for the platform support matrix, path/secret-backend
mapping and current gaps.

The next planned development slice is the batch queue (T08b/T26b), followed by job history and a log panel.
