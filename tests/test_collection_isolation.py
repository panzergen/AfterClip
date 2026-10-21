"""The default test collection must not pull in Qt's GUI libraries.

On Linux the Qt GUI modules (``QtGui``, ``QtWidgets``, ``QtQml``, ``QtQuick``,
``QtMultimedia``) link against ``libEGL``, which is not installed on a bare
CI runner or on many Linux desktops. The UI tests are excluded from the
default collection by the repository ``conftest.py``, so collecting the
default suite must never import those modules -- otherwise a plain ``pytest``
run fails at collection time on Linux instead of merely skipping the UI
tests.

This is a regression guard: if somebody adds a Qt GUI import to a module
that the unit suite imports, this test fails.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Qt modules that pull in the platform's OpenGL/graphics libraries.
GUI_MODULES = (
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickControls2",
    "PySide6.QtMultimedia",
)


def _collected_modules(*pytest_args: str) -> set[str]:
    """Collect the given pytest selection in a subprocess and report imports."""
    code = (
        "import sys, pytest\n"
        "pytest.main(list(sys.argv[1:]))\n"
        f"print('LOADED:' + ','.join(m for m in {GUI_MODULES!r} if m in sys.modules))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, *pytest_args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"collection failed:\n{result.stdout}\n{result.stderr}"
    for line in result.stdout.splitlines():
        if line.startswith("LOADED:"):
            return {name for name in line[len("LOADED:") :].split(",") if name}
    raise AssertionError(f"could not read the import report:\n{result.stdout}")


def test_default_collection_does_not_import_qt_gui_modules():
    """A plain `pytest` run must not need the Qt system libraries."""
    assert _collected_modules("-q", "--collect-only") == set()


def test_ui_marker_selection_does_collect_the_ui_tests():
    """`-m ui` must still collect the UI tests (which do need Qt)."""
    code = (
        "import pytest, sys\n"
        "pytest.main(['-q', '--collect-only', '-m', 'ui'])\n"
        "print('COUNT:' + str(len([m for m in sys.modules if m.startswith('app.ui')])))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"collection failed:\n{result.stdout}\n{result.stderr}"
    assert "COUNT:0" not in result.stdout, "the UI tests were not collected"
