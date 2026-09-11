import os
from pathlib import Path


def repository_dir() -> Path:
    """Directory of the AfterClip source repository (contains pyproject.toml)."""
    return Path(__file__).resolve().parents[2]


def project_dir() -> Path:
    """Workspace root holding Input-Folder / Output-Folder.

    Honours the AFTERCLIP_HOME environment variable so tests and relocated
    installations can point the application at a different workspace.
    """
    override = os.environ.get("AFTERCLIP_HOME")
    if override:
        return Path(override).resolve()
    repository = repository_dir()
    workspace_dir = repository.parent
    return workspace_dir if (workspace_dir / "Input-Folder").exists() else repository


def default_input_dir() -> Path:
    return project_dir() / "Input-Folder"


def default_output_dir() -> Path:
    return project_dir() / "Output-Folder"


def log_file() -> Path:
    """Per-user log location (%LOCALAPPDATA%/AfterClip/logs/app.log)."""
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / "AppData" / "Local"
    return root / "AfterClip" / "logs" / "app.log"
