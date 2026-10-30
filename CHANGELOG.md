# Changelog

All notable changes to AfterClip are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.0] — 2026-10-30

Phase 1 preset/prompt semantics plus the report-quality and vision-repair work.
Verified against eleven real jobs.

### Changed

- Report language is a separate per-job selection in the job settings, with a
  matching default in Settings. When no language is selected the report is
  **English**; the Whisper-detected and transcription languages no longer
  affect summaries, highlights, vision text or topics. Every AI output follows
  the selection, and summaries/highlights are rewritten once if the model
  answers in another language.
- The Ollama generation cap is raised from 1200 to 4096 tokens so long
  slide-by-slide summaries are no longer cut mid-sentence.
- The CLI can target one exact job with `--resume-dir` (alias `--job-dir`).
  The MCP server gains `fix_job`, detached `start_fix_job` and
  `get_fix_status`, so a long vision/text repair is not tied to one MCP tool
  call; `read_report` also exposes `Topics.md` and `Topics.json`. The optional
  MCP dependency is pinned to `mcp>=1.0,<2` because 2.x renamed `FastMCP`.

### Fixed

- Chatty AI replies no longer leak into the report. Summary cleaning now drops
  a whole leading block that talks about the prompt/user (for example
  "Harika bir sunum metni vermişsiniz…" followed by `---`), not just a single
  acknowledgement paragraph. The HTML report also cleans a cached summary.
- The HTML report no longer folds the `## Topics` list into **Key Highlights**.
  Section extraction uses the report's own headings, so summary headings inside
  the text survive, and highlights stop where `## Topics` begins.
- Topic titles follow the report language even when the model copies each
  section's language. A deterministic language guard detects a wrong-language
  title, rewrites the affected titles in one batch, then retries them
  individually. With no report language selected, reports default to English.
- Vision analysis no longer keeps an all-`[none]` answer. When a custom
  `vision_frame` template does not fit a frame (for example a slide-only prompt
  on a browser screen), the frame is retried once with the built-in
  content-agnostic prompt; frames the model explicitly marks `BLANK: true` are
  stored as `(no visible screen content)` without a retry. The built-in
  `vision_frame` prompt now describes slides, browser/app pages and meeting
  windows, and records retry/blank counts in `vision_filter_report.json`.
- One unreadable vision frame no longer discards the descriptions of every
  other frame: the failed frame is stored as blank and the step continues. The
  step still reports failure when every frame fails. Image requests never use
  the text-only Ollama CLI fallback, and the HTTP transport now enforces a
  wall-clock deadline because urllib's socket timeout can stop firing after a
  stalled response.
- Resumed jobs re-run text analysis once after this change (report writer
  version is part of the cached analysis fingerprint) instead of reusing a
  report that still carries the old preamble.
- The CLI can now reuse a finished transcription: `--reuse-transcription`
  (`--reuse`) resolves the latest completed job for the same input and skips
  Whisper. Speaker labels are restored from `Voiceprints.json` without
  re-reading the audio, so a resumed report keeps its speakers.
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
