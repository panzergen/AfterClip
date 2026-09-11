import json
import sys
from pathlib import Path

import pytest

from app.application.service import TranscriptionService, next_available_job_dir, parse_clip_time
from app.domain.models import TranscriptionRequest, TranscriptionResult
from app.infrastructure.process import ProcessRunner
from app.infrastructure.recorder import AudioRecorder


class Token:
    def __init__(self, cancelled=False):
        self.cancelled = cancelled

    def is_cancelled(self):
        return self.cancelled


class FakeMedia:
    def prepare_audio(self, input_path, work_dir, cancel_token, clip_start=None, clip_end=None):
        return input_path

    def extract_interval_frames(
        self,
        input_path,
        frames_dir,
        interval,
        cancel_token,
        clip_start=None,
        clip_end=None,
        highlight_times=(),
        mode="interval",
        sensitivity=0.35,
        resolution="full",
    ):
        frames_dir.mkdir(parents=True, exist_ok=True)
        frame = frames_dir / "frame_000000.png"
        frame.write_bytes(b"frame")
        return (frame,)


class FakeProvider:
    def transcribe(self, request, on_progress, cancel_token):
        output = request.output_dir / "sample.srt"
        output.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
        text = request.output_dir / "sample.txt"
        text.write_text("Hello", encoding="utf-8")
        return TranscriptionResult(request.output_dir, (output, text))


class FakeTextProvider:
    def summarize(self, transcript, language, on_progress=None, cancel_token=None):
        return f"summary of {transcript} in {language}"

    def extract_highlights(self, srt_content, language, on_progress=None, cancel_token=None):
        return "- 00:00:01 highlight"


def test_service_creates_transcript_output(tmp_path: Path):
    source = tmp_path / "sample.wav"
    source.write_bytes(b"fixture")
    result = TranscriptionService(FakeProvider(), FakeMedia()).run(
        TranscriptionRequest(source, tmp_path / "out"), lambda _: None, Token()
    )
    assert result.transcript_files[0].read_text(encoding="utf-8").endswith("Hello\n")
    assert result.output_dir == tmp_path / "out" / "sample" / "Transcripts"
    assert not (tmp_path / "out" / "sample" / "temp").exists()
    assert "Succeeded" in (tmp_path / "out" / "sample" / "Summary_Report.md").read_text(
        encoding="utf-8"
    )


def test_service_rejects_missing_input(tmp_path: Path):
    with pytest.raises(ValueError, match="not found"):
        TranscriptionService(FakeProvider(), FakeMedia()).run(
            TranscriptionRequest(tmp_path / "missing.wav", tmp_path / "out"),
            lambda _: None,
            Token(),
        )


def test_missing_external_program_has_actionable_error():
    with pytest.raises(RuntimeError, match="Required program was not found"):
        ProcessRunner().run(["program-that-does-not-exist"], Token())


def test_next_available_job_dir_increments_without_overwriting(tmp_path: Path):
    (tmp_path / "example").mkdir()
    (tmp_path / "example1").mkdir()
    assert next_available_job_dir(tmp_path, "example") == tmp_path / "example2"


def test_clip_time_parsing_and_validation(tmp_path: Path):
    assert parse_clip_time("01:30") == 90
    assert parse_clip_time("1:02:03") == 3723
    with pytest.raises(ValueError):
        parse_clip_time("not-a-time")
    source = tmp_path / "clip.wav"
    source.write_bytes(b"fixture")
    with pytest.raises(ValueError, match="greater"):
        TranscriptionService(FakeProvider(), FakeMedia()).run(
            TranscriptionRequest(source, tmp_path / "out", clip_start=10, clip_end=5),
            lambda _: None,
            Token(),
        )


def test_frame_extraction_is_checkpointed(tmp_path: Path):
    source = tmp_path / "sample.mp4"
    source.write_bytes(b"fixture")
    result = TranscriptionService(FakeProvider(), FakeMedia()).run(
        TranscriptionRequest(source, tmp_path / "out", extract_frames=True), lambda _: None, Token()
    )
    job_dir = result.output_dir.parent
    report = (job_dir / "Summary_Report.md").read_text(encoding="utf-8")
    assert "Frame extraction" in report
    assert '"frame_extraction_interval"' in (job_dir / "job_state.json").read_text(encoding="utf-8")


def test_master_timeline_generated_with_speaker_badges(tmp_path: Path):
    source = tmp_path / "sample.wav"
    source.write_bytes(b"fixture")
    vtt = tmp_path / "speakers.vtt"
    vtt.write_text(
        "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\n<v Alice> Hello\n",
        encoding="utf-8",
    )
    result = TranscriptionService(FakeProvider(), FakeMedia()).run(
        TranscriptionRequest(source, tmp_path / "out", speaker_vtt_path=str(vtt)),
        lambda _: None,
        Token(),
    )
    job_dir = result.output_dir.parent
    markdown = (job_dir / "Master_Timeline.md").read_text(encoding="utf-8")
    assert "[TRANSCRIPTION]" in markdown and "[SPEAKER: Alice]" in markdown
    jsonl = (job_dir / "multimodal_timeline.jsonl").read_text(encoding="utf-8")
    assert '"speaker": "Alice"' in jsonl and '"event_type": "transcription"' in jsonl
    assert '"master_timeline"' in (job_dir / "job_state.json").read_text(encoding="utf-8")


def test_master_timeline_tolerates_malformed_vtt(tmp_path: Path):
    source = tmp_path / "sample.wav"
    source.write_bytes(b"fixture")
    vtt = tmp_path / "broken.vtt"
    vtt.write_text("garbage content\n", encoding="utf-8")
    result = TranscriptionService(FakeProvider(), FakeMedia()).run(
        TranscriptionRequest(source, tmp_path / "out", speaker_vtt_path=str(vtt)),
        lambda _: None,
        Token(),
    )
    job_dir = result.output_dir.parent
    markdown = (job_dir / "Master_Timeline.md").read_text(encoding="utf-8")
    assert "[TRANSCRIPTION]" in markdown
    assert "[SPEAKER" not in markdown


def test_text_analysis_writes_report_and_keeps_whisper_results(tmp_path: Path):
    source = tmp_path / "sample.wav"
    source.write_bytes(b"fixture")
    result = TranscriptionService(FakeProvider(), FakeMedia(), FakeTextProvider()).run(
        TranscriptionRequest(source, tmp_path / "out", analyze_text=True, analysis_model="llama3"),
        lambda _: None,
        Token(),
    )
    job_dir = result.output_dir.parent
    analysis = (job_dir / "AI_Analysis.md").read_text(encoding="utf-8")
    assert "summary of Hello in en" in analysis
    assert "- 00:00:01 highlight" in analysis
    assert "llama3" in analysis
    assert '"status": "completed"' in (job_dir / "job_state.json").read_text(encoding="utf-8")


def test_text_analysis_failure_does_not_fail_job(tmp_path: Path):
    class BrokenTextProvider:
        def summarize(self, transcript, language, on_progress=None, cancel_token=None):
            raise RuntimeError("Ollama is down")

        def extract_highlights(self, srt_content, language, on_progress=None, cancel_token=None):
            return ""

    source = tmp_path / "sample.wav"
    source.write_bytes(b"fixture")
    result = TranscriptionService(FakeProvider(), FakeMedia(), BrokenTextProvider()).run(
        TranscriptionRequest(source, tmp_path / "out", analyze_text=True), lambda _: None, Token()
    )
    job_dir = result.output_dir.parent
    assert result.transcript_files
    state = (job_dir / "job_state.json").read_text(encoding="utf-8")
    assert '"status": "Succeeded"' in state or "Succeeded" in state
    assert '"text_analysis"' in state
    assert "Ollama is down" in state


def test_process_runner_drains_large_child_output():
    result = ProcessRunner().run(
        [
            sys.executable,
            "-c",
            "import sys; sys.stdout.write('x'*100000); sys.stderr.write('y'*100000)",
        ],
        Token(),
    )
    assert result.returncode == 0
    assert len(result.stdout) == 100000
    assert len(result.stderr) == 100000


def test_recorder_requires_an_audio_source(tmp_path: Path):
    with pytest.raises(ValueError, match="Select microphone"):
        AudioRecorder().start(tmp_path / "recording.wav", False, False)


def test_recorder_rejects_unavailable_system_audio(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.infrastructure.recorder.supports_system_audio", lambda: False)
    with pytest.raises(RuntimeError, match="WASAPI support"):
        AudioRecorder().start(tmp_path / "recording.wav", False, True)


def _write_job_state(job_dir: Path, input_path: Path, transcription: str) -> None:
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "Transcripts").mkdir(exist_ok=True)
    if transcription == "completed":
        (job_dir / "Transcripts" / "converted_audio.srt").write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8"
        )
    (job_dir / "job_state.json").write_text(
        json.dumps(
            {
                "input_path": str(input_path),
                "status": "Succeeded",
                "steps": {"transcription": {"status": transcription}},
            }
        ),
        encoding="utf-8",
    )


def test_find_reusable_job_dir_requires_completed_transcription_for_same_input(tmp_path: Path):
    from app.application.service_io import find_reusable_job_dir

    source = tmp_path / "meeting.mp4"
    source.write_bytes(b"x")
    other = tmp_path / "other.mp4"
    other.write_bytes(b"x")
    _write_job_state(tmp_path / "out" / "meeting", source, "completed")
    _write_job_state(tmp_path / "out" / "other", other, "completed")
    _write_job_state(tmp_path / "out" / "failed", source, "failed")
    assert find_reusable_job_dir(tmp_path / "out", source) == tmp_path / "out" / "meeting"
    assert find_reusable_job_dir(tmp_path / "out", tmp_path / "absent.mp4") is None


def test_service_reuse_dir_skips_transcription(tmp_path: Path):
    class ExplodingProvider:
        def transcribe(self, request, on_progress, cancel_token):
            raise AssertionError("transcription must be skipped when reusing")

    source = tmp_path / "sample.wav"
    source.write_bytes(b"fixture")
    transcript = TranscriptionService(FakeProvider(), FakeMedia()).run(
        TranscriptionRequest(source, tmp_path / "out"), lambda _: None, Token()
    )
    job_dir = transcript.output_dir.parent
    reused = TranscriptionService(ExplodingProvider(), FakeMedia()).run(
        TranscriptionRequest(source, tmp_path / "out"), lambda _: None, Token(), resume_dir=job_dir
    )
    assert reused.transcript_files[0].name == "sample.srt"
