# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the AfterClip Windows desktop build.

Build from the repository root (a one-directory bundle is produced at
``release/AfterClip/``)::

    python -m PyInstaller packaging/AfterClip.spec --noconfirm --clean ^
        --distpath release --workpath build/pyinstaller

A one-directory layout is deliberate: Qt plugins and QML modules stay on
disk (faster cold start) and the executable is less likely to trip antivirus
heuristics than a self-extracting one-file build.

The version resource is generated from ``app.version.__version__`` at build
time, so the executable metadata can never drift from the package version.
"""

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).resolve().parent
SRC = ROOT / "src"
APP = SRC / "app"

sys.path.insert(0, str(SRC))
from app.version import __version__  # noqa: E402  (spec-time single source of truth)

# Application QML sources plus the PySide6 QML modules/translations the engine
# resolves at runtime (the PySide6 hooks handle Qt shared libraries/plugins).
datas = [(str(APP / "ui" / "qml"), "app/ui/qml")]
datas += collect_data_files("PySide6", includes=["qml/**/*", "translations/**/*"])

# keyring discovers its backend dynamically, so PyInstaller cannot see it.
hiddenimports = [
    "keyring.backends.Windows",
    "keyring.backends.SecretService",
    "keyring.backends.kwallet",
]


def _version_resource(version: str) -> str:
    numbers = [int(part) for part in (version.split(".") + ["0", "0", "0", "0"])[:4]]
    quad = ", ".join(str(number) for number in numbers)
    return f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({quad}),
    prodvers=({quad}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0),
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', 'AfterClip'),
         StringStruct('FileDescription', 'AfterClip local media transcription'),
         StringStruct('FileVersion', '{version}'),
         StringStruct('InternalName', 'AfterClip'),
         StringStruct('OriginalFilename', 'AfterClip.exe'),
         StringStruct('ProductName', 'AfterClip'),
         StringStruct('ProductVersion', '{version}')],
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])]),
  ],
)
"""


build_dir = ROOT / "build" / "pyinstaller"
os.makedirs(build_dir, exist_ok=True)
version_file = build_dir / "version_info.txt"
version_file.write_text(_version_resource(__version__), encoding="utf-8")

icon_path = ROOT / "packaging" / "afterclip.ico"

a = Analysis(
    [str(ROOT / "packaging" / "entry_point.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest", "_pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AfterClip",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_path) if icon_path.is_file() else None,
    version=str(version_file),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="AfterClip",
)
