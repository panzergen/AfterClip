"""Pure UI helpers shared by controllers (no Qt widgets)."""

from pathlib import Path

from PySide6.QtCore import QUrl

PLAYBACK_SPEEDS = (1.0, 1.2, 1.5)


def format_duration(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def next_playback_speed(current: float) -> float:
    speeds = PLAYBACK_SPEEDS
    return speeds[(speeds.index(current) + 1) % len(speeds)]


def parse_time_text(text: str) -> float:
    """Parse 'HH:MM:SS' (or partial 'MM:SS' / 'SS') into seconds; -1 when invalid."""
    parts = text.strip().split(":")
    if not 1 <= len(parts) <= 3 or not all(part.isdigit() for part in parts):
        return -1.0
    values = [int(part) for part in parts]
    while len(values) < 3:
        values.insert(0, 0)
    return float(values[0] * 3600 + values[1] * 60 + values[2])


def local_path(value) -> str:
    """Normalize a str / QUrl / Path into a local filesystem path.

    QML file dialogs hand out `url` values; converting those to a Python str
    through a typed slot crashes in this PySide6 build, so controllers accept
    QVariant and normalize here instead.
    """
    if isinstance(value, QUrl):
        return value.toLocalFile() or value.toString()
    text = str(value)
    if text.startswith("file:"):
        return QUrl(text).toLocalFile()
    return text


def local_paths(values) -> list[str]:
    return [local_path(value) for value in values]


def path_name(value) -> str:
    return Path(local_path(value)).name
