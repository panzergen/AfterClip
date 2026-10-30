"""Headless CLI (Phase 4 WS-E).

This module must never import PySide6: ``python -c "import app.cli"`` has to
stay Qt-free so scripts and agents can drive AfterClip without a display.
"""

import argparse
import copy
import json
import signal
import sys
from pathlib import Path

from app.app_paths import default_output_dir
from app.application.cancellation import CancellationToken, JobCancelled
from app.application.headless import (
    ProviderUnavailableError,
    build_providers,
    resolve_prompts,
    resolve_sanitizer,
    resolve_segment_seconds,
    resolve_topics,
    run_request,
)
from app.application.history import scan_job_history
from app.application.prompt_scope import resolve_cli_prompts
from app.application.service import parse_clip_time
from app.application.service_io import find_reusable_job_dir
from app.application.topics import TOPIC_METHODS
from app.domain.models import TranscriptionRequest
from app.domain.presets import Preset
from app.infrastructure.presets import JsonPresetStore

EXIT_SUCCESS = 0
EXIT_VALIDATION = 2
EXIT_FAILURE = 3
EXIT_CANCELLED = 130

FRAME_MODES = ("none", "interval", "scene", "both")
FRAME_RESOLUTIONS = ("full", "mid", "low")


class CliError(Exception):
    """User-facing validation error (exit code 2)."""


def _add_job_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--model", help="Whisper model (default: turbo)")
    parser.add_argument("--language", help="Transcription language hint")
    parser.add_argument(
        "--report-language",
        help="Language for all AI outputs (summary, highlights, vision, topics); "
        "omit for English",
    )
    parser.add_argument("--task", default="", help="Extra instructions for AI analysis")
    parser.add_argument(
        "--provider", help="ollama | gemini | openrouter | opencode_go | opencode_zen"
    )
    parser.add_argument("--text-model", default="", help="Text analysis model id")
    parser.add_argument("--vision-model", default="", help="Vision analysis model id")
    parser.add_argument("--analyze-text", action="store_true", help="Enable AI text analysis")
    parser.add_argument("--analyze-vision", action="store_true", help="Enable AI vision analysis")
    parser.add_argument("--frames", choices=FRAME_MODES, help="Frame extraction mode")
    parser.add_argument("--frame-interval", type=int, help="Interval seconds between frames")
    parser.add_argument("--scene-sensitivity", type=float, help="Scene change sensitivity 0-1")
    parser.add_argument("--frame-resolution", choices=FRAME_RESOLUTIONS)
    parser.add_argument("--clip-start", help="Clip start (seconds, MM:SS or HH:MM:SS)")
    parser.add_argument("--clip-end", help="Clip end (seconds, MM:SS or HH:MM:SS)")
    parser.add_argument("--vtt", help="Speaker VTT support file")
    parser.add_argument("--segment", type=float, help="Transcript merge seconds (0 = raw)")
    parser.add_argument(
        "--embed-frames", action="store_true", help="Embed frames in the HTM report"
    )
    parser.add_argument("--no-filter", action="store_true", help="Disable hallucination filtering")
    parser.add_argument("--topics", choices=TOPIC_METHODS, help="Topic segmentation method")
    parser.add_argument("--topic-min-seconds", type=float, help="Minimum topic section seconds")
    parser.add_argument("--topic-max-sections", type=int, help="Maximum topic sections")
    parser.add_argument("--preset", help="Apply a saved preset by name")
    parser.add_argument("--output-name", default="", help="Output job folder base name")
    parser.add_argument(
        "--reuse-transcription",
        "--reuse",
        dest="reuse_transcription",
        action="store_true",
        help="Reuse the latest completed transcription for this input (skip Whisper)",
    )
    parser.add_argument(
        "--resume-dir",
        "--job-dir",
        dest="resume_dir",
        help="Reuse this exact existing job folder (skip Whisper)",
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress output")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="afterclip", description="AfterClip headless CLI")
    subparsers = parser.add_subparsers(dest="command")

    run = subparsers.add_parser("run", help="Process one media file")
    run.add_argument("--input", required=True, help="Input media file")
    run.add_argument("--output", required=True, help="Output directory (job folders live here)")
    _add_job_args(run)

    batch = subparsers.add_parser("batch", help="Process several media files sequentially")
    batch.add_argument("inputs", nargs="+", help="Input media files")
    batch.add_argument("--output", required=True, help="Output directory")
    _add_job_args(batch)

    status = subparsers.add_parser("status", help="List past jobs")
    status.add_argument("--output", help="Output directory (default: workspace Output-Folder)")
    status.add_argument("--json", action="store_true")

    subparsers.add_parser("mcp", help="Run the MCP stdio server (requires the [mcp] extra)")
    return parser


def _load_preset(name: str | None) -> Preset | None:
    if not name:
        return None
    for preset in JsonPresetStore().load():
        if preset.name == name:
            return preset
    raise CliError(f"Preset not found: {name}")


def _resolve_frame_modes(args, preset: Preset | None) -> tuple[str, ...]:
    if args.frames:
        if args.frames == "none":
            return ()
        if args.frames == "both":
            return ("interval", "scene")
        return (args.frames,)
    if preset:
        modes = []
        if preset.interval_mode:
            modes.append("interval")
        if preset.scene_mode:
            modes.append("scene")
        return tuple(modes)
    return ()


def _resolve_resolution(args, preset: Preset | None) -> str:
    if args.frame_resolution:
        return args.frame_resolution
    if preset and 0 <= preset.frame_resolution_index < len(FRAME_RESOLUTIONS):
        return FRAME_RESOLUTIONS[preset.frame_resolution_index]
    return "full"


def _clip_seconds(value: str | None) -> float | None:
    return parse_clip_time(value) if value else None


def build_request(args, preset: Preset | None = None) -> TranscriptionRequest:
    input_path = Path(args.input).resolve()
    if not input_path.is_file():
        raise CliError(f"Input file not found: {input_path}")
    output_dir = Path(args.output).resolve()
    if output_dir.exists() and not output_dir.is_dir():
        raise CliError(f"Output path is not a directory: {output_dir}")

    model = args.model or (preset.whisper_model if preset else "") or "turbo"
    language = args.language if args.language is not None else (preset.language if preset else "")
    report_language = (
        args.report_language
        if args.report_language is not None
        else (preset.report_language if preset else "")
    )
    frame_modes = _resolve_frame_modes(args, preset)
    frame_interval = args.frame_interval or (preset.frame_interval if preset else 10)
    scene_sensitivity = (
        args.scene_sensitivity
        if args.scene_sensitivity is not None
        else (preset.scene_sensitivity if preset else 0.35)
    )
    analyze_text = bool(
        args.analyze_text or args.text_model or (preset.analysis_enabled if preset else False)
    )
    analyze_vision = bool(
        args.analyze_vision or args.vision_model or (preset.vision_enabled if preset else False)
    )
    text_model = args.text_model or (preset.analysis_model_text if preset else "")
    vision_model = args.vision_model or (preset.vision_model_text if preset else "")
    embed_frames = bool(args.embed_frames or (preset.embed_frames if preset else False))
    segment_seconds = args.segment if args.segment is not None else resolve_segment_seconds()
    topic_method, topic_min, topic_max = resolve_topics()
    if getattr(args, "topics", None):
        topic_method = args.topics
    if getattr(args, "topic_min_seconds", None):
        topic_min = args.topic_min_seconds
    if getattr(args, "topic_max_sections", None):
        topic_max = args.topic_max_sections

    support_files = (str(Path(args.vtt).resolve()),) if getattr(args, "vtt", None) else ()

    return TranscriptionRequest(
        input_path=input_path,
        output_dir=output_dir,
        model=model,
        language=language or "",
        user_task=args.task or "",
        clip_start=_clip_seconds(args.clip_start),
        clip_end=_clip_seconds(args.clip_end),
        extract_frames=bool(frame_modes),
        frame_interval=frame_interval,
        output_name=args.output_name or "",
        frame_mode=frame_modes[0] if frame_modes else "interval",
        scene_sensitivity=scene_sensitivity,
        frame_modes=frame_modes,
        speaker_vtt_path=support_files[0] if support_files else "",
        analyze_text=analyze_text,
        analysis_model=text_model or "",
        analyze_vision=analyze_vision,
        vision_model=vision_model or "",
        embed_frames=embed_frames,
        frame_resolution=_resolve_resolution(args, preset),
        transcript_merge_seconds=segment_seconds,
        output_language=report_language or "",
        support_files=support_files,
        topic_method=topic_method,
        topic_min_seconds=topic_min,
        topic_max_sections=topic_max,
    )


def _emit_error(args, message: str, code: int = EXIT_VALIDATION) -> None:
    if getattr(args, "json", False):
        status = "cancelled" if code == EXIT_CANCELLED else "error"
        print(json.dumps({"status": status, "error": message, "exit_code": code}))
    else:
        print(message, file=sys.stderr)


def _install_sigint(token: CancellationToken) -> None:
    def handler(_signum, _frame):
        token.cancel()

    try:
        signal.signal(signal.SIGINT, handler)
    except (ValueError, OSError):
        pass


def process_one(args, preset: Preset | None = None) -> int:
    try:
        request = build_request(args, preset)
    except CliError as error:
        _emit_error(args, str(error))
        return EXIT_VALIDATION

    resume_dir = None
    if getattr(args, "resume_dir", None):
        resume_dir = Path(args.resume_dir).resolve()
        if not resume_dir.is_dir():
            _emit_error(args, f"Job folder not found: {resume_dir}")
            return EXIT_VALIDATION
    elif getattr(args, "reuse_transcription", False):
        resume_dir = find_reusable_job_dir(request.output_dir, request.input_path)
        if resume_dir is None:
            _emit_error(
                args,
                "No completed transcription was found for this input in the output "
                "directory. Run the job once without --reuse-transcription first.",
            )
            return EXIT_VALIDATION

    prompts = resolve_cli_prompts(preset, resolve_prompts())
    sanitizer = resolve_sanitizer(enabled=False if args.no_filter else None)
    provider = args.provider or (
        "ollama" if (request.analyze_text or request.analyze_vision) else None
    )
    try:
        text_provider, vision_provider = build_providers(
            provider,
            request.analysis_model,
            request.vision_model,
            request.analyze_text,
            request.analyze_vision,
            prompts,
        )
    except ProviderUnavailableError as error:
        _emit_error(args, str(error))
        return EXIT_VALIDATION

    token = CancellationToken()
    _install_sigint(token)
    events: list[dict] = []

    def on_event(event) -> None:
        if args.quiet:
            return
        if args.json:
            events.append({"message": event.message, "percent": event.percent})
        else:
            percent = f"{event.percent}%" if event.percent is not None else "--"
            print(f"[{percent}] {event.message}", file=sys.stderr)

    try:
        result = run_request(
            request,
            text_provider,
            vision_provider,
            sanitizer,
            on_event,
            token,
            resume_dir=resume_dir,
        )
    except JobCancelled:
        _emit_error(args, "Cancelled", code=EXIT_CANCELLED)
        return EXIT_CANCELLED
    except KeyboardInterrupt:
        token.cancel()
        _emit_error(args, "Cancelled", code=EXIT_CANCELLED)
        return EXIT_CANCELLED
    except Exception as error:
        _emit_error(args, f"Processing failed: {error}", code=EXIT_FAILURE)
        return EXIT_FAILURE

    job_dir = (
        result.output_dir.parent if result.output_dir.name == "Transcripts" else result.output_dir
    )
    payload = {
        "status": "succeeded",
        "job_dir": str(job_dir),
        "transcript_dir": str(result.output_dir),
        "transcript_files": [str(path) for path in result.transcript_files],
        "reports": sorted(path.name for path in job_dir.glob("*.md")),
        "events": events,
    }
    if args.json:
        print(json.dumps(payload))
    elif not args.quiet:
        print(f"Done: {job_dir}")
    return EXIT_SUCCESS


def _cmd_run(args) -> int:
    try:
        preset = _load_preset(args.preset)
    except CliError as error:
        _emit_error(args, str(error))
        return EXIT_VALIDATION
    return process_one(args, preset)


def _cmd_batch(args) -> int:
    try:
        preset = _load_preset(args.preset)
    except CliError as error:
        _emit_error(args, str(error))
        return EXIT_VALIDATION

    worst = EXIT_SUCCESS
    for index, input_path in enumerate(args.inputs, 1):
        item = copy.copy(args)
        item.input = input_path
        item.quiet = args.quiet
        if not args.quiet and not args.json:
            print(f"[{index}/{len(args.inputs)}] {input_path}", file=sys.stderr)
        code = process_one(item, preset)
        if code != EXIT_SUCCESS:
            worst = code
        if code == EXIT_CANCELLED:
            break
    return worst


def _cmd_status(args) -> int:
    output_dir = Path(args.output).resolve() if args.output else default_output_dir()
    entries = scan_job_history(output_dir)
    payload = [
        {
            "name": entry.name,
            "status": entry.status,
            "path": str(entry.path),
            "input": entry.input_path,
        }
        for entry in entries
    ]
    if args.json:
        print(json.dumps(payload))
    else:
        for entry in entries:
            print(f"{entry.status:<10} {entry.path}")
    return EXIT_SUCCESS


def _cmd_mcp(_args) -> int:
    try:
        from app.mcp_server import main as mcp_main
    except ImportError:
        print(
            'The MCP server needs the optional dependency: pip install "afterclip[mcp]"',
            file=sys.stderr,
        )
        return EXIT_VALIDATION
    return mcp_main()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return EXIT_VALIDATION
    if args.command == "run":
        return _cmd_run(args)
    if args.command == "batch":
        return _cmd_batch(args)
    if args.command == "status":
        return _cmd_status(args)
    if args.command == "mcp":
        return _cmd_mcp(args)
    parser.print_help()
    return EXIT_VALIDATION


if __name__ == "__main__":
    raise SystemExit(main())
