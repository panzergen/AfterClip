# Contributing to AfterClip

Thanks for your interest in improving AfterClip. This document explains how to
set up a development environment, the conventions the project follows, and what
a good pull request looks like.

## Code of conduct

Participation in this project is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
By taking part you are expected to uphold it.

## Reporting bugs

Open an issue using the **Bug report** template
(`.github/ISSUE_TEMPLATE/bug_report.yml`). Please include:

- The AfterClip version (`Help → About`, or the `version` shown in the log header)
- Your operating system and Python version
- The steps that reproduce the problem
- What you expected and what happened instead
- The relevant part of `<data dir>/logs/app.log`

**Never paste API keys into an issue.** AfterClip stores cloud provider keys in
the OS credential manager and redacts them from logs, but a key that reaches an
issue is compromised — rotate it.

## Development setup

AfterClip requires **Python 3.12 or newer**.

```powershell
git clone https://github.com/panzergen/AfterClip.git
cd AfterClip
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

External tools are needed for the actual transcription work but not for the test
suite:

- [FFmpeg](https://ffmpeg.org/download.html) — must be on `PATH` (`ffmpeg` and `ffprobe`)
- `openai-whisper` — `pip install openai-whisper`

## Running the tests

```powershell
python -m pytest -q                    # unit and regression suite
python -m pytest -m ui -q              # Qt UI tests
$env:QT_QPA_PLATFORM="offscreen"       # required for UI tests on a headless machine
python -m pytest --cov=app             # coverage report
```

The `ui` marker is deselected by default so the fast suite does not need a
display.

The default run does **not** need Qt's GUI libraries: `tests/ui` is excluded
from collection entirely unless you ask for it with `-m ui`. That keeps
`pytest` working on a machine without a GPU stack.

On **Linux**, the UI tests additionally need Qt's system libraries, because
`QtGui`/`QtQml` link against `libEGL`:

```bash
sudo apt-get install -y libegl1 libgl1 libxkbcommon-x11-0 libdbus-1-3 libfontconfig1
```

Without them, `pytest -m ui` reports a clear message and skips the UI tests
rather than failing collection. The CI workflow installs the full set
automatically.

## Linting and formatting

The project uses [ruff](https://docs.astral.sh/ruff/):

```powershell
python -m ruff check src tests packaging
python -m ruff format --check src tests packaging
```

Both must pass before a pull request is merged — CI enforces exactly these two
commands. If you change formatting, run `python -m ruff format src tests packaging`
to apply it.

## Project layout

The code follows a ports-and-adapters layout:

| Package | Responsibility |
| --- | --- |
| `app/domain/` | Plain data and rules. No I/O, no framework imports. |
| `app/application/` | Use cases and orchestration. Depends on ports, never on a concrete adapter. |
| `app/infrastructure/` | Adapters: FFmpeg, Whisper, HTTP clients, keyring, file stores. |
| `app/ui/` | PySide6 controllers (testable) and QML views. |
| `app/cli.py`, `app/mcp_server.py` | Headless entry points. |

New behaviour belongs in `app/application/` behind a port in
`app/application/ports/`, with the concrete adapter in `app/infrastructure/`.
That is what keeps the provider, media tool and secret backends swappable and
the test suite fast.

## Conventions

- **Type hints** on public functions and dataclasses.
- **Docstrings** explain *why*, not *what* — the code already says what.
- **Tests accompany behaviour changes.** A bug fix gets a regression test that
  fails without the fix.
- **No secrets in the repository.** Use the keyring-backed secret store.
- Keep lines under 100 characters (ruff enforces this).

## Pull requests

1. Fork the repository and create a branch from `main`.
2. Make your change with tests.
3. Make sure `python -m pytest -q`, `python -m pytest -m ui -q` and both ruff
   commands pass locally.
4. Fill in the pull request template, and describe user-visible behaviour
   changes in `docs/`.
5. Open the pull request against `main`.

Maintainers may ask for changes or split the work up. Small, focused pull
requests are much easier to review than large ones.

## Adding a cloud provider

Providers are registered in `app/application/provider_registry.py`. A new
provider needs:

1. A `ProviderSpec` entry (id, label, endpoint, credential name, kind).
2. An adapter — usually `openai_compat` if the provider speaks
   `/chat/completions`.
3. Tests in `tests/application/test_provider_registry.py` and the adapter's
   test module.
4. Documentation in `docs/PROVIDERS.md`, and an entry in `docs/PRIVACY.md` if
   any data leaves the machine.

All providers must route through `app/infrastructure/cloud_policy.py`, which
refuses video uploads.

## Reporting security issues

Please do **not** open a public issue for a security problem. See
[SECURITY.md](SECURITY.md) for the private reporting channel.

## License

By contributing you agree that your contributions are licensed under the
[MIT License](LICENSE).
