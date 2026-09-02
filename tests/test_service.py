from pathlib import Path
import sys

import pytest

from app.application.service import TranscriptionService, next_available_job_dir
from app.domain.models import TranscriptionRequest, TranscriptionResult
from app.infrastructure.process import ProcessRunner


class Token:
    def __init__(self, cancelled=False):
        self.cancelled = cancelled

    def is_cancelled(self):
        return self.cancelled


class FakeMedia:
    def prepare_audio(self, input_path, work_dir, cancel_token):
        return input_path


class FakeProvider:
    def transcribe(self, request, on_progress, cancel_token):
        output = request.output_dir / "sample.srt"
        output.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
        return TranscriptionResult(request.output_dir, (output,))


def test_service_creates_transcript_output(tmp_path: Path):
    source = tmp_path / "sample.wav"
    source.write_bytes(b"fixture")
    result = TranscriptionService(FakeProvider(), FakeMedia()).run(
        TranscriptionRequest(source, tmp_path / "out"), lambda _: None, Token()
    )
    assert result.transcript_files[0].read_text(encoding="utf-8").endswith("Hello\n")
    assert result.output_dir == tmp_path / "out" / "sample" / "Transcripts"
    assert not (tmp_path / "out" / "sample" / "temp").exists()
    assert "Succeeded" in (tmp_path / "out" / "sample" / "Summary_Report.md").read_text(encoding="utf-8")


def test_service_rejects_missing_input(tmp_path: Path):
    with pytest.raises(ValueError, match="not found"):
        TranscriptionService(FakeProvider(), FakeMedia()).run(
            TranscriptionRequest(tmp_path / "missing.wav", tmp_path / "out"), lambda _: None, Token()
        )


def test_missing_external_program_has_actionable_error():
    with pytest.raises(RuntimeError, match="Required program was not found"):
        ProcessRunner().run(["program-that-does-not-exist"], Token())


def test_next_available_job_dir_increments_without_overwriting(tmp_path: Path):
    (tmp_path / "example").mkdir()
    (tmp_path / "example1").mkdir()
    assert next_available_job_dir(tmp_path, "example") == tmp_path / "example2"


def test_process_runner_drains_large_child_output():
    result = ProcessRunner().run(
        [sys.executable, "-c", "import sys; sys.stdout.write('x'*100000); sys.stderr.write('y'*100000)"],
        Token(),
    )
    assert result.returncode == 0
    assert len(result.stdout) == 100000
    assert len(result.stderr) == 100000
