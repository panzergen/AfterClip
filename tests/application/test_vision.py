import json
from pathlib import Path

from app.application.service import TranscriptionService
from app.application.service_io import (
    frame_timestamp,
    frame_window,
    srt_timestamp,
    transcript_context,
    write_fallback_vision_srt,
)
from app.domain.models import TranscriptionRequest, TranscriptionResult


class CountingProvider:
    def __init__(self):
        self.calls = 0

    def transcribe(self, request, on_progress, cancel_token):
        self.calls += 1
        srt = request.output_dir / f"{request.input_path.stem}.srt"
        srt.write_text(
            "1\n00:00:00,000 --> 00:00:12,000\nLook at this screen\n"
            "2\n00:00:12,000 --> 00:00:30,000\nImportant conclusion\n",
            encoding="utf-8",
        )
        txt = request.output_dir / f"{request.input_path.stem}.txt"
        txt.write_text("Look at this screen. Important conclusion.", encoding="utf-8")
        return TranscriptionResult(request.output_dir, (srt, txt))


class FrameProducingMedia:
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
        (frames_dir / "interval_000000.png").write_bytes(b"frame")
        (frames_dir / "scene_01h00m05s.png").write_bytes(b"frame")
        (frames_dir / "interval_highlight_001.png").write_bytes(b"frame")
        return tuple(sorted(frames_dir.glob("*.png")))


class FakeVisionProvider:
    def __init__(self):
        self.calls = []

    def analyze_frame(
        self, image_path, audio_context, user_task, language, on_progress=None, cancel_token=None
    ):
        self.calls.append((Path(image_path).name, audio_context))
        return f"vision sees {Path(image_path).name} while hearing '{audio_context}'"


class BrokenVisionProvider:
    def analyze_frame(
        self, image_path, audio_context, user_task, language, on_progress=None, cancel_token=None
    ):
        raise RuntimeError("vision model is not installed")


class LoopingVisionProvider:
    provider_name = "ollama"
    model = "llava:7b"

    def analyze_frame(
        self, image_path, audio_context, user_task, language, on_progress=None, cancel_token=None
    ):
        return "the menu bar, the menu bar, the menu bar, the menu bar"


def run_job(
    tmp_path,
    vision_provider,
    extract_frames=True,
    analyze_vision=True,
    highlight_times=(),
    clip_start=None,
    embed_frames=False,
):
    source = tmp_path / "sample.mp4"
    source.write_bytes(b"fixture")
    output = tmp_path / "out"
    request = TranscriptionRequest(
        source,
        output,
        "tiny",
        "tr",
        extract_frames=extract_frames,
        frame_modes=("interval", "scene"),
        highlight_times=highlight_times,
        clip_start=clip_start,
        analyze_vision=analyze_vision,
        vision_model="llava",
        embed_frames=embed_frames,
    )
    return TranscriptionService(
        CountingProvider(), FrameProducingMedia(), None, vision_provider
    ).run(
        request,
        lambda event: None,
        type("Token", (), {"is_cancelled": lambda self: False})(),
    )


def test_frame_timestamp_recovered_from_frame_names():
    assert frame_timestamp(Path("scene_01h01m01s.png"), 10, None, ()) == 3661.0
    assert frame_timestamp(Path("scene_01h01m01s.png"), 10, 30.0, ()) == 3691.0
    assert frame_timestamp(Path("interval_000003.png"), 10, 5.0, ()) == 35.0
    assert frame_timestamp(Path("interval_highlight_002.png"), 10, None, (1.0, 7.5)) == 7.5
    assert frame_timestamp(Path("interval_highlight_009.png"), 10, None, (1.0,)) == 0.0
    assert frame_timestamp(Path("unknown.png"), 10, None, ()) == 0.0


def test_srt_timestamp_formatting():
    assert srt_timestamp(0) == "00:00:00,000"
    assert srt_timestamp(3661.5) == "01:01:01,500"
    assert srt_timestamp(-1) == "00:00:00,000"


def test_transcript_context_overlapping_and_fallback(tmp_path):
    transcript_dir = tmp_path / "Transcripts"
    transcript_dir.mkdir()
    (transcript_dir / "converted.srt").write_text(
        "1\n00:00:00,000 --> 00:00:12,000\nLook at this screen\n"
        "2\n00:00:12,000 --> 00:00:30,000\nImportant conclusion\n",
        encoding="utf-8",
    )
    assert transcript_context(transcript_dir, "converted", 5.0) == "Look at this screen"
    assert transcript_context(transcript_dir, "converted", 40.0) == "Important conclusion"
    assert transcript_context(transcript_dir, "converted", -1.0) == "Look at this screen"
    assert transcript_context(transcript_dir, "converted", 0.0) == "Look at this screen"


def test_transcript_context_without_srt_is_empty(tmp_path):
    assert transcript_context(tmp_path / "Transcripts", "converted", 5.0) == ""


def test_vision_analysis_writes_srt_and_feeds_master_timeline(tmp_path):
    vision = FakeVisionProvider()
    run_job(tmp_path, vision, highlight_times=(7.5,))
    job_dir = tmp_path / "out" / "sample"
    vision_srt = (job_dir / "Vision" / "vision_analysis.srt").read_text(encoding="utf-8")
    assert "FILE: interval_000000.png" in vision_srt
    assert "FILE: scene_01h00m05s.png" in vision_srt
    assert "FILE: interval_highlight_001.png" in vision_srt
    assert "DESCRIPTION: vision sees" in vision_srt
    analyzed = {name for name, _ in vision.calls}
    assert analyzed == {"interval_000000.png", "scene_01h00m05s.png", "interval_highlight_001.png"}
    by_name = {name: context for name, context in vision.calls}
    # interval frame 0 sits at t=0 -> transcript overlap; highlight maps to t=7.5
    assert by_name["interval_000000.png"] != ""
    assert by_name["interval_highlight_001.png"] != ""
    markdown = (job_dir / "Master_Timeline.md").read_text(encoding="utf-8")
    assert "[VISION]" in markdown and "![Frame](Vision/frames/interval_000000.png)" in markdown
    jsonl = (job_dir / "multimodal_timeline.jsonl").read_text(encoding="utf-8")
    assert '"event_type": "vision"' in jsonl and '"frame_path": "Vision/frames/' in jsonl
    state = json.loads((job_dir / "job_state.json").read_text(encoding="utf-8"))
    assert state["steps"]["vision_analysis"]["status"] == "completed"


def test_vision_loop_is_sanitized_before_writing(tmp_path):
    run_job(tmp_path, LoopingVisionProvider())
    job_dir = tmp_path / "out" / "sample"
    vision_srt = (job_dir / "Vision" / "vision_analysis.srt").read_text(encoding="utf-8")
    assert "DESCRIPTION: the menu bar" in vision_srt
    assert vision_srt.count("the menu bar, the menu bar") == 0
    report = json.loads(
        (job_dir / "Vision" / "vision_filter_report.json").read_text(encoding="utf-8")
    )
    assert report["collapsed_count"] == 3
    assert report["changes"][0]["reason"] == "repetition"
    state = json.loads((job_dir / "job_state.json").read_text(encoding="utf-8"))
    assert state["steps"]["vision_analysis"]["name"] == "Vision analysis (ollama: llava:7b)"
    # The master timeline renders the cleaned description, not the loop.
    markdown = (job_dir / "Master_Timeline.md").read_text(encoding="utf-8")
    assert "the menu bar, the menu bar" not in markdown


class EmptyThenDescribingVisionProvider:
    """First pass returns placeholders; the generic retry describes the frame."""

    provider_name = "ollama"
    model = "llava"

    def __init__(self):
        self.prompts = []

    def analyze_frame(
        self,
        image_path,
        audio_context,
        user_task,
        language,
        on_progress=None,
        cancel_token=None,
        prompt=None,
    ):
        self.prompts.append(prompt)
        if prompt is None:
            return "TITLE: [none] SLIDE TEXT: [none] VISUALS: [none] HIGHLIGHT: [none]"
        return "TITLE: Dashboard SCREEN TEXT: User list"


class BlankVisionProvider:
    provider_name = "ollama"
    model = "llava"

    def __init__(self):
        self.calls = 0

    def analyze_frame(
        self,
        image_path,
        audio_context,
        user_task,
        language,
        on_progress=None,
        cancel_token=None,
        prompt=None,
    ):
        self.calls += 1
        return "BLANK: true"


def test_placeholder_vision_response_retries_with_generic_prompt(tmp_path):
    provider = EmptyThenDescribingVisionProvider()
    run_job(tmp_path, provider)
    job_dir = tmp_path / "out" / "sample"
    vision_srt = (job_dir / "Vision" / "vision_analysis.srt").read_text(encoding="utf-8")
    assert "DESCRIPTION: TITLE: Dashboard" in vision_srt
    assert "[none]" not in vision_srt
    assert provider.prompts.count(None) == 3
    retries = [prompt for prompt in provider.prompts if prompt is not None]
    assert len(retries) == 3
    assert retries[0].startswith("This frame is from a screen recording")
    report = json.loads(
        (job_dir / "Vision" / "vision_filter_report.json").read_text(encoding="utf-8")
    )
    assert report["retried_count"] == 3
    assert {change["reason"] for change in report["changes"]} == {"empty_retry"}


def test_blank_vision_response_is_marked_without_retry(tmp_path):
    provider = BlankVisionProvider()
    run_job(tmp_path, provider)
    job_dir = tmp_path / "out" / "sample"
    vision_srt = (job_dir / "Vision" / "vision_analysis.srt").read_text(encoding="utf-8")
    assert "DESCRIPTION: (no visible screen content)" in vision_srt
    assert provider.calls == 3
    report = json.loads(
        (job_dir / "Vision" / "vision_filter_report.json").read_text(encoding="utf-8")
    )
    assert report["blank_count"] == 3
    assert report["retried_count"] == 0


class PartialTextProvider:
    """Summary succeeds; highlights fail - the summary must still be written."""

    provider_name = "gemini"
    model = "test-model"

    def summarize(self, transcript, language, on_progress=None, cancel_token=None):
        return "the meeting summary"

    def extract_highlights(self, srt_content, language, on_progress=None, cancel_token=None):
        raise RuntimeError("highlights failed for all sections")


def test_summary_survives_highlights_failure(tmp_path):
    source = tmp_path / "sample.mp4"
    source.write_bytes(b"fixture")
    output = tmp_path / "out"
    request = TranscriptionRequest(
        source, output, "tiny", "tr", analyze_text=True, analysis_model="test-model"
    )
    TranscriptionService(
        CountingProvider(), FrameProducingMedia(), PartialTextProvider(), None
    ).run(
        request,
        lambda event: None,
        type("Token", (), {"is_cancelled": lambda self: False})(),
    )
    job_dir = output / "sample"
    analysis = (job_dir / "AI_Analysis.md").read_text(encoding="utf-8")
    assert "the meeting summary" in analysis
    assert "No highlights were extracted." in analysis
    state = json.loads((job_dir / "job_state.json").read_text(encoding="utf-8"))
    assert state["steps"]["text_analysis"]["status"] == "completed"


def test_vision_frames_embedded_in_report_when_requested(tmp_path):
    run_job(tmp_path, FakeVisionProvider(), embed_frames=True)
    job_dir = tmp_path / "out" / "sample"
    markdown = (job_dir / "Master_Timeline.md").read_text(encoding="utf-8")
    assert "![Frame](Vision/frames/interval_000000.png)" in markdown
    assert "data:image" not in markdown
    html_text = (job_dir / "FullReportAndTimeline.htm").read_text(encoding="utf-8")
    assert "data:image/png;base64," in html_text


class PartialVisionFailureProvider:
    def __init__(self):
        self.calls = 0

    def analyze_frame(
        self, image_path, audio_context, user_task, language, on_progress=None, cancel_token=None
    ):
        self.calls += 1
        if self.calls == 2:
            raise RuntimeError("one frame failed")
        return "TITLE: Dashboard SCREEN TEXT: User list"


def test_one_failed_frame_does_not_discard_the_others(tmp_path):
    run_job(tmp_path, PartialVisionFailureProvider())
    job_dir = tmp_path / "out" / "sample"
    state = json.loads((job_dir / "job_state.json").read_text(encoding="utf-8"))
    assert state["status"] == "Succeeded"
    assert state["steps"]["vision_analysis"]["status"] == "completed"
    vision_srt = (job_dir / "Vision" / "vision_analysis.srt").read_text(encoding="utf-8")
    assert "DESCRIPTION: TITLE: Dashboard" in vision_srt
    assert "DESCRIPTION: (no visible screen content)" in vision_srt
    report = json.loads(
        (job_dir / "Vision" / "vision_filter_report.json").read_text(encoding="utf-8")
    )
    assert report["blank_count"] == 1


def test_vision_failure_keeps_other_results(tmp_path):
    run_job(tmp_path, BrokenVisionProvider())
    job_dir = tmp_path / "out" / "sample"
    state = json.loads((job_dir / "job_state.json").read_text(encoding="utf-8"))
    assert state["status"] == "Succeeded"
    assert state["steps"]["vision_analysis"]["status"] == "failed"
    assert "vision model is not installed" in state["steps"]["vision_analysis"]["error"]
    assert (job_dir / "Master_Timeline.md").is_file()


def test_vision_skipped_without_frames(tmp_path):
    run_job(tmp_path, FakeVisionProvider(), extract_frames=False)
    job_dir = tmp_path / "out" / "sample"
    assert not (job_dir / "Vision" / "vision_analysis.srt").exists()
    state = json.loads((job_dir / "job_state.json").read_text(encoding="utf-8"))
    assert "vision_analysis" not in state["steps"]


def test_fallback_vision_srt_lists_frames_without_ai(tmp_path):
    run_job(tmp_path, FakeVisionProvider(), analyze_vision=False, highlight_times=(7.5,))
    job_dir = tmp_path / "out" / "sample"
    vision_srt = (job_dir / "Vision" / "vision_analysis.srt").read_text(encoding="utf-8")
    assert "FILE: interval_000000.png" in vision_srt
    assert "FILE: scene_01h00m05s.png" in vision_srt
    assert "FILE: interval_highlight_001.png" in vision_srt
    assert "(no AI description)" in vision_srt
    markdown = (job_dir / "Master_Timeline.md").read_text(encoding="utf-8")
    assert markdown.count("[VISION]") == 3
    jsonl = (job_dir / "multimodal_timeline.jsonl").read_text(encoding="utf-8")
    assert jsonl.count('"event_type": "vision"') == 3


def test_fallback_vision_srt_without_frames_returns_none(tmp_path):
    assert write_fallback_vision_srt(tmp_path, 10, None, ()) is None


def test_vision_timeline_srt_keeps_descriptions_and_covers_all_frames(tmp_path):
    from app.application.service_io import parse_vision_descriptions, write_vision_timeline_srt

    frames = tmp_path / "Vision" / "frames"
    frames.mkdir(parents=True)
    (frames / "scene_00h00m02s.png").write_bytes(b"a")
    (frames / "scene_00h00m09s.png").write_bytes(b"b")
    (tmp_path / "Vision" / "vision_analysis.srt").write_text(
        "1\n00:00:02,000 --> 00:00:07,000\n"
        "FILE: scene_00h00m02s.png\nDESCRIPTION: A login page\n\n",
        encoding="utf-8",
    )
    descriptions = parse_vision_descriptions(tmp_path / "Vision" / "vision_analysis.srt")
    assert descriptions == {"scene_00h00m02s.png": "A login page"}
    merged = write_vision_timeline_srt(tmp_path, 10, None, (), descriptions)
    text = merged.read_text(encoding="utf-8")
    assert "FILE: scene_00h00m02s.png" in text and "DESCRIPTION: A login page" in text
    assert "FILE: scene_00h00m09s.png" in text and "(no AI description)" in text


def test_partial_vision_cache_reruns_and_all_frames_reach_timeline(tmp_path):
    vision = FakeVisionProvider()
    source = tmp_path / "sample.mp4"
    source.write_bytes(b"fixture")
    output = tmp_path / "out"
    request = TranscriptionRequest(
        source,
        output,
        "tiny",
        "tr",
        extract_frames=True,
        frame_modes=("interval", "scene"),
        analyze_vision=True,
        vision_model="llava",
    )
    token = type("Token", (), {"is_cancelled": lambda self: False})()
    TranscriptionService(CountingProvider(), FrameProducingMedia(), None, vision).run(
        request, lambda event: None, token
    )
    job_dir = output / "sample"
    assert len(vision.calls) == 3
    # A re-run extracted one more frame; the cached vision SRT is now partial.
    (job_dir / "Vision" / "frames" / "scene_00h00m09s.png").write_bytes(b"new frame")
    replayed = FakeVisionProvider()
    TranscriptionService(CountingProvider(), FrameProducingMedia(), None, replayed).run(
        request, lambda event: None, token, resume_dir=job_dir
    )
    assert len(replayed.calls) == 4
    markdown = (job_dir / "Master_Timeline.md").read_text(encoding="utf-8")
    assert markdown.count("[VISION]") == 4


def test_frame_window_by_frame_kind():
    assert frame_window(Path("interval_000003.png"), 10) == 10.0
    assert frame_window(Path("scene_01h01m01s.png"), 10) == 5.0
    assert frame_window(Path("interval_highlight_001.png"), 10) == 5.0


def test_vision_analysis_resumes_from_checkpoint(tmp_path):
    job_dir = tmp_path / "out" / "sample"
    vision_dir = job_dir / "Vision"
    vision_dir.mkdir(parents=True)
    (vision_dir / "vision_analysis.srt").write_text(
        "1\n00:00:00,000 --> 00:00:10,000\nFILE: interval_000000.png\nDESCRIPTION: cached\n\n",
        encoding="utf-8",
    )
    state = {
        "status": "cancelled",
        "steps": {
            "vision_analysis": {
                "name": "Vision analysis (Ollama)",
                "status": "completed",
                "duration_seconds": 1.0,
            }
        },
    }
    (job_dir / "job_state.json").write_text(json.dumps(state), encoding="utf-8")

    vision = FakeVisionProvider()

    class NoTranscribeProvider:
        def transcribe(self, request, on_progress, cancel_token):
            srt = request.output_dir / f"{request.input_path.stem}.srt"
            srt.write_text("1\n00:00:00,000 --> 00:00:12,000\nHello\n", encoding="utf-8")
            return TranscriptionResult(request.output_dir, (srt,))

    class NoFramesMedia:
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
            return ()

    source = tmp_path / "sample.mp4"
    source.write_bytes(b"fixture")
    TranscriptionService(NoTranscribeProvider(), NoFramesMedia(), None, vision).run(
        TranscriptionRequest(source, tmp_path / "out", analyze_vision=True, vision_model="llava"),
        lambda event: None,
        type("Token", (), {"is_cancelled": lambda self: False})(),
    )
    assert vision.calls == []
    assert "DESCRIPTION: cached" in (vision_dir / "vision_analysis.srt").read_text(encoding="utf-8")
