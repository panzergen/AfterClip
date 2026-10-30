"""Single source of truth for the AfterClip application version.

``pyproject.toml`` reads this value via a setuptools dynamic ``attr`` so the
package metadata, the Windows executable version resource and the version
shown at runtime can never drift apart.
"""

APP_NAME = "AfterClip"
__version__ = "0.4.0"


def version_string() -> str:
    """Human-readable version used in UI, logs and reports."""
    return __version__


def version_info_version() -> str:
    """The package version padded to a four-part Windows version resource.

    ``0.3.0`` → ``0.3.0.0``. Windows version resources (the PE ``FileVersion``
    structure and Inno Setup's ``VersionInfoVersion``) require exactly four
    numeric components; fewer leave Explorer's Details tab blank.
    """
    parts = __version__.split(".")
    return ".".join([*parts, "0", "0", "0", "0"][:4])
