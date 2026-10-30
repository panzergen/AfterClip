# Headless CLI and MCP Server

Phase 4 (WS-E) adds a non-interactive entry point so scripts and AI agents can
produce reports without the GUI. The CLI path never imports PySide6.

## CLI

`afterclip` with no arguments still opens the GUI; subcommands run headless.

```powershell
afterclip run --input "C:\media\meeting.mp4" --output "$env:USERPROFILE\Output-Folder" `
    --model turbo --report-language tr --frames scene `
    --provider opencode_go --analyze-text --text-model glm-5.2 `
    --analyze-vision --vision-model deepseek-v4-flash-vision-exp `
    --json
```

| Command | Purpose |
| --- | --- |
| `run` | Process one media file |
| `batch` | Process several files sequentially |
| `status` | List past jobs (`--json`) |
| `mcp` | Run the MCP stdio server |

Common flags: `--model`, `--language`, `--report-language`, `--task`,
`--provider` (`ollama`/`gemini`/`openrouter`/`opencode_go`/`opencode_zen`),
`--text-model`, `--vision-model`, `--analyze-text`, `--analyze-vision`, `--frames`
(`none`/`interval`/`scene`/`both`), `--frame-interval`, `--scene-sensitivity`,
`--frame-resolution`, `--clip-start`, `--clip-end`, `--vtt`, `--segment`,
`--embed-frames`, `--no-filter`, `--preset`, `--output-name`,
`--reuse-transcription`, `--json`, `--quiet`.

- **Reusing a transcription**: `--reuse-transcription` (or `--reuse`) picks the
  latest job for the same input under `--output` whose transcription completed
  and reuses every completed step, so Whisper is skipped and only the missing
  steps (for example AI text analysis after a prompt/language change) re-run.
  It fails with exit code `2` when no cached transcription exists. Speaker
  labels from the job's `Voiceprints.json` are restored without reading the
  audio.
- **Exact job**: `--resume-dir PATH` (alias `--job-dir`) reuses one specific
  job folder, including an interrupted `running` job. Use it when two jobs
  share the same input and `--reuse-transcription` would pick the latest one.

  ```powershell
  afterclip run --input "F:\media\meeting.mp4" --output "F:\Output-Folder" `
      --reuse-transcription --report-language tr --provider ollama `
      --analyze-text --text-model qwen3.5-agent:latest --embed-frames
  ```

- **Report language**: `--report-language CODE` selects the language for every
  AI output (summary, highlights, vision and topics). Omitting it uses English;
  the Whisper/transcription language does not affect the report.
- **Presets**: `--preset NAME` applies the saved preset, then explicit flags
  override it. A `replace` preset applies its full prompt snapshot; a
  `legacy-partial` preset merges its overrides; `inherit` leaves the global
  prompts untouched. Omitting `--preset` uses the global prompt store.
- **JSON**: `--json` prints one machine-readable object with `status`,
  `job_dir`, `transcript_files`, `reports` and progress `events`.
- **Exit codes**: `0` success, `2` validation error, `3` processing failure,
  `130` cancelled. `Ctrl+C` cancels gracefully (kills FFmpeg/Whisper).

The CLI uses the exact same `TranscriptionService`, providers and settings as
the GUI, so outputs are identical for the same inputs (T43).

## MCP server

Install the optional SDK and run over stdio:

```powershell
pip install -e ".[mcp]"
afterclip mcp
```

Tools (thin wrappers over the same service):

| Tool | Returns |
| --- | --- |
| `transcribe_media` | Job directory, transcripts, reports |
| `fix_job` | Re-runs AI text/vision/topics for one existing job (synchronous) |
| `start_fix_job` | Starts `fix_job` in a detached process and returns immediately |
| `get_fix_status` | Detached process metadata plus the job's current state |
| `get_job_status` | Job status and step timings |
| `list_jobs` | Past jobs under the output directory |
| `read_report` | One whitelisted report file (`Topics.md`, `AI_Analysis.md`, …) |
| `list_presets` | Saved presets (metadata only) |

Long repairs should use `start_fix_job` and poll `get_fix_status`; an MCP tool
call must not be kept open for the tens of minutes a vision re-run can take.

Safety: the server is **local stdio only** (no network bind), tools can only
read/write under the workspace roots (`AFTERCLIP_HOME`, the default Input and
Output folders), `read_report` is limited to a whitelist of report files, no
tool returns secrets, and the shared cloud policy means video is never uploaded.
