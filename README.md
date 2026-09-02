# AfterClip

Windows-first desktop application for local media transcription. This repository is the new modular implementation; the legacy `whisper_gui2.py` remains outside it.

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

Run unit tests with `pytest`.
