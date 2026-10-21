# Changelog

All notable changes to AfterClip are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Work that has landed on `main` since the last tagged release.

### Fixed

- Concurrent writers no longer collide on report and state files. The atomic
  write helper now uses a unique temporary file name per call and retries a
  briefly-refused replace, which removes intermittent `PermissionError`
  failures on Windows (`app/infrastructure/atomic_file.py`).
- Batch jobs now run voiceprints. The batch worker previously built its
  transcription service without the voiceprint store and embedder, so the
  per-job `voiceprint_enabled` flag was silently ignored.
- The default test run no longer needs Qt's GUI libraries. `tests/ui` was
  imported during collection even though the `ui` marker deselected it
  afterwards, so on Linux — where `QtGui` links against `libEGL` — a plain
  `pytest` run failed at collection with an `ImportError`. The directory is
  now excluded from collection unless `-m ui` is given, and CI installs the
  Qt system libraries for the UI job.

## [0.3.0] — 2026-10-20

The first public release. Earlier work existed on private branches only.

### Added

**Transcription and media**

- Whisper transcription through a background worker, with cancellation of the
  active job and resume of completed steps.
- FFmpeg WAV preparation and clip-range processing.
- Interval and scene-change frame extraction at full, 1024px and 768px
  resolution, with a preview cache and frame navigation.
- Microphone recording to the selected output directory, with system-audio
  capture where FFmpeg supports WASAPI.
- Speaker VTT parsing with graceful fallback when the file is missing or
  malformed.
- Transcript segments merged into readable paragraphs (30s default, with
  speaker-aware breaks) and a Whisper hallucination sanitizer.

**Reports**

- `Master_Timeline.md` — a lean Markdown timeline for AI consumption.
- `FullReportAndTimeline.htm` — a human-readable report with summary,
  highlights, the full transcript and embedded frames.
- Multimodal JSONL output with speaker badges.
- Topic segmentation into per-topic report sections, with AI-generated topic
  titles and a cohesion fallback.
- Media-type classification with per-type suggestions.

**AI providers**

- A single provider registry driving **Ollama** (local), **Gemini**,
  **OpenRouter**, **OpenCode Go** and **OpenCode Zen**, all behind one
  OpenAI-compatible adapter plus a dedicated Gemini adapter.
- Optional AI text analysis (summary and timestamped highlights) and AI vision
  analysis (frame descriptions) behind `TextAnalysisProvider` and
  `VisionProvider` ports.
- Provider-grouped model dropdowns with live model lists and capability
  filtering — the vision dropdown only offers image-capable models.
- Explicit, revocable cloud consent: a pre-job confirmation names the
  provider and model and what leaves the machine, blocks the job until
  accepted, and warns about API charges.
- Per-job cloud usage (requests, tokens, images) and an approximate cost
  estimate, recorded in `job_state.json` and in the report.
- Separate transcription language and report language.
- A transcript hallucination filter and an optional AI cleanup prompt template.
- Pre-start time estimates from past jobs, with a self-correction factor.

**Interface**

- PySide6 Qt Quick (QML) two-column, Windows-first interface. All UI state
  lives in testable Python controllers exposed to the QML views as context
  properties.
- Native `QMediaPlayer` playback inside the QML scene, with a shared
  `QVideoSink` and a WMF/FFmpeg-safe source-switch guard.
- Media, Record, Batch and History tabs; job history and an in-app log tail.
- Keyboard shortcuts and accessibility support.
- An optional completion sound (on by default) that plays when a job finishes
  or fails.

**Advanced**

- Local voiceprints (optional `voiceprint` extra): identify speakers by voice
  and cluster unknowns into `Speaker N`, complementing the speaker VTT without
  overriding it.
- Editable prompt templates and named job presets.

**Packaging and automation**

- A headless CLI with `run`, `batch` and `status` subcommands, and an MCP
  stdio server.
- A one-directory Windows bundle via PyInstaller, an optional zip and an
  Inno Setup installer.
- Per-user data directories on Windows, macOS and Linux, with a
  schema-versioned, automatically migrated settings file.
- API keys in the OS credential manager via `keyring`, redacted from logs.
- Disk, GPU and external-tool diagnostics, and an output preflight check.

[Unreleased]: https://github.com/panzergen/AfterClip/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/panzergen/AfterClip/releases/tag/v0.3.0
