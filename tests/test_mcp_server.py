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
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_tool_specs_cover_expected_tools():
    from app.mcp_server import tool_specs

    names = [spec["name"] for spec in tool_specs()]
    assert names == [
        "transcribe_media",
        "fix_job",
        "start_fix_job",
        "get_fix_status",
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


def test_fix_job_reuses_the_existing_job(monkeypatch, tmp_path):
    monkeypatch.setenv("AFTERCLIP_HOME", str(tmp_path))
    import app.mcp_server as mcp
    from app.domain.models import TranscriptionResult

    job = _make_job(tmp_path, "job1")
    source = tmp_path / "Input-Folder" / "meeting.mp4"
    source.parent.mkdir()
    source.write_bytes(b"fixture")
    state = json.loads((job / "job_state.json").read_text(encoding="utf-8"))
    state["input_path"] = str(source)
    state["run_settings"] = {"model": "turbo"}
    (job / "job_state.json").write_text(json.dumps(state), encoding="utf-8")

    captured = {}

    def fake_run(
        request,
        text_provider,
        vision_provider,
        sanitizer,
        on_event=None,
        cancel_token=None,
        **kwargs,
    ):
        captured["resume_dir"] = kwargs.get("resume_dir")
        captured["request"] = request
        return TranscriptionResult(job / "Transcripts", ())

    monkeypatch.setattr(mcp, "run_request", fake_run)
    result = mcp.fix_job(
        str(job), report_language="tr", analyze_text=False, analyze_vision=False
    )
    assert result["status"] == "succeeded"
    assert captured["resume_dir"] == job
    assert captured["request"].output_language == "tr"


def test_start_fix_job_spawns_detached_cli(monkeypatch, tmp_path):
    monkeypatch.setenv("AFTERCLIP_HOME", str(tmp_path))
    import app.mcp_server as mcp

    job = _make_job(tmp_path, "job1")
    source = tmp_path / "Input-Folder" / "meeting.mp4"
    source.parent.mkdir()
    source.write_bytes(b"fixture")
    state = json.loads((job / "job_state.json").read_text(encoding="utf-8"))
    state["input_path"] = str(source)
    (job / "job_state.json").write_text(json.dumps(state), encoding="utf-8")

    captured = {}

    class FakeProcess:
        pid = 4321

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(mcp.subprocess, "Popen", fake_popen)
    result = mcp.start_fix_job(
        str(job),
        report_language="en",
        provider="ollama",
        text_model="text-model",
        vision_model="vision-model",
        analyze_vision=True,
    )
    assert result["status"] == "started"
    assert result["pid"] == 4321
    command = captured["command"]
    assert "--resume-dir" in command and str(job) in command
    assert "--report-language" in command and "en" in command
    assert "--analyze-vision" in command
    assert "--vision-model" in command and "vision-model" in command
    assert captured["kwargs"]["stdin"] == subprocess.DEVNULL
    assert (job / "fix_task.json").is_file()

    status = mcp.get_fix_status(str(job))
    assert status["task"]["pid"] == 4321
    assert status["status"] == "Succeeded"


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
