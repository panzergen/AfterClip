# Packaging AfterClip for Windows

This document describes the Phase 3 packaging spike: how to produce a
distributable Windows build from the repository, what gets bundled, and what
still has to be installed on the target machine.

## Prerequisites

- Windows 10/11 (x64)
- Python 3.12+ with `pip` (the build script uses whichever `python` is active)
- Network access for the first dependency install

FFmpeg/FFprobe and `openai-whisper` are **not** bundled. They are external
tools the application discovers on `PATH` (see `Where things are stored` in the
main README). Distribution of those binaries is tracked separately because of
licensing, CUDA/PyTorch size and antivirus considerations.

## Build

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1 -Clean -Zip
```

The script:

1. installs the project with the `build` extra (`pip install ".[build]"`),
2. runs `python -m PyInstaller packaging/AfterClip.spec`,
3. writes the executable to `release\AfterClip\AfterClip.exe`,
4. with `-Zip`, also emits `release\AfterClip-<version>-win64.zip`.

Manual equivalent:

```powershell
python -m pip install ".[build]"
python -m PyInstaller packaging\AfterClip.spec --noconfirm --clean `
    --distpath release --workpath build\pyinstaller
```

## Output layout

A one-directory bundle (`--onedir`) is produced on purpose: Qt plugins and QML
modules stay on disk, cold start is faster, and the executable is less likely to
trip antivirus heuristics than a self-extracting one-file build.

```
release/
└── AfterClip/
    ├── AfterClip.exe          # windowed (no console) launcher
    ├── _internal/             # Python runtime, Qt libs, plugins, QML modules
    └── ...
```

## Versioning

`src/app/version.py` is the single source of truth. `pyproject.toml` reads it
through a setuptools dynamic `attr`, and `packaging/AfterClip.spec` generates
the Windows version resource from it at build time. To release a new version,
edit `__version__` in `src/app/version.py` only; a test
(`tests/test_packaging.py`) guards the wiring.

## Runtime paths when frozen

A packaged build has no repository beside it, so `app/app_paths.py` switches
behaviour when `sys.frozen` is set:

| Path | Source run | Frozen build |
| --- | --- | --- |
| QML sources | `src/app/ui/qml` | `<bundle>/app/ui/qml` |
| Workspace (Input/Output folders) | repository or `AFTERCLIP_HOME` | `%USERPROFILE%\AfterClip` (or `AFTERCLIP_HOME`) |
| Settings / logs | `%LOCALAPPDATA%\AfterClip` | `%LOCALAPPDATA%\AfterClip` |

`AFTERCLIP_HOME` overrides the workspace in both modes.

## Clean-machine smoke test

1. Copy `release\AfterClip\` (or unzip the archive) to a machine without the
   dev environment.
2. Install FFmpeg/FFprobe and `openai-whisper` per the main README.
3. Launch `AfterClip.exe`; confirm the window opens and the environment LEDs
   report the tools.
4. Process a small media file end to end and confirm outputs land in
   `%USERPROFILE%\AfterClip\Output-Folder`.
5. Confirm `%LOCALAPPDATA%\AfterClip\logs\app.log` is created and contains no
   secret material.

See `TEST_SCENARIOS.md` (T29, T30) for the release smoke expectations.

## Known gaps / next steps

- **Code signing**: unsigned executables trigger SmartScreen/antivirus
  warnings. An EV/OV certificate and `signtool` are required for a public
  release.
- **Icon**: drop `packaging/afterclip.ico` and the spec picks it up
  automatically; none is committed yet.
- **Installer**: an Inno Setup (or MSIX) script is still required to produce a
  real installer with Start Menu/Uninstall entries.
- **Bundling FFmpeg/Whisper**: still unresolved (size, CUDA, licensing).
- **Python 3.14**: verify the chosen PyInstaller version supports it; pin/test
  the interpreter version used for the release build.
- **Qt QML modules**: if the frozen app fails to load a QML module, add
  `collect_all("PySide6")` in the spec (larger bundle) or extend the
  `collect_data_files` includes.
