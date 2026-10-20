import os
import sys
from pathlib import Path

from app.version import APP_NAME


def is_frozen() -> bool:
    """True when running from a PyInstaller (``--onedir``/``--onefile``) bundle."""
    return bool(getattr(sys, "frozen", False))


def repository_dir() -> Path:
    """Directory of the AfterClip source repository (contains pyproject.toml)."""
    return Path(__file__).resolve().parents[2]


def bundle_dir() -> Path:
    """Root of the extracted PyInstaller bundle, or the repository for source runs."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return repository_dir()


def package_dir() -> Path:
    """Directory of the ``app`` package (holds the ``ui/qml`` data files).

    In a frozen build the QML sources are copied to ``<bundle>/app/ui/qml`` by
    the PyInstaller spec, so this resolves the same relative layout in both
    source and packaged runs.
    """
    if is_frozen():
        return bundle_dir() / "app"
    return Path(__file__).resolve().parent


def app_data_dir() -> Path:
    """Per-user writable directory for settings, logs and caches.

    Follows each platform's convention so a macOS/Linux build writes where
    users (and backup tools) expect it, while Windows keeps the existing
    ``%LOCALAPPDATA%\\AfterClip`` location.
    """
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Local"
        return root / APP_NAME
    xdg = os.environ.get("XDG_DATA_HOME")
    root = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return root / APP_NAME


def default_workspace_dir() -> Path:
    """Workspace holding Input-Folder/Output-Folder for installed builds.

    A frozen build has no repository beside it, so a per-user folder keeps the
    Input/Output folders discoverable and writable without admin rights.
    """
    return Path.home() / APP_NAME


def project_dir() -> Path:
    """Workspace root holding Input-Folder / Output-Folder.

    Honours the AFTERCLIP_HOME environment variable so tests and relocated
    installations can point the application at a different workspace. Frozen
    builds default to the per-user workspace; source runs keep the existing
    repository/workspace heuristic.
    """
    override = os.environ.get("AFTERCLIP_HOME")
    if override:
        return Path(override).resolve()
    if is_frozen():
        return default_workspace_dir()
    repository = repository_dir()
    workspace_dir = repository.parent
    return workspace_dir if (workspace_dir / "Input-Folder").exists() else repository


def default_input_dir() -> Path:
    return project_dir() / "Input-Folder"


def default_output_dir() -> Path:
    return project_dir() / "Output-Folder"


def log_file() -> Path:
    """Per-user log location (%LOCALAPPDATA%/AfterClip/logs/app.log)."""
    return app_data_dir() / "logs" / "app.log"


def crash_file() -> Path:
    """Fatal-crash report written by faulthandler; bounds the log directory."""
    return app_data_dir() / "logs" / "crash.log"


def notification_sound_default() -> Path:
    """Bundled default completion sound (synthesized, public-domain-equivalent)."""
    return package_dir() / "ui" / "assets" / "complete.wav"
