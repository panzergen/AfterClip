"""MCP stdio server (Phase 4 WS-E).

Thin, local-only wrappers over the same service the GUI uses. The official
``mcp`` SDK is an optional dependency (``pip install "afterclip[mcp]"``); this
module imports it lazily so ``import app.mcp_server`` stays Qt- and SDK-free.

Security: tools only read/write under the configured workspace roots, never
return secrets, and obey the cloud upload policy (video is never uploaded).
"""

import argparse
import json
import os
import sys
from pathlib import Path

from app.app_paths import default_input_dir, default_output_dir
from app.application.headless import (
    build_providers,
    resolve_prompts,
    resolve_sanitizer,
    run_request,
)
from app.application.history import scan_job_history
from app.application.prompt_scope import resolve_cli_prompts
from app.domain.presets import Preset
from app.infrastructure.presets import JsonPresetStore

ALLOWED_REPORT_FILES = (
    "Summary_Report.md",
    "Master_Timeline.md",
    "AI_Analysis.md",
    "transcript_filter_report.json",
    "job_state.json",
)

MCP_INSTALL_HINT = 'pip install "afterclip[mcp]"'


def allowed_roots() -> tuple[Path, ...]:
    """Workspace roots tools may read/write (path allowlist)."""
    roots = {default_input_dir(), default_output_dir()}
    home = os.environ.get("AFTERCLIP_HOME")
    if home:
        roots.add(Path(home))
    return tuple(root.resolve() for root in roots)


def ensure_allowed(path: Path) -> Path:
    resolved = Path(path).resolve()
    for root in allowed_roots():
        if resolved == root or root in resolved.parents:
            return resolved
    raise PermissionError(f"Path is outside the allowed workspace roots: {resolved}")


# -- tool implementations (SDK-free, unit-testable) --------------------------------


def list_jobs(output_dir: str | None = None) -> list[dict]:
    root = ensure_allowed(Path(output_dir)) if output_dir else default_output_dir()
    return [
        {
            "name": entry.name,
            "status": entry.status,
            "path": str(entry.path),
            "input": entry.input_path,
        }
        for entry in scan_job_history(root)
    ]


def get_job_status(job_dir: str) -> dict:
    path = ensure_allowed(Path(job_dir)) / "job_state.json"
    if not path.is_file():
        raise FileNotFoundError(f"No job_state.json in {job_dir}")
    state = json.loads(path.read_text(encoding="utf-8"))
    steps = state.get("steps", {})
    return {
        "status": state.get("status", "unknown"),
        "current_step": state.get("current_step"),
        "steps": {
            key: {"status": value.get("status"), "duration_seconds": value.get("duration_seconds")}
            for key, value in steps.items()
            if isinstance(value, dict)
        },
        "cloud_usage": state.get("cloud_usage"),
    }


def read_report(job_dir: str, name: str = "Summary_Report.md") -> str:
    root = ensure_allowed(Path(job_dir))
    if name not in ALLOWED_REPORT_FILES:
        raise PermissionError(f"Report not exposed over MCP: {name}")
    path = root / name
    if not path.is_file():
        raise FileNotFoundError(f"Report not found: {name}")
    return path.read_text(encoding="utf-8", errors="replace")


def list_presets() -> list[dict]:
    return [
        {
            "name": preset.name,
            "whisper_model": preset.whisper_model,
            "language": preset.language,
            "report_language": preset.report_language,
            "analyze_text": preset.analysis_enabled,
            "analyze_vision": preset.vision_enabled,
            "prompt_mode": preset.prompt_mode,
            "has_prompts": bool(preset.prompts),
            "is_legacy_prompts": preset.is_legacy_prompts,
        }
        for preset in JsonPresetStore().load()
    ]


def _preset_by_name(name: str | None) -> Preset | None:
    if not name:
        return None
    for preset in JsonPresetStore().load():
        if preset.name == name:
            return preset
    raise ValueError(f"Preset not found: {name}")


def transcribe_media(
    input_path: str,
    output_dir: str | None = None,
    model: str = "turbo",
    language: str = "",
    report_language: str = "",
    provider: str | None = None,
    text_model: str = "",
    vision_model: str = "",
    analyze_text: bool = False,
    analyze_vision: bool = False,
    frames: str = "none",
    preset: str | None = None,
) -> dict:
    from app.cli import build_request

    source = ensure_allowed(Path(input_path))
    if not source.is_file():
        raise FileNotFoundError(f"Input file not found: {source}")
    output = ensure_allowed(Path(output_dir)) if output_dir else default_output_dir()

    saved_preset = _preset_by_name(preset)
    args = argparse.Namespace(
        input=str(source),
        output=str(output),
        model=model or None,
        language=language or None,
        report_language=report_language or None,
        task="",
        provider=provider,
        text_model=text_model,
        vision_model=vision_model,
        analyze_text=analyze_text,
        analyze_vision=analyze_vision,
        frames=frames or None,
        frame_interval=None,
        scene_sensitivity=None,
        frame_resolution=None,
        clip_start=None,
        clip_end=None,
        vtt=None,
        segment=None,
        embed_frames=False,
        no_filter=False,
        preset=preset,
        output_name="",
        json=False,
        quiet=True,
    )
    request = build_request(args, saved_preset)
    prompts = resolve_cli_prompts(saved_preset, resolve_prompts())
    active_provider = provider or (
        "ollama" if (request.analyze_text or request.analyze_vision) else None
    )
    text_provider, vision_provider = build_providers(
        active_provider,
        request.analysis_model,
        request.vision_model,
        request.analyze_text,
        request.analyze_vision,
        prompts,
    )
    result = run_request(request, text_provider, vision_provider, resolve_sanitizer())
    job_dir = (
        result.output_dir.parent if result.output_dir.name == "Transcripts" else result.output_dir
    )
    return {
        "status": "succeeded",
        "job_dir": str(job_dir),
        "transcripts": [str(path) for path in result.transcript_files],
        "reports": sorted(path.name for path in job_dir.glob("*.md")),
    }


TOOL_SPECS: tuple[dict, ...] = (
    {
        "name": "transcribe_media",
        "description": "Transcribe a media file and build reports; returns the job directory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_path": {"type": "string"},
                "output_dir": {"type": "string"},
                "model": {"type": "string"},
                "language": {"type": "string"},
                "report_language": {"type": "string"},
                "provider": {"type": "string"},
                "text_model": {"type": "string"},
                "vision_model": {"type": "string"},
                "analyze_text": {"type": "boolean"},
                "analyze_vision": {"type": "boolean"},
                "frames": {"type": "string", "enum": ["none", "interval", "scene", "both"]},
                "preset": {"type": "string"},
            },
            "required": ["input_path"],
        },
    },
    {
        "name": "get_job_status",
        "description": "Read a job's status and step timings.",
        "inputSchema": {
            "type": "object",
            "properties": {"job_dir": {"type": "string"}},
            "required": ["job_dir"],
        },
    },
    {
        "name": "list_jobs",
        "description": "List past jobs under the output directory.",
        "inputSchema": {
            "type": "object",
            "properties": {"output_dir": {"type": "string"}},
        },
    },
    {
        "name": "read_report",
        "description": "Read one whitelisted report file from a job directory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "job_dir": {"type": "string"},
                "name": {"type": "string", "enum": list(ALLOWED_REPORT_FILES)},
            },
            "required": ["job_dir"],
        },
    },
    {
        "name": "list_presets",
        "description": "List saved job presets.",
        "inputSchema": {"type": "object", "properties": {}},
    },
)


def tool_specs() -> list[dict]:
    return [dict(spec) for spec in TOOL_SPECS]


def build_server():
    """Create the FastMCP server (imports the optional SDK; raises ImportError)."""
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("afterclip")

    @server.tool()
    def transcribe_media_tool(
        input_path: str,
        output_dir: str | None = None,
        model: str = "turbo",
        language: str = "",
        report_language: str = "",
        provider: str | None = None,
        text_model: str = "",
        vision_model: str = "",
        analyze_text: bool = False,
        analyze_vision: bool = False,
        frames: str = "none",
        preset: str | None = None,
    ) -> dict:
        return transcribe_media(
            input_path,
            output_dir,
            model,
            language,
            report_language,
            provider,
            text_model,
            vision_model,
            analyze_text,
            analyze_vision,
            frames,
            preset,
        )

    @server.tool()
    def get_job_status_tool(job_dir: str) -> dict:
        return get_job_status(job_dir)

    @server.tool()
    def list_jobs_tool(output_dir: str | None = None) -> list[dict]:
        return list_jobs(output_dir)

    @server.tool()
    def read_report_tool(job_dir: str, name: str = "Summary_Report.md") -> str:
        return read_report(job_dir, name)

    @server.tool()
    def list_presets_tool() -> list[dict]:
        return list_presets()

    return server


def main() -> int:
    try:
        server = build_server()
    except ImportError:
        print(
            f"The MCP server needs the optional dependency: {MCP_INSTALL_HINT}",
            file=sys.stderr,
        )
        return 2
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
