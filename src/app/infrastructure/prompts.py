import json
import logging
from pathlib import Path

from app.app_paths import app_data_dir
from app.domain.prompts import TEMPLATE_NAMES, PromptSet, build_prompt_set
from app.infrastructure.atomic_file import atomic_write_text as _atomic_write_text

LOGGER = logging.getLogger(__name__)

PROMPTS_SCHEMA_VERSION = 1


class InMemoryPromptStore:
    """Dict-backed store for tests and callers without persistence."""

    def __init__(self, prompt_set: PromptSet | None = None):
        self._prompt_set = prompt_set or PromptSet()

    def load(self) -> PromptSet:
        return self._prompt_set

    def save(self, prompt_set: PromptSet) -> None:
        self._prompt_set = prompt_set


class JsonPromptStore:
    """JSON prompt persistence; defaults to %LOCALAPPDATA%/AfterClip/prompts.json.

    Only known template keys are honored; anything else in the file is ignored
    so a hand-edited or future-version file cannot break loading.
    """

    def __init__(self, path: Path | None = None):
        self.path = path or (app_data_dir() / "prompts.json")

    def load(self) -> PromptSet:
        raw = self._read()
        overrides = {
            key: value
            for key, value in raw.items()
            if key in TEMPLATE_NAMES and isinstance(value, str) and value
        }
        return build_prompt_set(overrides)

    def save(self, prompt_set: PromptSet) -> None:
        payload = {"version": PROMPTS_SCHEMA_VERSION, **prompt_set.to_dict()}
        _atomic_write_text(self.path, json.dumps(payload, ensure_ascii=False, indent=2))

    def _read(self) -> dict:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            LOGGER.debug("Prompt file not readable (%s): %s", self.path, error)
            return {}
        return payload if isinstance(payload, dict) else {}
