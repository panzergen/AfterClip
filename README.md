# AfterClip

[![CI](https://github.com/panzergen/AfterClip/actions/workflows/ci.yml/badge.svg)](https://github.com/panzergen/AfterClip/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![Platforms](https://img.shields.io/badge/platform-Windows%20primary-lightgrey.svg)](docs/PLATFORMS.md)

Windows-first desktop application for local media transcription. AfterClip turns
a recording into a transcript, a speaker-attributed timeline, a set of AI
highlights and a readable HTML report — on your own machine, with the cloud
optional and consented.

- **Local by default.** Whisper runs locally through FFmpeg. Ollama gives a
  fully offline AI path. Nothing is uploaded unless you pick a cloud provider
  and grant consent.
- **Consent you can see.** A pre-job dialog names the provider, the model and
  exactly what leaves the machine. Consent is revocable.
- **Keys stay out of files.** API keys live in the OS credential manager and are
  redacted from logs.
- **Reports you can read.** A lean `Master_Timeline.md` for AI consumption, a
  full `FullReportAndTimeline.htm` for humans, and multimodal JSONL for
  pipelines.

## Screens

The interface has four tabs — **Media**, **Record**, **Batch** and **History** —
over a two-column layout with the player and job form on the left and the
transcript and reports on the right.

## Install

### Windows (recommended)

Download the installer from the
[releases page](https://github.com/panzergen/AfterClip/releases), then install
the two external tools:

- [FFmpeg](https://ffmpeg.org/download.html) — both `ffmpeg` and `ffprobe` must
  be on `PATH`
- `openai-whisper` — `pip install openai-whisper`

These are **not bundled**: Whisper pulls in PyTorch (and CUDA, if you want
GPU acceleration), and bundling it would multiply the download size and the
antivirus false-positive rate.

### From source

```powershell
git clone https://github.com/panzergen/AfterClip.git
cd AfterClip
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pip install openai-whisper
afterclip
```

`run_afterclip.bat` can be double-clicked instead of running `afterclip`.

Python 3.12 or newer is required. macOS and Linux run from source; see
[docs/PLATFORMS.md](docs/PLATFORMS.md).

## Usage

1. Pick a media file and an output directory.
2. Choose a Whisper model and, optionally, frame extraction and AI analysis.
3. Press `Ctrl+Enter` to start. `Ctrl+.` cancels.

Outputs land in the job folder under your output directory:

| File | Contents |
| --- | --- |
| `Master_Timeline.md` | Chronological transcript with speaker badges, topics and highlights |
| `FullReportAndTimeline.htm` | The same content as a readable page, with embedded frames |
| `multimodal_timeline.jsonl` | One JSON object per segment, for pipelines |
| `AI_Analysis.md` | Summary and timestamped highlights |
| `Processing_Report.md` | Metadata, step timings and cloud usage |
| `job_state.json` | Checkpoint state, so an interrupted job can resume |

## Cloud providers

| Provider | Id | Kind |
| --- | --- | --- |
| Ollama | `ollama` | local |
| Gemini | `gemini` | cloud |
| OpenRouter | `openrouter` | cloud |
| OpenCode Go | `opencode_go` | cloud |
| OpenCode Zen | `opencode_zen` | cloud |

All cloud providers sit behind one OpenAI-compatible adapter (plus a dedicated
Gemini adapter) and share the same upload policy: text and single still frames
only — video upload is impossible by construction. See
[docs/PROVIDERS.md](docs/PROVIDERS.md).

## Commands

```powershell
afterclip                                  # GUI
afterclip run --input file.mp4 --output .  # headless
afterclip batch --input-dir . --output .   # headless queue
afterclip status                           # list known jobs
pytest                  # unit/regression suite (UI tests deselected by default)
pytest -m ui            # opt-in Qt UI tests (set QT_QPA_PLATFORM=offscreen for headless runs)
pytest --cov=app        # coverage
```

The CLI never imports PySide6. An MCP stdio server is also available; see
[docs/CLI.md](docs/CLI.md).

## Keyboard shortcuts

| Shortcut | Action |
| --- | --- |
| `Ctrl+O` | Browse for a media file |
| `Ctrl+Enter` | Start processing |
| `Ctrl+.` | Cancel the running job |
| `Ctrl+1`..`Ctrl+4` | Switch to Media / Record / Batch / History |
| `Ctrl+,` | Open Settings |
| `Tab` / arrows | Move focus between controls |

## Where things are stored

- **Settings:** per-user data directory — `%LOCALAPPDATA%\AfterClip\settings.json`
  on Windows, `~/Library/Application Support/AfterClip/settings.json` on macOS and
  `$XDG_DATA_HOME/AfterClip/settings.json` (or `~/.local/share/...`) on Linux.
  Non-secret preferences only; `settings.json` is schema-versioned and migrated
  automatically.
- **API keys:** OS credential manager via `keyring` (Windows Credential Manager,
  macOS Keychain, Linux Secret Service) — service `afterclip`, names
  `gemini_api_key`, `openrouter_api_key` and `opencode_go_api_key`. Never
  written to disk in plaintext, redacted from logs.
- **Application log:** `<data directory>/logs/app.log`

See [docs/PLATFORMS.md](docs/PLATFORMS.md) for the full path and secret-backend
mapping, and [docs/PRIVACY.md](docs/PRIVACY.md) for what a cloud job sends.

## Features

- PySide6 Qt Quick (QML) two-column Windows-first desktop UI; all UI state lives
  in testable Python controllers (`app/ui/controllers/`) exposed to the QML views
  (`app/ui/qml/`) as context properties
- Native QMediaPlayer playback inside the QML scene (shared QVideoSink) with a
  WMF/FFmpeg-safe source-switch guard
- Video preview caching and frame navigation
- Media / Record / Batch / History tabs, with job history and an in-app log tail
- Whisper transcription through a background worker, with cancellation and
  resume of completed steps
- FFmpeg WAV preparation and clip range processing
- Interval and scene-change frame extraction (full / 1024px / 768px resolution)
- Microphone recording, and system-audio capture where FFmpeg supports WASAPI
- Speaker VTT parsing with graceful fallback when the file is missing or
  malformed
- Master Timeline Markdown and multimodal JSONL outputs with speaker badges
- Transcript segments merged into readable paragraphs (30s default,
  speaker-aware breaks) plus a Whisper hallucination filter
- Optional AI text analysis (summary and timestamped highlights) via **Ollama
  (local)** or a cloud provider, behind a `TextAnalysisProvider` port
- Optional AI vision analysis (frame descriptions) via the same providers behind
  a `VisionProvider` port; video uploads are impossible by policy
- Explicit, revocable cloud consent: a pre-job confirmation names the
  provider/model and what leaves the machine, blocks the job until accepted, and
  warns about API charges (see [docs/PRIVACY.md](docs/PRIVACY.md))
- Per-job cloud usage (requests, tokens, images) and an approximate cost
  estimate, recorded in `job_state.json` and the report
- Provider-grouped model dropdowns with live model lists and capability
  filtering (the vision dropdown only shows image-capable models)
- Separate transcription language and report language
- Local voiceprints (optional `voiceprint` extra): identify speakers by voice
  and cluster unknowns into `Speaker N`, complementing the speaker VTT without
  overriding it
- Topic segmentation into per-topic report sections with AI-generated titles
- Media-type classification with per-type suggestions
- Pre-start time estimates from past jobs
- Optional completion sound (on by default): plays a bundled chime or a
  user-selected WAV when a job finishes or fails
- `FullReportAndTimeline.htm` human-readable report with summary, highlights,
  full transcript and embedded frames; `Master_Timeline.md` stays lean for AI
  consumption
- Metadata, report versioning, checkpoint state, progress and step timings

## Documentation

- [docs/USER_GUIDE.md](docs/USER_GUIDE.md) — setup, tabs, outputs and workflow
- [docs/PROMPTS.md](docs/PROMPTS.md) — editable prompt templates and placeholders
- [docs/PRESETS.md](docs/PRESETS.md) — save/apply named job presets
- [docs/TRANSCRIPT_FILTER.md](docs/TRANSCRIPT_FILTER.md) — Whisper hallucination filtering
- [docs/FORECAST.md](docs/FORECAST.md) — pre-start time estimates from past jobs
- [docs/PROVIDERS.md](docs/PROVIDERS.md) — cloud provider registry
- [docs/CLI.md](docs/CLI.md) — headless CLI and MCP server
- [docs/TOPICS.md](docs/TOPICS.md) — topic segmentation and its report outputs
- [docs/MEDIA_TYPE.md](docs/MEDIA_TYPE.md) — media-type classification and suggestions
- [docs/PLAN_TOPICS_HIGHLIGHTS.md](docs/PLAN_TOPICS_HIGHLIGHTS.md) — plan for topics/highlights refinements
- [docs/PLAN_VOICEPRINTS.md](docs/PLAN_VOICEPRINTS.md) — plan for local voiceprints
- [docs/PLAN_ROADMAP.md](docs/PLAN_ROADMAP.md) — release roadmap from `0.3.0` through `1.0.0`
- [docs/PLAN_PROMPT_PACKS.md](docs/PLAN_PROMPT_PACKS.md) — plan index for content-type prompt packs, presets and vision-heavy video
- [docs/PLAN_PRESET_PROMPT_SCOPE.md](docs/PLAN_PRESET_PROMPT_SCOPE.md) — full prompt snapshots, global vs custom prompts, batch propagation
- [docs/PLAN_CONTENT_PACKS.md](docs/PLAN_CONTENT_PACKS.md) — prompt drafts for slides, software/product demos, narrative and travel
- [docs/PLAN_VISION_SYNTHESIS.md](docs/PLAN_VISION_SYNTHESIS.md) — vision synthesis, structured output and frame sampling
- [docs/PLAN_NARRATIVE_CONTINUITY.md](docs/PLAN_NARRATIVE_CONTINUITY.md) — character sheets and rolling context for narrative video
- [docs/TEST_SCENARIOS.md](docs/TEST_SCENARIOS.md) — manual test scenarios for recent features
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — common problems and fixes
- [docs/PACKAGING.md](docs/PACKAGING.md) — Windows release build
- [docs/PLATFORMS.md](docs/PLATFORMS.md) — platform support, paths and secret backends
- [docs/PRIVACY.md](docs/PRIVACY.md) — what stays local and what a cloud job sends
- [docs/RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md) — pre-release automated + manual checks

## Contributing

Issues and pull requests are welcome — see
[CONTRIBUTING.md](CONTRIBUTING.md), the
[code of conduct](CODE_OF_CONDUCT.md) and [SECURITY.md](SECURITY.md) for how to
report a security problem privately.

## Build a Windows release

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1 -Clean -Zip -Installer
```

This produces `release\AfterClip\AfterClip.exe` (one-directory bundle),
`release\AfterClip-<version>-win64.zip` and, with `-Installer` and Inno Setup 6
installed, `release\AfterClip-<version>-setup.exe`. The application version
lives in `src/app/version.py` and is the single source of truth for package
metadata and the executable version resource. See
[docs/PACKAGING.md](docs/PACKAGING.md) for the full build, clean-machine smoke
test and current release gaps.

Tagged releases are built automatically by GitHub Actions.

## License

[MIT](LICENSE) © 2026 AfterClip contributors.
