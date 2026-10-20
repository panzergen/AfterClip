# Release Checklist

Run through this before sharing a build. Automated tests come first; the manual
steps cover what unit tests cannot (packaged UI, external tools, hardware).

## Automated

```powershell
python -m pytest -q
$env:QT_QPA_PLATFORM="offscreen"; python -m pytest -m ui -q
python -m ruff check src tests packaging
python -m ruff format --check src tests packaging
```

Expected: all pass. UI tests need `QT_QPA_PLATFORM=offscreen`. The two ruff
commands are the same ones CI runs, so a green local run means a green CI run.
`ruff` is part of the `dev` extra (`pip install -e ".[dev]"`).

## Build

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1 -Clean -Zip
```

- Confirm `release\AfterClip\AfterClip.exe` exists and version metadata matches
  `src/app/version.py` (right-click → Properties → Details).
- Confirm the zip `release\AfterClip-<version>-win64.zip` is produced.

## Clean-machine smoke test (T29)

1. Copy the bundle (or zip) to a machine without the dev environment.
2. Install FFmpeg/FFprobe and `openai-whisper`; ensure they are on `PATH`.
3. Launch `AfterClip.exe` — the window opens; the status tooltip lists
   FFmpeg/FFprobe/Whisper, GPU and disk.
4. Process a small media file end to end; outputs land in the workspace
   (`%USERPROFILE%\AfterClip` by default) and open correctly.
5. Confirm `<data dir>\logs\app.log` exists and contains no secret material.

## Feature checks

- **High DPI / dark mode (T30)** — layout and text stay readable.
- **Cancel (T07)** — `Ctrl+.` stops a running job; state shows `cancelled`.
- **Resume (T26)** — re-running an interrupted file reuses completed steps.
- **Batch (T08b/T26b)** — multiple files queue, run in order, and survive a
  restart (pending jobs reload).
- **Cloud consent** — the first cloud job prompts for the selected provider;
  revoking consent in Settings re-prompts; no API key → no cloud request.
- **Usage/cost** — `Summary_Report.md` shows the Cloud Usage section after a
  cloud job.
- **Shortcuts** — `Ctrl+O`, `Ctrl+Enter`, `Ctrl+.`, `Ctrl+1..4`, `Ctrl+,`.

## Sign-off

- [ ] Automated suites green
- [ ] Build produced with correct version
- [ ] Clean-machine smoke test passed
- [ ] Feature checks passed
- [ ] `docs/` updated for any behaviour change
