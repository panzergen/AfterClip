import json
from pathlib import Path

import pytest

from app.application.cancellation import CancellationToken
from app.application.service import JobCancelled, TranscriptionService
from app.domain.models import TranscriptionRequest, TranscriptionResult


class CountingProvider:
    def __init__(self):
        self.calls = 0

    def transcribe(self, request, on_progress, cancel_token):
        self.calls += 1
        output = request.output_dir / f"{request.input_path.stem}.srt"
        output.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
        return TranscriptionResult(request.output_dir, (output,))


class CountingMedia:
    def __init__(self, cancel_after_prepare: bool = False):
        self.prepares = 0
        self.cancel_after_prepare = cancel_after_prepare

    def prepare_audio(self, input_path, work_dir, cancel_token, clip_start=None, clip_end=None):
        self.prepares += 1
        if self.cancel_after_prepare and hasattr(cancel_token, "cancel"):
            cancel_token.cancel()
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
        return ()


def write_resumable_job(output_dir: Path, source: Path, audio_path: Path, status: str) -> Path:
    job = output_dir / "sample"
    (job / "Transcripts").mkdir(parents=True)
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"wav")
    (job / "job_state.json").write_text(
        json.dumps(
            {
                "status": status,
                "input_path": str(source),
                "output_name": "sample",
                "audio_path": str(audio_path),
                "steps": {
                    "media_preparation": {
                        "name": "Media preparation",
                        "status": "completed",
                        "duration_seconds": 0.1,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return job


def test_cancel_between_steps_does_not_run_next_step(tmp_path):
    source = tmp_path / "sample.wav"
    source.write_bytes(b"fixture")
    output = tmp_path / "out"
    provider = CountingProvider()
    media = CountingMedia(cancel_after_prepare=True)
    with pytest.raises(JobCancelled):
        TranscriptionService(provider, media).run(
            TranscriptionRequest(source, output), lambda _: None, CancellationToken()
        )
    assert provider.calls == 0
    state = json.loads((output / "sample" / "job_state.json").read_text(encoding="utf-8"))
    assert state["status"] == "Cancelled"


def test_resume_after_cancelled_replays_completed_steps(tmp_path):
    source = tmp_path / "sample.wav"
    source.write_bytes(b"fixture")
    output = tmp_path / "out"
    audio = tmp_path / "elsewhere" / "converted.wav"
    job = write_resumable_job(output, source, audio, "cancelled")
    provider = CountingProvider()
    media = CountingMedia()
    result = TranscriptionService(provider, media).run(
        TranscriptionRequest(source, output), lambda _: None, CancellationToken()
    )
    assert media.prepares == 0
    assert provider.calls == 1
    assert result.output_dir == job / "Transcripts"


def test_resume_after_failed_replays_completed_steps(tmp_path):
    source = tmp_path / "sample.wav"
    source.write_bytes(b"fixture")
    output = tmp_path / "out"
    audio = tmp_path / "elsewhere" / "converted.wav"
    job = write_resumable_job(output, source, audio, "failed")
    provider = CountingProvider()
    media = CountingMedia()
    result = TranscriptionService(provider, media).run(
        TranscriptionRequest(source, output), lambda _: None, CancellationToken()
    )
    assert media.prepares == 0
    assert provider.calls == 1
    assert result.output_dir == job / "Transcripts"


def test_stale_audio_path_in_state_triggers_reprepare(tmp_path):
    source = tmp_path / "sample.wav"
    source.write_bytes(b"fixture")
    output = tmp_path / "out"
    stale_audio = tmp_path / "missing" / "converted.wav"
    job = write_resumable_job(output, source, stale_audio, "cancelled")
    stale_audio.unlink()
    provider = CountingProvider()
    media = CountingMedia()
    TranscriptionService(provider, media).run(
        TranscriptionRequest(source, output), lambda _: None, CancellationToken()
    )
    assert media.prepares == 1
    assert provider.calls == 1
    state = json.loads((job / "job_state.json").read_text(encoding="utf-8"))
    assert state["steps"]["media_preparation"]["status"] == "completed"


class TranscriptOnlyProvider:
    """Writes a .txt transcript but no .srt, so the master timeline must skip."""

    def transcribe(self, request, on_progress, cancel_token):
        output = request.output_dir / f"{request.input_path.stem}.txt"
        output.write_text("Hello", encoding="utf-8")
        return TranscriptionResult(request.output_dir, (output,))


def test_master_timeline_skipped_without_transcript_srt(tmp_path):
    source = tmp_path / "sample.wav"
    source.write_bytes(b"fixture")
    output = tmp_path / "out"
    result = TranscriptionService(TranscriptOnlyProvider(), CountingMedia()).run(
        TranscriptionRequest(source, output), lambda _: None, CancellationToken()
    )
    assert not (result.output_dir.parent / "Master_Timeline.md").exists()
    assert result.transcript_files


def test_zero_frames_produce_a_visible_warning(tmp_path):
    events = []
    source = tmp_path / "sample.mp4"
    source.write_bytes(b"fixture")
    output = tmp_path / "out"
    TranscriptionService(CountingProvider(), CountingMedia()).run(
        TranscriptionRequest(source, output, extract_frames=True, frame_modes=("scene",)),
        events.append,
        CancellationToken(),
    )
    assert any("0 frames" in event.message for event in events)


class LanguageRecordingTextProvider:
    provider_name = "gemini"
    model = "test-model"

    def __init__(self):
        self.languages = []

    def summarize(self, transcript, language, on_progress=None, cancel_token=None):
        self.languages.append(language)
        return "summary"

    def extract_highlights(self, srt_content, language, on_progress=None, cancel_token=None):
        self.languages.append(language)
        return ""


def test_output_language_is_independent_of_transcription_language(tmp_path):
    source = tmp_path / "sample.wav"
    source.write_bytes(b"fixture")
    output = tmp_path / "out"
    provider = LanguageRecordingTextProvider()
    TranscriptionService(CountingProvider(), CountingMedia(), provider).run(
        TranscriptionRequest(
            source,
            output,
            language="tr",
            output_language="de",
            analyze_text=True,
            analysis_model="test-model",
        ),
        lambda _: None,
        CancellationToken(),
    )
    assert provider.languages and all(language == "de" for language in provider.languages)

    provider = LanguageRecordingTextProvider()
    TranscriptionService(CountingProvider(), CountingMedia(), provider).run(
        TranscriptionRequest(
            source, output, language="tr", analyze_text=True, analysis_model="test-model"
        ),
        lambda _: None,
        CancellationToken(),
    )
    assert provider.languages and all(language == "tr" for language in provider.languages)


def test_multiple_frame_modes_run_sequentially(tmp_path):
    source = tmp_path / "sample.mp4"
    source.write_bytes(b"fixture")
    output = tmp_path / "out"
    TranscriptionService(CountingProvider(), CountingMedia()).run(
        TranscriptionRequest(
            source, output, extract_frames=True, frame_modes=("interval", "scene")
        ),
        lambda _: None,
        CancellationToken(),
    )
    state = (output / "sample" / "job_state.json").read_text(encoding="utf-8")
    assert '"frame_extraction_interval"' in state
    assert '"frame_extraction_scene"' in state
