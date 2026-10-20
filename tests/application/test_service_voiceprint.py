import json

from app.application.job_context import JobContext, StepRecorder
from app.application.service import TranscriptionService
from app.application.voiceprints import SpeakerCluster, SpeakerSegment, write_voiceprint_sidecar
from app.domain.models import TranscriptionRequest
from app.infrastructure.audio import write_wav_samples


class Token:
    def is_cancelled(self):
        return False


class FakeEmbedder:
    def embed_samples(self, samples, sample_rate=16000, work_dir=None):
        return [1.0, 0.0, 0.0]


class FakeVoiceprintStore:
    def __init__(self, data=None):
        self._data = dict(data or {})

    def load(self):
        return dict(self._data)


SRT = (
    "1\n00:00:00,000 --> 00:00:02,000\nhello there\n\n"
    "2\n00:00:30,000 --> 00:00:32,000\nworld again\n\n"
)

VTT = "WEBVTT\n\n00:00:00.000 --> 00:00:02.000\n<v Alice>hello there\n\n"


def _make_service():
    return TranscriptionService(
        None,
        None,
        voiceprint_store=FakeVoiceprintStore({"Bob": [1.0, 0.0, 0.0]}),
        voiceprint_embedder=FakeEmbedder(),
    )


def test_voiceprint_labelling_complements_vtt(tmp_path):
    transcript_dir = tmp_path / "Transcripts"
    transcript_dir.mkdir()
    (transcript_dir / "a.srt").write_text(SRT, encoding="utf-8")
    vtt_path = tmp_path / "speakers.vtt"
    vtt_path.write_text(VTT, encoding="utf-8")
    audio_path = tmp_path / "a.wav"
    write_wav_samples(audio_path, [0.0] * (32 * 16000))

    request = TranscriptionRequest(
        tmp_path / "a.mp4",
        tmp_path / "out",
        speaker_vtt_path=str(vtt_path),
        voiceprint_enabled=True,
    )
    job_dir = tmp_path / "out" / "a"
    job_dir.mkdir(parents=True)
    context = JobContext(
        job_dir=job_dir,
        state_path=job_dir / "job_state.json",
        report_path=job_dir / "Summary_Report.md",
        request=request,
        metadata={},
        state={"steps": {}},
        steps={},
        on_event=lambda _event: None,
    )
    service = _make_service()
    service._run_voiceprint_labelling(StepRecorder(context), transcript_dir, audio_path, Token())

    intervals = service._speaker_intervals
    by_speaker = {interval.speaker: interval for interval in intervals}
    assert "Alice" in by_speaker  # VTT label preserved
    assert "Bob" in by_speaker  # voiceprint fills the unlabeled gap
    assert by_speaker["Alice"].end_ms == 2000
    assert by_speaker["Bob"].start_ms == 30000


def test_voiceprint_labelling_skips_when_disabled(tmp_path):
    transcript_dir = tmp_path / "Transcripts"
    transcript_dir.mkdir()
    (transcript_dir / "a.srt").write_text(SRT, encoding="utf-8")
    vtt_path = tmp_path / "speakers.vtt"
    vtt_path.write_text(VTT, encoding="utf-8")
    audio_path = tmp_path / "a.wav"
    write_wav_samples(audio_path, [0.0] * (4 * 16000))

    request = TranscriptionRequest(
        tmp_path / "a.mp4",
        tmp_path / "out",
        speaker_vtt_path=str(vtt_path),
        voiceprint_enabled=False,
    )
    job_dir = tmp_path / "out" / "a"
    job_dir.mkdir(parents=True)
    context = JobContext(
        job_dir=job_dir,
        state_path=job_dir / "job_state.json",
        report_path=job_dir / "Summary_Report.md",
        request=request,
        metadata={},
        state={"steps": {}},
        steps={},
        on_event=lambda _event: None,
    )
    service = _make_service()
    service._run_voiceprint_labelling(StepRecorder(context), transcript_dir, audio_path, Token())
    assert {interval.speaker for interval in service._speaker_intervals} == {"Alice"}


def test_reprocess_voiceprints_relabels_from_sidecar(tmp_path):
    job_dir = tmp_path / "job"
    transcript_dir = job_dir / "Transcripts"
    transcript_dir.mkdir(parents=True)
    (transcript_dir / "converted_audio.srt").write_text(
        "1\n00:00:00,000 --> 00:00:02,000\nhello world\n\n", encoding="utf-8"
    )
    (job_dir / "job_state.json").write_text(
        json.dumps(
            {
                "status": "Succeeded",
                "input_path": str(tmp_path / "a.mp4"),
                "output_name": "a",
                "audio_path": str(job_dir / "temp" / "converted_audio.wav"),
                "topics": [],
                "steps": {},
            }
        ),
        encoding="utf-8",
    )
    write_voiceprint_sidecar(
        job_dir / "Voiceprints.json",
        [SpeakerSegment(0, 2000, [1.0, 0.0, 0.0])],
        [SpeakerCluster("Speaker 1", [1.0, 0.0, 0.0], [(0, 2000)])],
    )

    service = TranscriptionService(
        None,
        None,
        voiceprint_store=FakeVoiceprintStore({"Alice": [1.0, 0.0, 0.0]}),
        voiceprint_embedder=FakeEmbedder(),
    )
    request = TranscriptionRequest(tmp_path / "a.mp4", tmp_path / "out")
    ok = service.reprocess_voiceprints(request, job_dir, lambda _event: None, Token())
    assert ok is True
    speakers = {interval.speaker for interval in service._speaker_intervals}
    assert "Alice" in speakers
    assert "Speaker 1" not in speakers
    assert (job_dir / "Master_Timeline.md").is_file()
