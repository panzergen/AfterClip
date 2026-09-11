"""Single source of truth for the AfterClip application version.

``pyproject.toml`` reads this value via a setuptools dynamic ``attr`` so the
package metadata, the Windows executable version resource and the version
shown at runtime can never drift apart.
"""

APP_NAME = "AfterClip"
__version__ = "0.3.0"


def version_string() -> str:
    """Human-readable version used in UI, logs and reports."""
    return __version__
