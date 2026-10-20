import json
import logging
from pathlib import Path

from app.app_paths import app_data_dir
from app.infrastructure.atomic_file import atomic_write_text as _atomic_write_text

LOGGER = logging.getLogger(__name__)

VOICEPRINTS_SCHEMA_VERSION = 1


class InMemoryVoiceprintStore:
    """Dict-backed store for tests and callers without persistence."""

    def __init__(self, voiceprints: dict[str, list[float]] | None = None):
        self._voiceprints = {
            name: list(embedding) for name, embedding in (voiceprints or {}).items()
        }

    def load(self) -> dict[str, list[float]]:
        return {name: list(embedding) for name, embedding in self._voiceprints.items()}

    def save(self, name: str, embedding: list[float]) -> None:
        self._voiceprints[name] = list(embedding)

    def remove(self, name: str) -> None:
        self._voiceprints.pop(name, None)


class JsonVoiceprintStore:
    """JSON voiceprint persistence; defaults to %LOCALAPPDATA%/AfterClip/voiceprints.json.

    Embeddings are plain float lists keyed by speaker name. Only well-formed
    ``name -> [float, …]`` entries are kept, so a hand-edited or future-version
    file cannot break loading.
    """

    def __init__(self, path: Path | None = None):
        self.path = path or (app_data_dir() / "voiceprints.json")

    def load(self) -> dict[str, list[float]]:
        raw = self._read()
        if isinstance(raw.get("voiceprints"), dict):
            raw = raw["voiceprints"]
        voiceprints: dict[str, list[float]] = {}
        for name, embedding in raw.items():
            if isinstance(name, str) and name and _is_float_list(embedding):
                voiceprints[name] = [float(value) for value in embedding]
        return voiceprints

    def save(self, name: str, embedding: list[float]) -> None:
        if not name or not _is_float_list(embedding):
            raise ValueError("A voiceprint needs a name and a non-empty float embedding.")
        data = self.load()
        data[name] = [float(value) for value in embedding]
        self._write(data)

    def remove(self, name: str) -> None:
        data = self.load()
        if name in data:
            del data[name]
            self._write(data)

    def _read(self) -> dict:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            LOGGER.debug("Voiceprint file not readable (%s): %s", self.path, error)
            return {}
        return payload if isinstance(payload, dict) else {}

    def _write(self, data: dict) -> None:
        payload = {"version": VOICEPRINTS_SCHEMA_VERSION, "voiceprints": data}
        _atomic_write_text(self.path, json.dumps(payload, ensure_ascii=False, indent=2))


def _is_float_list(value) -> bool:
    return (
        isinstance(value, (list, tuple))
        and bool(value)
        and all(isinstance(item, (int, float)) for item in value)
    )
