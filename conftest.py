"""Repository-wide pytest configuration.

The tests under ``tests/ui`` import PySide6, which links against Qt's system
libraries (``libEGL`` and friends on Linux). Those are not present on every
machine, and pytest imports test modules *during collection* -- before the
``-m 'not ui'`` deselection can filter them out. So on a machine without the
Qt libraries, collecting ``tests/ui`` fails the whole run with an ImportError
instead of merely skipping the UI tests.

Two things happen here:

* ``tests/ui`` is not collected at all unless the ``ui`` marker is explicitly
  selected, so the default ``pytest`` run needs no Qt libraries.
* When the UI tests *are* requested but PySide6 cannot be imported, the
  directory is skipped with a clear explanation instead of a traceback.
"""

import re
from pathlib import Path

UI_TESTS_DIR = Path(__file__).parent / "tests" / "ui"

#: Matches the ``ui`` marker as a whole word in a marker expression.
_UI_MARKER = re.compile(r"\bui\b")


def _ui_marker_selected(config) -> bool:
    """True when the ``-m`` expression selects tests marked ``ui``.

    The default expression is ``not ui``, which excludes them. Any positive
    branch that mentions the marker selects them, so ``-m ui`` and
    ``-m 'ui or slow'`` both count while ``-m 'not ui or slow'`` does not.
    """
    expression = (config.getoption("markexpr") or "").strip().lower()
    for branch in expression.split("or"):
        branch = branch.strip()
        if branch.startswith("not "):
            continue
        if _UI_MARKER.search(branch):
            return True
    return False


def pytest_ignore_collect(collection_path, config):
    """Skip the UI tests unless they were asked for, and Qt is usable."""
    if Path(collection_path) != UI_TESTS_DIR:
        return None
    if not _ui_marker_selected(config):
        return True
    try:
        import PySide6.QtWidgets  # noqa: F401
    except ImportError as error:
        config.issue_config_time_warning(
            "The UI tests were requested but PySide6 could not be imported "
            f"({error}). Install the Qt system libraries -- on Debian/Ubuntu: "
            "libegl1 libgl1 libxkbcommon-x11-0 libdbus-1-3 libfontconfig1 -- "
            "or run without '-m ui'."
        )
        return True
    return None
