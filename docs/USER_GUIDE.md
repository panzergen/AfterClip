# AfterClip User Guide

AfterClip transcribes media locally with Whisper and optionally builds a
report, timeline and AI analysis. It is Windows-first; macOS/Linux run from
source (see `PLATFORMS.md`).

## Install (from source)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pip install openai-whisper
```

Install **FFmpeg/FFprobe** and make sure `ffmpeg`, `ffprobe` and `whisper` are
on `PATH`. Start the app with `afterclip` or by double-clicking
`run_afterclip.bat`.

## First run

1. Pick a media file with **Browse** (or drag one onto the window).
2. Choose an **Output directory**.
3. Press **Start Processing**.

The status LED (bottom-right) turns green only when FFmpeg, FFprobe, Whisper
and Ollama are all available; hover it to see the exact tool, GPU and free-disk
status.

## Tabs

- **Media** — preview frames, playback, clip start/end, bookmark highlights.
- **Record** — record from a microphone (and system audio on Windows when
  WASAPI is available) straight into the output directory.
- **Batch** — queue several files; they run sequentially with per-job status,
  retry and cancel.
- **History** — past jobs from the output directory plus the app log.

## Transcription settings

- **Language** is the spoken language hint for Whisper (empty = auto-detect).
- **Report language** controls summaries/highlights/vision text, independent of
  the spoken language (empty = Whisper-detected video language).
- **Segment length** merges raw Whisper segments into readable paragraphs
  (Whisper default / 15s / 30s / 60s).

## AI analysis (optional)

- **Ollama (local)** — summaries, highlights and frame descriptions; nothing
  leaves the machine.
- **Cloud providers** — **Gemini**, **OpenRouter**, **OpenCode Go** and
  **OpenCode Zen** offer the same features over their own APIs. The first cloud
  job shows a consent dialog naming the provider/model and what is uploaded;
  accept it to proceed. Grant or revoke consent any time in Settings. Video is
  **never** uploaded — only transcript text and single frames.

Pick the provider in the job form, then set its key and model list in
**Settings → Cloud provider**. See `PROVIDERS.md` for the endpoints and
credential names.

## Outputs

Each job writes a folder under the output directory:

```
<name>/
├── Summary_Report.md          # metadata, steps, status, cloud usage
├── Master_Timeline.md         # speaker-aware timeline for reading/AI
├── multimodal_timeline.jsonl  # machine-readable timeline (text + vision)
├── FullReportAndTimeline.htm  # human-readable report with embedded frames
├── AI_Analysis.md             # summary + highlights (when AI runs)
├── job_state.json             # checkpoint state (enables resume)
├── Transcripts/               # Whisper output: .srt, .txt, .json, .vtt
└── Vision/
    ├── vision_analysis.srt    # per-frame AI descriptions
    ├── timeline_frames.srt    # every extracted frame
    └── frames/*.png
```

Interrupted jobs resume: re-running the same file reuses completed steps.
Transcription and extracted frames are reused as-is; AI text/vision analysis
re-runs automatically when the prompts or report language changed since, so
edited prompts always take effect on a resumed job.

## Keyboard shortcuts

| Shortcut | Action |
| --- | --- |
| `Ctrl+O` | Browse for a media file |
| `Ctrl+Enter` | Start processing |
| `Ctrl+.` | Cancel the running job |
| `Ctrl+1`..`Ctrl+4` | Media / Record / Batch / History |
| `Ctrl+,` | Settings |

## Where your data lives

See `PLATFORMS.md`. Settings and logs are under the per-user data directory;
API keys live in the OS credential manager, never on disk in plaintext.
