"""Job history scan and log tail access for the UI panels."""
import json
import logging
from dataclasses import dataclass
from pathlib import Path

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class JobHistoryEntry:
    name: str
    path: Path
    status: str
    updated: str
    input_path: str


def scan_job_history(output_dir: Path) -> list[JobHistoryEntry]:
    """Job folders under the output root, newest first."""
    entries = []
    for state_path in sorted(output_dir.glob("*/job_state.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            LOGGER.info("Skipping unreadable job state %s: %s", state_path, error)
            continue
        entries.append(
            JobHistoryEntry(
                name=state_path.parent.name,
                path=state_path.parent,
                status=state.get("status", "unknown"),
                updated=state.get("updated", ""),
                input_path=state.get("input_path", ""),
            )
        )
    return entries


def read_log_tail(log_path: Path, lines: int = 400) -> str:
    try:
        content = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "(log file not found)"
    return "\n".join(content[-lines:])
