import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _make_job(tmp_path: Path, name: str = "job1", status: str = "Succeeded") -> Path:
    job = tmp_path / "Output-Folder" / name
    job.mkdir(parents=True)
    (job / "job_state.json").write_text(
        json.dumps(
            {
                "status": status,
                "current_step": None,
                "steps": {"transcription": {"status": "completed", "duration_seconds": 1.5}},
            }
        ),
        encoding="utf-8",
    )
    (job / "Summary_Report.md").write_text("# Report\n", encoding="utf-8")
    return job


def test_mcp_server_import_is_qt_and_sdk_free():
    src = ROOT / "src"
    env = {**os.environ, "PYTHONPATH": str(src)}
    code = (
        "import sys; import app.mcp_server; "
        "bad = [m for m in sys.modules if m.startswith('PySide6') or m == 'mcp']; "
        "assert not bad, bad"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_tool_specs_cover_expected_tools():
    from app.mcp_server import tool_specs

    names = [spec["name"] for spec in tool_specs()]
    assert names == [
        "transcribe_media",
        "get_job_status",
        "list_jobs",
        "read_report",
        "list_presets",
    ]


def test_ensure_allowed_scopes_to_workspace(monkeypatch, tmp_path):
    monkeypatch.setenv("AFTERCLIP_HOME", str(tmp_path))
    from app.mcp_server import ensure_allowed

    inside = tmp_path / "Output-Folder" / "job1"
    assert ensure_allowed(inside) == inside.resolve()
    with pytest.raises(PermissionError):
        ensure_allowed(tmp_path.parent / "elsewhere")


def test_mcp_read_tools(monkeypatch, tmp_path):
    monkeypatch.setenv("AFTERCLIP_HOME", str(tmp_path))
    from app.mcp_server import get_job_status, list_jobs, read_report

    job = _make_job(tmp_path)
    jobs = list_jobs(str(tmp_path / "Output-Folder"))
    assert jobs[0]["name"] == "job1"
    assert jobs[0]["status"] == "Succeeded"

    status = get_job_status(str(job))
    assert status["status"] == "Succeeded"
    assert status["steps"]["transcription"]["status"] == "completed"

    assert "Report" in read_report(str(job))


def test_read_report_rejects_unknown_name(monkeypatch, tmp_path):
    monkeypatch.setenv("AFTERCLIP_HOME", str(tmp_path))
    from app.mcp_server import read_report

    job = _make_job(tmp_path)
    with pytest.raises(PermissionError):
        read_report(str(job), "secrets.txt")


def test_read_report_rejects_path_outside_workspace(monkeypatch, tmp_path):
    monkeypatch.setenv("AFTERCLIP_HOME", str(tmp_path))
    from app.mcp_server import read_report

    with pytest.raises(PermissionError):
        read_report(str(tmp_path.parent), "Summary_Report.md")


def test_list_presets(monkeypatch):
    import app.mcp_server as mcp
    from app.domain.presets import Preset
    from app.infrastructure.presets import InMemoryPresetStore

    monkeypatch.setattr(
        mcp, "JsonPresetStore", lambda: InMemoryPresetStore([Preset("m", whisper_model="base")])
    )
    presets = mcp.list_presets()
    assert presets[0]["name"] == "m"
    assert presets[0]["whisper_model"] == "base"
