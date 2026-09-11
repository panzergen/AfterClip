import logging
import shutil
from collections.abc import Callable
from pathlib import Path

from app.application.cancellation import CancelToken, JobCancelled, ProcessingCancelled
from app.application.job_context import JobContext, StepRecorder
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
    srt_timestamp,
    srt_transcript_text,
    transcript_context,
    validate_request,
    write_fallback_vision_srt,
    write_vision_timeline_srt,
)
from app.application.timeline import (
    find_transcript_srt,
    find_vision_srt,
    parse_speaker_vtt,
    write_master_timeline,
)
from app.domain.models import ProgressEvent, TranscriptionRequest, TranscriptionResult
from app.infrastructure.llm.transport import chunk_text
from app.infrastructure.process import get_media_metadata

LOGGER = logging.getLogger(__name__)

__all__ = ["JobCancelled", "TranscriptionService", "next_available_job_dir", "parse_clip_time"]


def resolve_speaker_vtt_path(request: TranscriptionRequest) -> str:
    """Speaker VTT comes from support files (first .vtt); legacy field as fallback."""
    for path in request.support_files:
        if Path(path).suffix.lower() == ".vtt":
            return path
    return request.speaker_vtt_path


class TranscriptionService:
    def __init__(
        self,
        provider: TranscriptionProvider,
        media_tool: MediaTool,
        text_provider: TextAnalysisProvider | None = None,
        vision_provider: VisionProvider | None = None,
    ):
        self.provider = provider
        self.media_tool = media_tool
        self.text_provider = text_provider
        self.vision_provider = vision_provider

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
            if request.extract_frames:
                selected_modes = request.frame_modes or (request.frame_mode,)
                for mode in selected_modes:
                    recorder.record(
                        f"frame_extraction_{mode}",
                        f"Frame extraction ({mode.title()})",
                        98,
                        lambda mode=mode: self.media_tool.extract_interval_frames(
                            request.input_path,
                            job_dir / "Vision" / "frames",
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
                frames_dir = job_dir / "Vision" / "frames"
                if not any(frames_dir.glob("*.png")):
                    LOGGER.warning("Frame extraction produced 0 frames in %s", frames_dir)
                    recorder.context.on_event(
                        ProgressEvent(
                            "Frame extraction produced 0 frames; lower scene sensitivity or enable Interval mode",
                            98,
                        )
                    )
            if request.analyze_text and self.text_provider is not None:
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
                    set(parse_vision_descriptions(vision_srt)) if vision_srt.is_file() else set()
                )
                vision_completed = (
                    context.steps.get("vision_analysis", {}).get("status") == "completed"
                )
                # Resume only when the cache describes every extracted frame;
                # a re-run that changed the frame set must be analysed again.
                if (
                    vision_completed
                    and vision_srt.is_file()
                    and (not frames or frames <= described)
                ):
                    recorder.context.on_event(
                        ProgressEvent("Vision analysis resumed from cache", 97)
                    )
                else:
                    if vision_completed:
                        recorder.context.on_event(
                            ProgressEvent("Frame set changed; vision analysis will re-run", 97)
                        )
                    self._run_vision_analysis(recorder, transcript_dir, audio_path, cancel_token)
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
            language = request.output_language.strip() or request.language.strip() or "en"
            progress = lambda message: recorder.context.on_event(ProgressEvent(message))
            chunks = chunk_text(transcript_text, getattr(self.text_provider, "chunk_size", 3500))
            recorder.context.on_event(
                ProgressEvent(f"AI analysis: transcript split into {len(chunks)} section(s)", 96)
            )
            summary = self.text_provider.summarize(
                transcript_text, language, progress, cancel_token
            )
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
            (recorder.context.job_dir / "AI_Analysis.md").write_text(
                "# AI Analysis\n\n"
                f"- **Provider:** `{getattr(self.text_provider, 'provider_name', 'local')}`\n"
                f"- **Model:** `{request.analysis_model or self.text_provider.model}`\n\n"
                "## Summary\n\n"
                f"{summary}\n\n"
                "## Key Highlights\n\n"
                f"{highlights or 'No highlights were extracted.'}\n",
                encoding="utf-8",
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
        """Describe extracted frames through the vision provider; failure is non-fatal (T16 policy)."""
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
        language = request.output_language.strip() or request.language.strip() or "en"

        def action() -> None:
            entries = []
            for index, frame in enumerate(frames, 1):
                recorder.context.on_event(
                    ProgressEvent(f"Vision analysis frame {index}/{len(frames)}", 97)
                )
                timestamp = frame_timestamp(
                    frame, request.frame_interval, request.clip_start, request.highlight_times
                )
                audio_context = transcript_context(transcript_dir, audio_path.stem, timestamp)
                description = self.vision_provider.analyze_frame(
                    frame,
                    audio_context,
                    request.user_task,
                    language,
                    None,
                    cancel_token,
                )
                window = frame_window(frame, request.frame_interval)
                entries.append((timestamp, window, frame.name, description))
            vision_dir.mkdir(parents=True, exist_ok=True)
            with (vision_dir / "vision_analysis.srt").open("w", encoding="utf-8") as vision_srt:
                for number, (timestamp, window, frame_name, description) in enumerate(entries, 1):
                    vision_srt.write(
                        f"{number}\n"
                        f"{srt_timestamp(timestamp)} --> {srt_timestamp(timestamp + window)}\n"
                        f"FILE: {frame_name}\n"
                        f"DESCRIPTION: {description}\n\n"
                    )

        recorder.record(
            "vision_analysis",
            "Vision analysis (Ollama)",
            97,
            action,
            tolerated_failure_event=("Vision analysis failed; other results are kept", 97),
        )

    def _run_master_timeline_step(
        self,
        recorder: StepRecorder,
        job_dir: Path,
        base_name: str,
        transcript_dir: Path,
        audio_path: Path,
    ) -> None:
        request = recorder.context.request
        speaker_intervals = parse_speaker_vtt(resolve_speaker_vtt_path(request))
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
                    parse_vision_descriptions(ai_vision_srt),
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
            )

        timeline_paths = recorder.record("master_timeline", "Master timeline", 99, action)
        context = recorder.context
        context.state["master_timeline_path"] = str(timeline_paths[0])
        recorder.save()
