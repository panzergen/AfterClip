import json

from app.application.cancellation import CancellationToken
from app.application.service import TranscriptionService, analysis_fingerprint
from app.application.service_io import (
    detect_transcript_language,
    prompt_set_fingerprint,
    resolve_report_language,
)
from app.domain.models import TranscriptionRequest, TranscriptionResult
from app.domain.prompts import PromptSet, build_prompt_set


def _request(**overrides):
    from pathlib import Path

    base = {
        "input_path": Path("sample.mp4"),
        "output_dir": Path("out"),
    }
    base.update(overrides)
    return TranscriptionRequest(**base)


def test_detect_transcript_language_reads_whisper_json(tmp_path):
    (tmp_path / "sample.json").write_text(
        json.dumps({"text": "merhaba", "language": "tr"}), encoding="utf-8"
    )
    assert detect_transcript_language(tmp_path, "sample") == "tr"


def test_detect_transcript_language_normalizes_case(tmp_path):
    (tmp_path / "sample.json").write_text(json.dumps({"language": "TR"}), encoding="utf-8")
    assert detect_transcript_language(tmp_path, "sample") == "tr"


def test_detect_transcript_language_rejects_missing_and_bad(tmp_path):
    assert detect_transcript_language(tmp_path, "missing") == ""
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    assert detect_transcript_language(tmp_path, "bad") == ""
    (tmp_path / "odd.json").write_text(json.dumps({"language": "klingon!!"}), encoding="utf-8")
    assert detect_transcript_language(tmp_path, "odd") == ""
    (tmp_path / "nolang.json").write_text(json.dumps({"text": "hi"}), encoding="utf-8")
    assert detect_transcript_language(tmp_path, "nolang") == ""


def test_resolve_report_language_prefers_explicit_selection(tmp_path):
    (tmp_path / "sample.json").write_text(json.dumps({"language": "tr"}), encoding="utf-8")
    request = _request(output_language="de", language="en")
    assert resolve_report_language(request, tmp_path, "sample") == "de"


def test_resolve_report_language_falls_back_to_detected_video_language(tmp_path):
    (tmp_path / "sample.json").write_text(json.dumps({"language": "tr"}), encoding="utf-8")
    request = _request(output_language="", language="")
    assert resolve_report_language(request, tmp_path, "sample") == "tr"


def test_resolve_report_language_hint_then_english(tmp_path):
    request = _request(output_language="", language="fr")
    assert resolve_report_language(request, tmp_path, "sample") == "fr"
    assert resolve_report_language(_request(), tmp_path, "sample") == "en"


class DetectedLanguageProvider:
    """Fake transcriber that writes Whisper-style SRT+JSON with a language tag."""

    def transcribe(self, request, on_progress, cancel_token):
        stem = request.input_path.stem
        (request.output_dir / f"{stem}.srt").write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nMerhaba\n", encoding="utf-8"
        )
        (request.output_dir / f"{stem}.json").write_text(
            json.dumps({"text": "Merhaba", "language": "tr"}), encoding="utf-8"
        )
        files = tuple(sorted(request.output_dir.glob(f"{stem}.*")))
        return TranscriptionResult(request.output_dir, files)


class LanguageRecordingTextProvider:
    provider_name = "test"
    model = "test-model"

    def __init__(self, prompts=None):
        self.languages = []
        self.calls = 0
        self.prompts = prompts

    def summarize(self, transcript, language, on_progress=None, cancel_token=None):
        self.languages.append(language)
        self.calls += 1
        return "summary"

    def extract_highlights(self, srt_content, language, on_progress=None, cancel_token=None):
        self.languages.append(language)
        return ""


class PassthroughMedia:
    def prepare_audio(self, input_path, work_dir, cancel_token, clip_start=None, clip_end=None):
        return input_path

    def extract_interval_frames(self, *args, **kwargs):
        return ()


def test_service_uses_detected_video_language_when_nothing_selected(tmp_path):
    source = tmp_path / "sample.wav"
    source.write_bytes(b"fixture")
    provider = LanguageRecordingTextProvider()
    TranscriptionService(DetectedLanguageProvider(), PassthroughMedia(), provider).run(
        TranscriptionRequest(
            source, tmp_path / "out", analyze_text=True, analysis_model="test-model"
        ),
        lambda _: None,
        CancellationToken(),
    )
    assert provider.languages and all(language == "tr" for language in provider.languages)


def test_resumed_job_reruns_analysis_when_prompts_changed(tmp_path):
    from app.domain.prompts import build_prompt_set as _build

    source = tmp_path / "sample.wav"
    source.write_bytes(b"fixture")
    out = tmp_path / "out"

    def run_with(summary_text):
        provider = LanguageRecordingTextProvider(
            prompts=_build({"summary": summary_text})
        )
        TranscriptionService(DetectedLanguageProvider(), PassthroughMedia(), provider).run(
            TranscriptionRequest(
                source, out, analyze_text=True, analysis_model="test-model"
            ),
            lambda _: None,
            CancellationToken(),
        )
        return provider

    first = run_with("AAA {lang} {transcript}")
    assert first.calls == 1
    job_dirs = [path for path in out.iterdir() if path.is_dir()]
    assert len(job_dirs) == 1
    state_path = job_dirs[0] / "job_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["text_analysis_prompts"]["language"] == "tr"

    # Simulate a failed job resumed with different prompts: analysis must re-run.
    state["status"] = "failed"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    second = run_with("BBB {lang} {transcript}")
    assert second.calls == 1

    # Same prompts on the next resume: the cached report is reused.
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["status"] = "failed"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    third = run_with("BBB {lang} {transcript}")
    assert third.calls == 0


def test_prompt_set_fingerprint_is_stable_and_sensitive(tmp_path):
    first = prompt_set_fingerprint(build_prompt_set({"summary": "A {lang} {transcript}"}))
    assert first == prompt_set_fingerprint(build_prompt_set({"summary": "A {lang} {transcript}"}))
    assert first != prompt_set_fingerprint(build_prompt_set({"summary": "B {lang} {transcript}"}))
    assert first != prompt_set_fingerprint(PromptSet())
    assert prompt_set_fingerprint(None) == ""
    assert prompt_set_fingerprint(object()) == ""


def test_text_analysis_cached_rejects_changed_prompts(tmp_path):
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    (job_dir / "AI_Analysis.md").write_text("# AI Analysis\n", encoding="utf-8")
    import types

    ctx = types.SimpleNamespace(
        steps={"text_analysis": {"status": "completed"}},
        job_dir=job_dir,
        state={"text_analysis_prompts": {"prompts": "aaa", "language": "tr"}},
    )
    assert TranscriptionService._text_analysis_cached(ctx, {"prompts": "aaa", "language": "tr"}) is True
    assert TranscriptionService._text_analysis_cached(ctx, {"prompts": "bbb", "language": "tr"}) is False
    assert TranscriptionService._text_analysis_cached(ctx, {"prompts": "aaa", "language": "en"}) is False
    # Old job states without a fingerprint never count as cached.
    ctx.state = {}
    assert TranscriptionService._text_analysis_cached(ctx, {"prompts": "aaa", "language": "tr"}) is False
    # Missing report is never cached.
    (job_dir / "AI_Analysis.md").unlink()
    ctx.state = {"text_analysis_prompts": {"prompts": "aaa", "language": "tr"}}
    assert TranscriptionService._text_analysis_cached(ctx, {"prompts": "aaa", "language": "tr"}) is False
