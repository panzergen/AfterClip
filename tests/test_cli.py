import json
import os
import subprocess
import sys
from pathlib import Path

from app.cli import build_parser, build_request, main
from app.domain.presets import Preset

ROOT = Path(__file__).resolve().parents[1]


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "in.mp4"
    source.write_bytes(b"x")
    return source


def test_cli_import_is_qt_free():
    src = ROOT / "src"
    env = {**os.environ, "PYTHONPATH": str(src)}
    code = (
        "import sys; import app.cli; "
        "bad = [m for m in sys.modules if m.startswith('PySide6')]; "
        "assert not bad, bad"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_build_request_maps_flags(tmp_path):
    source = _source(tmp_path)
    out = tmp_path / "out"
    args = build_parser().parse_args(
        [
            "run", "--input", str(source), "--output", str(out),
            "--model", "small", "--language", "tr", "--report-language", "en",
            "--frames", "both", "--frame-interval", "20", "--frame-resolution", "mid",
            "--analyze-text", "--text-model", "glm-5.2", "--provider", "opencode_go",
            "--clip-start", "10", "--clip-end", "01:00", "--segment", "15",
        ]
    )
    request = build_request(args)
    assert request.model == "small"
    assert request.language == "tr"
    assert request.output_language == "en"
    assert request.frame_modes == ("interval", "scene")
    assert request.frame_interval == 20
    assert request.frame_resolution == "mid"
    assert request.analyze_text and request.analysis_model == "glm-5.2"
    assert request.clip_start == 10 and request.clip_end == 60
    assert request.transcript_merge_seconds == 15
    assert request.extract_frames is True


def test_build_request_uses_preset_defaults(tmp_path):
    source = _source(tmp_path)
    preset = Preset(
        name="meeting",
        whisper_model="base",
        language="en",
        interval_mode=True,
        scene_mode=False,
        frame_interval=12,
        frame_resolution_index=1,
        analysis_enabled=True,
        analysis_model_text="some-model",
    )
    args = build_parser().parse_args(
        ["run", "--input", str(source), "--output", str(tmp_path / "out")]
    )
    request = build_request(args, preset)
    assert request.model == "base"
    assert request.language == "en"
    assert request.frame_modes == ("interval",)
    assert request.frame_interval == 12
    assert request.frame_resolution == "mid"
    assert request.analyze_text and request.analysis_model == "some-model"


def test_build_request_topic_flags(tmp_path):
    source = _source(tmp_path)
    default_args = build_parser().parse_args(
        ["run", "--input", str(source), "--output", str(tmp_path / "out")]
    )
    assert build_request(default_args).topic_method == "cohesion"

    off_args = build_parser().parse_args(
        [
            "run", "--input", str(source), "--output", str(tmp_path / "out"),
            "--topics", "off", "--topic-min-seconds", "300", "--topic-max-sections", "5",
        ]
    )
    request = build_request(off_args)
    assert request.topic_method == "off"
    assert request.topic_min_seconds == 300
    assert request.topic_max_sections == 5


def test_cli_missing_input_returns_validation(tmp_path, capsys):
    code = main(
        [
            "run", "--input", str(tmp_path / "missing.mp4"),
            "--output", str(tmp_path / "out"), "--json",
        ]
    )
    assert code == 2
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["status"] == "error"
    assert "not found" in payload["error"]


def test_cli_cloud_provider_without_key_is_validation(tmp_path, capsys, monkeypatch):
    class NoKeyStore:
        def get(self, name):
            return None

        def set(self, name, value):
            pass

        def delete(self, name):
            pass

    monkeypatch.setattr("app.application.headless.KeyringSecretStore", NoKeyStore)
    source = _source(tmp_path)
    code = main(
        [
            "run", "--input", str(source), "--output", str(tmp_path / "out"),
            "--provider", "openrouter", "--analyze-text", "--text-model", "m", "--json",
        ]
    )
    assert code == 2
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert "API key" in payload["error"]


def test_cli_status_lists_jobs(tmp_path, capsys):
    job = tmp_path / "out" / "job1"
    job.mkdir(parents=True)
    (job / "job_state.json").write_text(
        json.dumps({"status": "Succeeded", "input_path": "x"}), encoding="utf-8"
    )
    code = main(["status", "--output", str(tmp_path / "out"), "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload[0]["name"] == "job1"
    assert payload[0]["status"] == "Succeeded"


def test_cli_no_command_prints_help(capsys):
    assert main([]) == 2
