import json
import logging
import shutil
from collections.abc import Callable
from pathlib import Path

from app.application.cancellation import CancelToken, JobCancelled, ProcessingCancelled
from app.application.cloud_usage import COST_NOTE, estimate_cost_usd
from app.application.forecast import forecast, load_history
from app.application.job_context import JobContext, StepRecorder
from app.application.language import language_name, language_verdict
from app.application.media_type import classify_tier1, signals_from_metadata
from app.application.ports import (
    MediaTool,
    TextAnalysisProvider,
    TranscriptionProvider,
    VisionProvider,
)
from app.application.service_io import (
    find_resumable_job_dir,
    frame_timestamp,
    frame_window,
    load_state,
    next_available_job_dir,
    parse_clip_time,
    parse_vision_descriptions,
    prompt_set_fingerprint,
    resolve_report_language,
    srt_timestamp,
    srt_transcript_text,
    transcript_context,
    validate_request,
    write_fallback_vision_srt,
    write_vision_timeline_srt,
)
from app.application.summary import clean_summary_output
from app.application.timeline import (
    find_transcript_srt,
    find_vision_srt,
    merge_transcript_entries,
    parse_speaker_vtt,
    parse_srt,
    resolve_speaker,
    write_master_timeline,
)
from app.application.topics import (
    DEFAULT_TOPIC_METHOD,
    TopicSegment,
    render_topics_summary,
    retitle_with_provider,
    segment_topics_cohesion,
    write_topics,
)
from app.application.transcript_sanitizer import (
    SanitizerConfig,
    load_segments,
    render_srt,
    render_text,
    sanitize_segments,
)
from app.application.vision_sanitizer import (
    VisionSanitizerConfig,
    VisionSanitizeResult,
    has_vision_content,
    is_blank_vision_response,
    sanitize_description,
)
from app.application.voiceprints import (
    DEFAULT_CLUSTER_THRESHOLD,
    DEFAULT_IDENTIFY_THRESHOLD,
    SpeakerSegment,
    analyse_speakers,
    identify_speaker,
    load_voiceprint_sidecar,
    write_voiceprint_sidecar,
)
from app.domain.models import (
    ProgressEvent,
    SpeakerInterval,
    TranscriptionRequest,
    TranscriptionResult,
)
from app.domain.prompts import PromptSet
from app.infrastructure.audio import TARGET_RATE, read_wav_samples, slice_samples, to_16k_mono
from app.infrastructure.llm.transport import chunk_text, clean_thinking_tags
from app.infrastructure.process import get_media_metadata

LOGGER = logging.getLogger(__name__)

# Voiceprint embeddings are computed over merged transcript blocks (not raw
# Whisper cues) so each embedding averages ~20s of speech and clusters cleanly.
VOICEPRINT_BLOCK_SECONDS = 20.0

#: Stored when a frame has no visible screen content (blank, loading or only
#: the meeting participant gallery).
BLANK_VISION_DESCRIPTION = "(no visible screen content)"

#: Bumped when vision post-processing changes so a resumed job re-runs the
#: vision step instead of reusing descriptions produced by older logic.
VISION_ANALYSIS_VERSION = 2

__all__ = ["JobCancelled", "TranscriptionService", "next_available_job_dir", "parse_clip_time"]


def resolve_speaker_vtt_path(request: TranscriptionRequest) -> str:
    """Speaker VTT comes from support files (first .vtt); legacy field as fallback."""
    for path in request.support_files:
        if Path(path).suffix.lower() == ".vtt":
            return path
    return request.speaker_vtt_path


def vision_analysis_label(vision_provider: object) -> str:
    """Step name naming the provider and model actually used for the run."""
    provider = getattr(vision_provider, "provider_name", "") or "ollama"
    model = getattr(vision_provider, "model", "")
    return f"Vision analysis ({provider}: {model})" if model else f"Vision analysis ({provider})"


#: Bumped when the report writer changes how model output is post-processed, so
#: a resumed job re-runs text analysis instead of reusing a stale report that
#: still carries a preamble or an outdated section layout.
TEXT_ANALYSIS_VERSION = 3


def analysis_fingerprint(
    provider,
    request,
    transcript_dir,
    audio_stem: str,
    version: int | None = None,
) -> dict:
    """Prompts + language identity for an analysis step (resume-staleness check)."""
    payload = {
        "prompts": prompt_set_fingerprint(getattr(provider, "prompts", None)),
        "language": resolve_report_language(request, transcript_dir, audio_stem),
    }
    if version is not None:
        payload["version"] = version
    return payload


class TranscriptionService:
    def __init__(
        self,
        provider: TranscriptionProvider,
        media_tool: MediaTool,
        text_provider: TextAnalysisProvider | None = None,
        vision_provider: VisionProvider | None = None,
        sanitizer_config: SanitizerConfig | None = None,
        vision_sanitizer_config: VisionSanitizerConfig | None = None,
        voiceprint_store=None,
        voiceprint_embedder=None,
        voiceprint_identify_threshold: float = DEFAULT_IDENTIFY_THRESHOLD,
        voiceprint_cluster_threshold: float = DEFAULT_CLUSTER_THRESHOLD,
    ):
        self.provider = provider
        self.media_tool = media_tool
        self.text_provider = text_provider
        self.vision_provider = vision_provider
        self.sanitizer_config = sanitizer_config
        self.vision_sanitizer_config = vision_sanitizer_config or VisionSanitizerConfig()
        self.voiceprint_store = voiceprint_store
        self.voiceprint_embedder = voiceprint_embedder
        self.voiceprint_identify_threshold = voiceprint_identify_threshold
        self.voiceprint_cluster_threshold = voiceprint_cluster_threshold
        self._topics: list = []
        self._speaker_intervals: tuple = ()

    def run(
        self,
        request: TranscriptionRequest,
        on_event: Callable[[ProgressEvent], None],
        cancel_token: CancelToken,
        resume_dir: Path | None = None,
    ) -> TranscriptionResult:
        validate_request(request)
        base_name = request.output_name.strip() or request.input_path.stem
        if resume_dir is not None and resume_dir.is_dir():
            # Caller chose an existing job folder ("reuse existing
            # transcription"); completed steps inside it are skipped.
            job_dir = resume_dir
        else:
            job_dir = find_resumable_job_dir(request.output_dir, base_name, request.input_path)
            if job_dir is None:
                job_dir = next_available_job_dir(request.output_dir, base_name)
        transcript_dir = job_dir / "Transcripts"
        work_dir = job_dir / "temp"
        transcript_dir.mkdir(parents=True, exist_ok=True)
        work_dir.mkdir(parents=True, exist_ok=True)
        context = JobContext(
            job_dir=job_dir,
            state_path=job_dir / "job_state.json",
            report_path=job_dir / "Summary_Report.md",
            request=request,
            metadata=get_media_metadata(request.input_path),
            state=load_state(job_dir / "job_state.json"),
            steps={},
            on_event=on_event,
        )
        context.steps = context.state.setdefault("steps", {})
        recorder = StepRecorder(context)
        recorder.report("Running")
        context.state.update(
            {
                "status": "running",
                "user_task": request.user_task,
                "input_path": str(request.input_path),
                "output_name": base_name,
                "steps": context.steps,
            }
        )
        # Features used by the time-forecasting history (Phase 4 WS-H).
        context.state["media"] = {
            "duration": context.metadata.get("duration"),
            "file_size_mb": context.metadata.get("file_size_mb"),
        }
        guess = classify_tier1(
            signals_from_metadata(
                str(request.input_path),
                context.metadata,
                has_support_vtt=bool(resolve_speaker_vtt_path(request)),
            )
        )
        context.metadata["media_type"] = guess.to_dict()
        context.state["media_type"] = guess.to_dict()
        context.state["run_settings"] = {
            "model": request.model,
            "frame_modes": list(
                request.frame_modes or ((request.frame_mode,) if request.extract_frames else ())
            ),
            "frame_resolution": request.frame_resolution,
            "analyze_text": request.analyze_text,
            "analyze_vision": request.analyze_vision,
            "voiceprint_enabled": request.voiceprint_enabled,
        }
        self._record_forecast(context, request)
        recorder.save()

        audio_path = None
        if context.steps.get("media_preparation", {}).get(
            "status"
        ) == "completed" and context.state.get("audio_path"):
            audio_path = Path(context.state["audio_path"])
            if not audio_path.exists():
                audio_path = None
                recorder.discard("media_preparation")
        if audio_path is None:
            audio_path = recorder.record(
                "media_preparation",
                "Media preparation",
                5,
                lambda: self.media_tool.prepare_audio(
                    request.input_path, work_dir, cancel_token, request.clip_start, request.clip_end
                ),
            )
            context.state["audio_path"] = str(audio_path)
            recorder.save()
        if cancel_token.is_cancelled():
            recorder.finish("Cancelled")
            raise JobCancelled
        on_event(ProgressEvent("Transcription", 20))
        result = None
        try:
            if context.steps.get("transcription", {}).get("status") == "completed":
                files = tuple(sorted(transcript_dir.glob(f"{audio_path.stem}.*")))
                if not files:
                    recorder.discard("transcription")
                else:
                    result = TranscriptionResult(transcript_dir, files)
            if result is None:
                result = recorder.record(
                    "transcription",
                    "Transcription",
                    20,
                    lambda: self.provider.transcribe(
                        TranscriptionRequest(
                            audio_path,
                            transcript_dir,
                            request.model,
                            request.language,
                            request.user_task,
                        ),
                        lambda message: on_event(ProgressEvent(message)),
                        cancel_token,
                    ),
                    emit_start=False,
                    end_percent=95,
                )
            if self.sanitizer_config is not None and self.sanitizer_config.enabled:
                filter_report = job_dir / "transcript_filter_report.json"
                if self._transcript_filter_cached(context, filter_report):
                    recorder.context.on_event(
                        ProgressEvent("Transcript filter resumed from cache", 94)
                    )
                else:
                    self._run_transcript_filter(recorder, transcript_dir, audio_path)
            self._run_topic_segmentation(recorder, transcript_dir, audio_path, cancel_token)
            if request.extract_frames:
                selected_modes = request.frame_modes or (request.frame_mode,)
                frames_dir = job_dir / "Vision" / "frames"
                for mode in selected_modes:
                    if self._frames_cached(context, mode, frames_dir):
                        recorder.context.on_event(
                            ProgressEvent(
                                f"Frame extraction ({mode.title()}) resumed from cache", 98
                            )
                        )
                        continue
                    recorder.record(
                        f"frame_extraction_{mode}",
                        f"Frame extraction ({mode.title()})",
                        98,
                        lambda mode=mode: self.media_tool.extract_interval_frames(
                            request.input_path,
                            frames_dir,
                            request.frame_interval,
                            cancel_token,
                            request.clip_start,
                            request.clip_end,
                            request.highlight_times,
                            mode,
                            request.scene_sensitivity,
                            request.frame_resolution,
                        ),
                    )
                if not any(frames_dir.glob("*.png")):
                    LOGGER.warning("Frame extraction produced 0 frames in %s", frames_dir)
                    recorder.context.on_event(
                        ProgressEvent(
                            "Frame extraction produced 0 frames; lower scene sensitivity "
                            "or enable Interval mode",
                            98,
                        )
                    )
            if request.analyze_text and self.text_provider is not None:
                expected_text = analysis_fingerprint(
                    self.text_provider,
                    request,
                    transcript_dir,
                    audio_path.stem,
                    TEXT_ANALYSIS_VERSION,
                )
                if self._text_analysis_cached(context, expected_text):
                    recorder.context.on_event(
                        ProgressEvent("AI text analysis resumed from cache", 96)
                    )
                else:
                    if context.steps.get("text_analysis", {}).get("status") == "completed":
                        recorder.context.on_event(
                            ProgressEvent(
                                "Prompts or report language changed; "
                                "AI text analysis will re-run",
                                96,
                            )
                        )
                    self._run_text_analysis(recorder, transcript_dir, audio_path, cancel_token)
            if request.analyze_vision and self.vision_provider is not None:
                vision_srt = job_dir / "Vision" / "vision_analysis.srt"
                frames_dir = job_dir / "Vision" / "frames"
                frames = (
                    {path.name for path in frames_dir.glob("*.png")}
                    if frames_dir.is_dir()
                    else set()
                )
                described = (
                    set(parse_vision_descriptions(vision_srt, self.vision_sanitizer_config))
                    if vision_srt.is_file()
                    else set()
                )
                vision_completed = (
                    context.steps.get("vision_analysis", {}).get("status") == "completed"
                )
                expected_vision = analysis_fingerprint(
                    self.vision_provider,
                    request,
                    transcript_dir,
                    audio_path.stem,
                    VISION_ANALYSIS_VERSION,
                )
                vision_prompts_match = self._prompts_state_match(
                    context, "vision_analysis_prompts", expected_vision
                )
                # Resume only when the cache describes every extracted frame;
                # a re-run that changed the frame set must be analysed again.
                # A prompts/language change also invalidates the cache.
                if (
                    vision_completed
                    and vision_srt.is_file()
                    and (not frames or frames <= described)
                    and vision_prompts_match
                ):
                    recorder.context.on_event(
                        ProgressEvent("Vision analysis resumed from cache", 97)
                    )
                else:
                    if vision_completed and not vision_prompts_match:
                        recorder.context.on_event(
                            ProgressEvent(
                                "Prompts or report language changed; "
                                "vision analysis will re-run",
                                97,
                            )
                        )
                    elif vision_completed:
                        recorder.context.on_event(
                            ProgressEvent("Frame set changed; vision analysis will re-run", 97)
                        )
                    self._run_vision_analysis(recorder, transcript_dir, audio_path, cancel_token)
            self._record_cloud_usage(recorder)
            self._run_voiceprint_labelling(recorder, transcript_dir, audio_path, cancel_token)
            self._run_master_timeline_step(recorder, job_dir, base_name, transcript_dir, audio_path)
        except ProcessingCancelled as error:
            recorder.finish("Cancelled")
            raise JobCancelled from error
        except JobCancelled:
            recorder.finish("Cancelled")
            raise
        except Exception:
            recorder.finish("Failed")
            raise
        shutil.rmtree(work_dir, ignore_errors=True)
        recorder.finish("Succeeded")
        on_event(ProgressEvent("Transcription complete", 100))
        return result

    def _record_forecast(self, context: JobContext, request: TranscriptionRequest) -> None:
        """Persist the pre-start estimate so later jobs can self-correct against it."""
        try:
            duration = float(context.metadata.get("duration") or 0.0)
        except (TypeError, ValueError):
            duration = 0.0
        if request.clip_end and request.clip_end > (request.clip_start or 0.0):
            duration = request.clip_end - (request.clip_start or 0.0)
        modes = tuple(request.frame_modes) or (
            (request.frame_mode,) if request.extract_frames else ()
        )
        result = forecast(
            duration,
            request.model,
            modes,
            bool(request.analyze_text),
            bool(request.analyze_vision),
            request.frame_resolution,
            load_history(request.output_dir),
        )
        if result.expected_seconds is not None and "forecast" not in context.state:
            context.state["forecast"] = {
                "expected_seconds": result.expected_seconds,
                "low_seconds": result.low_seconds,
                "high_seconds": result.high_seconds,
                "basis": result.basis,
                "sample_count": result.sample_count,
            }

    @staticmethod
    def _transcript_filter_cached(context: JobContext, report_path: Path) -> bool:
        if context.steps.get("transcript_filter", {}).get("status") != "completed":
            return False
        return report_path.is_file()

    def _run_transcript_filter(
        self, recorder: StepRecorder, transcript_dir: Path, audio_path: Path
    ) -> None:
        """Deterministically drop hallucinated segments; keep raw + a report (WS-C)."""
        config = self.sanitizer_config
        job_dir = recorder.context.job_dir
        stem = audio_path.stem
        json_path = transcript_dir / f"{stem}.json"
        srt_path = transcript_dir / f"{stem}.srt"
        txt_path = transcript_dir / f"{stem}.txt"
        raw_json = transcript_dir / f"{stem}.raw.json"
        raw_srt = transcript_dir / f"{stem}.raw.srt"
        raw_txt = transcript_dir / f"{stem}.raw.txt"

        def action() -> None:
            if not json_path.is_file():
                raise RuntimeError("Whisper JSON transcript not found for filtering.")
            # Preserve the raw output exactly once; re-runs stay idempotent by
            # always filtering from the preserved raw copy.
            if not raw_json.is_file():
                shutil.copy2(json_path, raw_json)
                if srt_path.is_file():
                    shutil.copy2(srt_path, raw_srt)
                if txt_path.is_file():
                    shutil.copy2(txt_path, raw_txt)
            segments = load_segments(raw_json)
            result = sanitize_segments(segments, config)
            srt_path.write_text(render_srt(result.kept), encoding="utf-8")
            txt_path.write_text(render_text(result.kept), encoding="utf-8")
            report = result.report()
            report["config"] = config.to_dict()
            (job_dir / "transcript_filter_report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            recorder.context.state["transcript_filter"] = {
                "removed": report["removed_count"],
                "flagged": report["flagged_count"],
            }

        recorder.record(
            "transcript_filter",
            "Transcript hallucination filter",
            94,
            action,
            tolerated_failure_event=("Transcript filter failed; raw transcript kept", 94),
        )

    @staticmethod
    def _frames_cached(context: JobContext, mode: str, frames_dir: Path) -> bool:
        """True when this frame mode completed earlier and its frames still exist."""
        if context.steps.get(f"frame_extraction_{mode}", {}).get("status") != "completed":
            return False
        if not frames_dir.is_dir():
            return False
        pattern = "scene_*.png" if mode == "scene" else "interval_*.png"
        return any(frames_dir.glob(pattern))

    @staticmethod
    def _prompts_state_match(context: JobContext, key: str, expected: dict) -> bool:
        """True when a previous run recorded the same prompts+language for `key`."""
        stored = context.state.get(key)
        return isinstance(stored, dict) and stored == expected

    @staticmethod
    def _text_analysis_cached(context: JobContext, expected: dict | None = None) -> bool:
        """True when text analysis completed earlier and its report remains.

        When `expected` (prompts fingerprint + language) is given, a mismatch
        means the prompts changed since and the step must re-run instead of
        reusing stale outputs.
        """
        if context.steps.get("text_analysis", {}).get("status") != "completed":
            return False
        if not (context.job_dir / "AI_Analysis.md").is_file():
            return False
        return expected is None or TranscriptionService._prompts_state_match(
            context, "text_analysis_prompts", expected
        )

    def _topics_markdown_section(self) -> str:
        topics_summary = render_topics_summary(self._topics)
        return f"\n## Topics\n\n{topics_summary}\n" if topics_summary else ""

    def _record_cloud_usage(self, recorder: StepRecorder) -> None:
        """Persist provider usage/cost metadata when a cloud client ran (Phase 3)."""
        usages = []
        for provider in (self.text_provider, self.vision_provider):
            usage = getattr(getattr(provider, "client", None), "usage", None)
            if usage is not None and (usage.requests or usage.images):
                usages.append(usage)
        if not usages:
            return
        merged = usages[0]
        for extra in usages[1:]:
            merged = merged.merged(extra)
        payload = merged.to_dict()
        cost = estimate_cost_usd(merged)
        if cost is not None:
            payload["estimated_cost_usd"] = cost
        payload["cost_note"] = COST_NOTE
        recorder.context.metadata["cloud_usage"] = payload
        recorder.context.state["cloud_usage"] = payload
        recorder.save()

    def _run_topic_segmentation(
        self,
        recorder: StepRecorder,
        transcript_dir: Path,
        audio_path: Path,
        cancel_token: CancelToken,
    ) -> None:
        """Topic sections (WS-I); off/failure leaves outputs flat, AI titles fall back."""
        request = recorder.context.request
        method = request.topic_method or DEFAULT_TOPIC_METHOD
        if method == "off":
            return
        transcript_srt = find_transcript_srt(transcript_dir, audio_path.stem)
        if transcript_srt is None:
            return

        def action() -> None:
            entries = parse_srt(transcript_srt, "TRANSCRIPTION")
            speaker_intervals = parse_speaker_vtt(resolve_speaker_vtt_path(request))
            merged = entries
            if request.transcript_merge_seconds and request.transcript_merge_seconds > 0:
                merged = merge_transcript_entries(
                    entries, request.transcript_merge_seconds, speaker_intervals
                )
            topics = segment_topics_cohesion(
                merged,
                request.topic_min_seconds,
                request.topic_max_sections or None,
            )
            if not topics:
                return
            if method == "ai" and self.text_provider is not None:
                topics = retitle_with_provider(
                    topics,
                    merged,
                    self.text_provider,
                    getattr(self.text_provider, "prompts", None),
                    resolve_report_language(request, transcript_dir, audio_path.stem),
                    cancel_token,
                )
            write_topics(recorder.context.job_dir, topics)
            self._topics = list(topics)
            recorder.context.state["topics"] = [topic.to_dict() for topic in topics]
            recorder.context.on_event(ProgressEvent(f"Topics: {len(topics)} section(s)", 95))

        recorder.record(
            "topic_segmentation",
            "Topic segmentation",
            95,
            action,
            tolerated_failure_event=("Topic segmentation failed; timeline stays flat", 95),
        )

    def _ensure_report_language(
        self,
        text: str,
        language: str,
        cancel_token: CancelToken,
    ) -> str:
        """Rewrite a report block when the model answered in another language.

        Topics are handled by their own guard; summaries and highlights are
        long-lived prose and use the same verdict check here. When no text
        provider is available (vision-only jobs) the original text is kept.
        """
        if not text or not language:
            return text
        if language_verdict(text, language) is not False:
            return text
        generate = getattr(self.text_provider, "generate", None)
        if not callable(generate):
            return text
        prompt = (
            f"Rewrite the text below entirely in {language_name(language)}. "
            "Keep every fact, name, number, timestamp and bullet point; do not add "
            "or remove content. Output only the rewritten text.\n\n"
            f"{text}"
        )
        try:
            rewritten = generate(prompt, cancel_token)
        except Exception as error:  # a translation must not discard the report
            LOGGER.warning("Report language rewrite failed: %s", error)
            return text
        rewritten = clean_thinking_tags(rewritten or "").strip()
        if rewritten and language_verdict(rewritten, language) is not False:
            return rewritten
        return text

    def _run_text_analysis(
        self,
        recorder: StepRecorder,
        transcript_dir: Path,
        audio_path: Path,
        cancel_token: CancelToken,
    ) -> None:
        """Optional local AI analysis; failure never fails the job (T16)."""
        request = recorder.context.request

        def action() -> None:
            srt_path = find_transcript_srt(transcript_dir, audio_path.stem)
            srt_content = srt_path.read_text(encoding="utf-8", errors="ignore") if srt_path else ""
            txt_path = transcript_dir / f"{audio_path.stem}.txt"
            transcript_text = (
                txt_path.read_text(encoding="utf-8", errors="ignore")
                if txt_path.is_file()
                else srt_transcript_text(srt_path)
            )
            language = resolve_report_language(request, transcript_dir, audio_path.stem)

            def progress(message: str) -> None:
                recorder.context.on_event(ProgressEvent(message))

            chunks = chunk_text(transcript_text, getattr(self.text_provider, "chunk_size", 3500))
            recorder.context.on_event(
                ProgressEvent(f"AI analysis: transcript split into {len(chunks)} section(s)", 96)
            )
            summary = clean_summary_output(
                self.text_provider.summarize(
                    transcript_text, language, progress, cancel_token
                )
            )
            summary = self._ensure_report_language(summary, language, cancel_token)
            try:
                highlights = (
                    self.text_provider.extract_highlights(
                        srt_content, language, progress, cancel_token
                    )
                    if srt_content
                    else ""
                )
            except Exception as error:
                # A summary is already in hand; a highlights outage must not
                # discard it (T16 policy granularity).
                LOGGER.warning("Highlights failed; keeping the summary: %s", error)
                highlights = ""
            highlights = self._ensure_report_language(highlights, language, cancel_token)
            (recorder.context.job_dir / "AI_Analysis.md").write_text(
                "# AI Analysis\n\n"
                f"- **Provider:** `{getattr(self.text_provider, 'provider_name', 'local')}`\n"
                f"- **Model:** `{request.analysis_model or self.text_provider.model}`\n\n"
                "## Summary\n\n"
                f"{summary}\n\n"
                "## Key Highlights\n\n"
                f"{highlights or 'No highlights were extracted.'}\n"
                f"{self._topics_markdown_section()}",
                encoding="utf-8",
            )
            recorder.context.state["text_analysis_prompts"] = analysis_fingerprint(
                self.text_provider,
                request,
                transcript_dir,
                audio_path.stem,
                TEXT_ANALYSIS_VERSION,
            )

        recorder.record(
            "text_analysis",
            "AI text analysis",
            96,
            action,
            tolerated_failure_event=("AI analysis failed; Whisper results are kept", 96),
        )

    def _run_vision_analysis(
        self,
        recorder: StepRecorder,
        transcript_dir: Path,
        audio_path: Path,
        cancel_token: CancelToken,
    ) -> None:
        """Describe extracted frames through the vision provider.

        Failure is non-fatal (T16 policy).
        """
        request = recorder.context.request
        frames_dir = recorder.context.job_dir / "Vision" / "frames"
        frames = tuple(sorted(frames_dir.glob("*.png"))) if frames_dir.is_dir() else ()
        if not frames:
            LOGGER.info("Vision analysis skipped: no extracted frames.")
            recorder.context.on_event(
                ProgressEvent("Vision analysis skipped: no extracted frames", 97)
            )
            return
        vision_dir = recorder.context.job_dir / "Vision"
        language = resolve_report_language(request, transcript_dir, audio_path.stem)

        def action() -> None:
            entries = []
            changes: list[dict] = []
            retried = 0
            blank = 0
            frame_errors: list[Exception] = []
            for index, frame in enumerate(frames, 1):
                recorder.context.on_event(
                    ProgressEvent(f"Vision analysis frame {index}/{len(frames)}", 97)
                )
                timestamp = frame_timestamp(
                    frame, request.frame_interval, request.clip_start, request.highlight_times
                )
                audio_context = transcript_context(transcript_dir, audio_path.stem, timestamp)
                frame_failed = False
                try:
                    description = self.vision_provider.analyze_frame(
                        frame,
                        audio_context,
                        request.user_task,
                        language,
                        None,
                        cancel_token,
                    )
                except Exception as error:
                    # One unreadable frame must not discard the other 100+
                    # descriptions. The step still fails when every frame
                    # fails, so a genuinely unavailable provider is reported.
                    LOGGER.warning("Vision failed for %s: %s", frame.name, error)
                    frame_errors.append(error)
                    frame_failed = True
                    description = ""
                cleaned = sanitize_description(description, self.vision_sanitizer_config)
                reason = cleaned.reason
                retry_description = None
                if frame_failed:
                    cleaned = VisionSanitizeResult(
                        BLANK_VISION_DESCRIPTION, True, "blank", 0
                    )
                    reason = "blank"
                    blank += 1
                # A custom pack may not fit this frame (for example a slide-only
                # prompt on a browser screen). Retry once with the built-in
                # content-agnostic prompt instead of storing an all-[none] answer.
                elif not has_vision_content(description):
                    if is_blank_vision_response(description):
                        cleaned = VisionSanitizeResult(
                            BLANK_VISION_DESCRIPTION, True, "blank", len(description)
                        )
                        reason = "blank"
                        blank += 1
                    else:
                        fallback_prompt = PromptSet().render(
                            "vision_frame",
                            user_desc=request.user_task,
                            audio_context=audio_context,
                            lang=language or "en",
                        )
                        try:
                            retry_description = self.vision_provider.analyze_frame(
                                frame,
                                audio_context,
                                request.user_task,
                                language,
                                None,
                                cancel_token,
                                prompt=fallback_prompt,
                            )
                        except Exception as error:  # a retry must not drop the frame
                            LOGGER.warning(
                                "Vision retry failed for %s: %s", frame.name, error
                            )
                            retry_description = ""
                        retried += 1
                        retry_cleaned = sanitize_description(
                            retry_description, self.vision_sanitizer_config
                        )
                        if has_vision_content(retry_description, include_highlight=True):
                            cleaned = retry_cleaned
                            reason = "empty_retry"
                        else:
                            cleaned = VisionSanitizeResult(
                                BLANK_VISION_DESCRIPTION, True, "blank", len(description)
                            )
                            reason = "blank"
                            blank += 1
                if cleaned.changed or reason in {"empty_retry", "blank"}:
                    change = {
                        "frame": frame.name,
                        "reason": reason,
                        "original": description,
                        "cleaned": cleaned.text,
                    }
                    if retry_description is not None:
                        change["retry"] = retry_description
                    changes.append(change)
                window = frame_window(frame, request.frame_interval)
                entries.append((timestamp, window, frame.name, cleaned.text))
            if frame_errors and len(frame_errors) == len(frames):
                raise frame_errors[0]
            vision_dir.mkdir(parents=True, exist_ok=True)
            with (vision_dir / "vision_analysis.srt").open("w", encoding="utf-8") as vision_srt:
                for number, (timestamp, window, frame_name, description) in enumerate(entries, 1):
                    vision_srt.write(
                        f"{number}\n"
                        f"{srt_timestamp(timestamp)} --> {srt_timestamp(timestamp + window)}\n"
                        f"FILE: {frame_name}\n"
                        f"DESCRIPTION: {description}\n\n"
                    )
            report = {
                "collapsed_count": len(changes),
                "retried_count": retried,
                "blank_count": blank,
                "frame_count": len(entries),
                "config": self.vision_sanitizer_config.to_dict(),
                "changes": changes,
            }
            (vision_dir / "vision_filter_report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            recorder.context.state["vision_filter"] = {
                "collapsed": len(changes),
                "retried": retried,
                "blank": blank,
            }
            recorder.context.state["vision_analysis_prompts"] = analysis_fingerprint(
                self.vision_provider,
                request,
                transcript_dir,
                audio_path.stem,
                VISION_ANALYSIS_VERSION,
            )

        recorder.record(
            "vision_analysis",
            vision_analysis_label(self.vision_provider),
            97,
            action,
            tolerated_failure_event=("Vision analysis failed; other results are kept", 97),
        )

    def _cached_voiceprint_intervals(
        self,
        job_dir: Path,
        vtt_intervals: tuple[SpeakerInterval, ...],
    ) -> tuple[SpeakerInterval, ...]:
        """Restore speaker labels from the job sidecar without reading audio.

        Only the segments that had no speaker-VTT label are in the sidecar.
        Stored cluster labels are kept, and enrolled names are refreshed from
        the current voiceprint store when one is available.
        """
        segments, clusters = load_voiceprint_sidecar(job_dir / "Voiceprints.json")
        if not segments:
            return vtt_intervals
        stored_labels = {
            (start_ms, end_ms): cluster.label
            for cluster in clusters
            for start_ms, end_ms in cluster.segments
        }
        voiceprints = self.voiceprint_store.load() if self.voiceprint_store is not None else {}
        restored: list[SpeakerInterval] = []
        for segment in segments:
            name = (
                identify_speaker(
                    segment.embedding,
                    voiceprints,
                    self.voiceprint_identify_threshold,
                )
                if voiceprints
                else None
            )
            label = name or stored_labels.get((segment.start_ms, segment.end_ms))
            if label:
                restored.append(SpeakerInterval(segment.start_ms, segment.end_ms, label))
        return vtt_intervals + tuple(restored)

    def _run_voiceprint_labelling(
        self,
        recorder: StepRecorder,
        transcript_dir: Path,
        audio_path: Path,
        cancel_token: CancelToken,
    ) -> None:
        """Fill speaker gaps with voiceprints; never overrides the speaker VTT.

        Voiceprints complement the VTT: a segment already covered by the VTT
        keeps its label, and only unlabeled segments are identified (against
        enrolled voiceprints) or clustered into ``Speaker N``.
        """
        request = recorder.context.request
        vtt_intervals = parse_speaker_vtt(resolve_speaker_vtt_path(request))
        # A resumed job keeps the labels its completed voiceprint step already
        # produced; re-reading the audio is only needed for a fresh run.
        self._speaker_intervals = self._cached_voiceprint_intervals(
            recorder.context.job_dir, vtt_intervals
        )
        if not request.voiceprint_enabled:
            return
        if self.voiceprint_embedder is None or self.voiceprint_store is None:
            LOGGER.warning("Voiceprints enabled but unavailable; skipping speaker identification.")
            recorder.context.state["voiceprint_labelling"] = {
                "status": "skipped",
                "reason": "voiceprint extra not installed",
            }
            recorder.save()
            return
        transcript_srt = find_transcript_srt(transcript_dir, audio_path.stem)
        if transcript_srt is None:
            return

        def action():
            # Embed merged blocks, not raw Whisper cues: a ~2s cue yields a
            # noisy embedding that fragments clustering, while a ~20s block is
            # robust and produces a handful of speaker groups.
            entries = parse_srt(transcript_srt, "TRANSCRIPTION")
            blocks = merge_transcript_entries(entries, VOICEPRINT_BLOCK_SECONDS, ())
            unlabelled = [
                (entry.start_ms, entry.end_ms)
                for entry in blocks
                if resolve_speaker(vtt_intervals, entry.start_ms, entry.end_ms) is None
            ]
            if not unlabelled:
                return vtt_intervals
            samples, rate, channels = read_wav_samples(audio_path)
            samples = to_16k_mono(samples, rate, channels)
            voiceprints = self.voiceprint_store.load()
            work_dir = recorder.context.job_dir / "temp"
            speaker_segments = []
            labelled = []
            for start_ms, end_ms in unlabelled:
                chunk = slice_samples(samples, start_ms / 1000.0, end_ms / 1000.0, TARGET_RATE)
                if len(chunk) < TARGET_RATE * 0.3:
                    continue
                try:
                    embedding = self.voiceprint_embedder.embed_samples(chunk, TARGET_RATE, work_dir)
                except Exception as error:  # a failed slice must not fail the job
                    LOGGER.warning(
                        "Voiceprint embedding failed for %d–%dms: %s", start_ms, end_ms, error
                    )
                    continue
                labelled.append((start_ms, end_ms))
                speaker_segments.append(SpeakerSegment(start_ms, end_ms, embedding))
            if not labelled:
                return vtt_intervals
            analysis = analyse_speakers(
                labelled,
                [segment.embedding for segment in speaker_segments],
                voiceprints,
                self.voiceprint_identify_threshold,
                self.voiceprint_cluster_threshold,
            )
            write_voiceprint_sidecar(
                recorder.context.job_dir / "Voiceprints.json", speaker_segments, analysis.clusters
            )
            return vtt_intervals + tuple(analysis.intervals)

        combined = recorder.record(
            "voiceprint_labelling",
            "Speaker identification",
            99,
            action,
            tolerated_failure_event=(
                "Speaker identification failed; timeline keeps VTT speakers",
                99,
            ),
        )
        self._speaker_intervals = tuple(combined) if combined is not None else vtt_intervals

    def reprocess_voiceprints(
        self,
        request: TranscriptionRequest,
        job_dir: Path,
        on_event: Callable[[ProgressEvent], None],
        cancel_token: CancelToken,
    ) -> bool:
        """Re-label a finished job from its stored embeddings (no audio re-read).

        Used after enrollment: the same segment embeddings are re-matched against
        the updated voiceprint store and the master timeline is rewritten. All
        other steps (Whisper, frames, text/vision) are untouched.
        """
        sidecar_path = job_dir / "Voiceprints.json"
        segments, _ = load_voiceprint_sidecar(sidecar_path)
        if not segments:
            return False
        state = load_state(job_dir / "job_state.json")
        self._topics = [
            TopicSegment(**topic) for topic in state.get("topics", []) if isinstance(topic, dict)
        ]
        voiceprints = self.voiceprint_store.load() if self.voiceprint_store is not None else {}
        vtt_intervals = parse_speaker_vtt(resolve_speaker_vtt_path(request))
        analysis = analyse_speakers(
            [(segment.start_ms, segment.end_ms) for segment in segments],
            [segment.embedding for segment in segments],
            voiceprints,
            self.voiceprint_identify_threshold,
            self.voiceprint_cluster_threshold,
        )
        self._speaker_intervals = vtt_intervals + tuple(analysis.intervals)
        write_voiceprint_sidecar(sidecar_path, segments, analysis.clusters)

        base_name = request.output_name.strip() or Path(state.get("input_path", "")).stem
        audio_path = Path(state.get("audio_path") or "converted_audio.wav")
        context = JobContext(
            job_dir=job_dir,
            state_path=job_dir / "job_state.json",
            report_path=job_dir / "Summary_Report.md",
            request=request,
            metadata=state.get("media_type", {}),
            state=state,
            steps=state.setdefault("steps", {}),
            on_event=on_event,
        )
        self._run_master_timeline_step(
            StepRecorder(context), job_dir, base_name, job_dir / "Transcripts", audio_path
        )
        return True

    def _run_master_timeline_step(
        self,
        recorder: StepRecorder,
        job_dir: Path,
        base_name: str,
        transcript_dir: Path,
        audio_path: Path,
    ) -> None:
        request = recorder.context.request
        speaker_intervals = self._speaker_intervals or parse_speaker_vtt(
            resolve_speaker_vtt_path(request)
        )
        transcript_srt = find_transcript_srt(transcript_dir, audio_path.stem)
        if transcript_srt is None:
            LOGGER.info("Master timeline skipped: no transcript subtitles found.")
            recorder.context.on_event(ProgressEvent("Master timeline skipped: no subtitles found"))
            return

        def action():
            # Every extracted frame reaches the timeline: real AI descriptions
            # where a vision run produced them, placeholders otherwise, and
            # never dropped just because a partial/stale vision SRT omitted it.
            ai_vision_srt = find_vision_srt(job_dir, base_name)
            if ai_vision_srt is None:
                vision_srt = write_fallback_vision_srt(
                    job_dir,
                    request.frame_interval,
                    request.clip_start,
                    request.highlight_times,
                )
            else:
                vision_srt = write_vision_timeline_srt(
                    job_dir,
                    request.frame_interval,
                    request.clip_start,
                    request.highlight_times,
                    parse_vision_descriptions(ai_vision_srt, self.vision_sanitizer_config),
                )
            analysis_path = job_dir / "AI_Analysis.md"
            analysis_markdown = (
                analysis_path.read_text(encoding="utf-8", errors="ignore")
                if analysis_path.is_file()
                else ""
            )
            return write_master_timeline(
                job_dir,
                transcript_srt,
                vision_srt,
                speaker_intervals,
                embed_frames=request.embed_frames,
                transcript_merge_seconds=request.transcript_merge_seconds,
                analysis_markdown=analysis_markdown,
                topics=tuple(self._topics),
            )

        timeline_paths = recorder.record("master_timeline", "Master timeline", 99, action)
        context = recorder.context
        context.state["master_timeline_path"] = str(timeline_paths[0])
        recorder.save()
