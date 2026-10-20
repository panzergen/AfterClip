# Security Policy

## Supported versions

| Version | Supported |
| --- | --- |
| 0.3.x | ✅ |

AfterClip is pre-1.0. Security fixes land on `main` and in the next release;
there is no long-term support branch.

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Report it privately through GitHub's **Report a vulnerability** button on the
repository's Security tab (`Security → Report a vulnerability`). That creates a
private advisory visible only to the maintainers.

If that option is unavailable, open a regular issue that says only *"Security
report — please open a private channel"* with no technical detail, and a
maintainer will follow up.

Please include:

- Affected version and platform
- Steps to reproduce, or a proof of concept
- The impact you believe it has
- Any suggested mitigation

### What to expect

- **Acknowledgement** within 7 days
- **Initial assessment** within 30 days, including whether we consider it a
  vulnerability and whether a fix is planned
- **Fix and disclosure** coordinated with you. We aim to publish a fix within
  90 days of the initial report, and we credit reporters in the release notes
  unless you prefer otherwise.

Please give us a reasonable amount of time to release a fix before disclosing
the issue publicly.

## Scope

In scope:

- The code in this repository
- The packaged Windows application built from it
- The published release artifacts (zip and installer)

Out of scope:

- Vulnerabilities in third-party dependencies with no AfterClip-specific
  exploitation path — report those upstream, though please tell us so we can
  update
- Vulnerabilities in FFmpeg, `openai-whisper`, PySide6 or the operating system
- Findings that require an attacker to already have administrative access to
  the machine
- Denial of service through extremely large media files that the user themself
  selected
- Cloud provider API behaviour (report to the provider)

## Security-relevant design notes

AfterClip handles user media and, optionally, cloud API keys. The design
decisions below are deliberate — please do not weaken them in a pull request.

### API keys never touch disk

Cloud provider keys are stored in the **OS credential manager** through the
`keyring` library (Windows Credential Manager, macOS Keychain, Linux Secret
Service). They are never written to `settings.json` or any other file.

Every registered secret is added to a redaction filter
(`app/infrastructure/logging_filter.py`) that scrubs it from log messages *and*
tracebacks, so keys cannot leak through stack traces.

### Cloud uploads are policy-constrained

All cloud providers route through `app/infrastructure/cloud_policy.py`. It
refuses video uploads outright — only text and single still frames are ever
transmitted. This is enforced at the adapter layer, not in the UI, so it holds
for the CLI and MCP server too.

### Consent is explicit and revocable

A cloud job does not start until consent is granted for that provider, naming
the provider and model and describing what leaves the machine. Consent is
revocable in Settings, and revoking it re-prompts on the next job.

### Local-first by default

Transcription runs locally through FFmpeg and `openai-whisper`. Ollama is a
fully local AI provider. Nothing is sent anywhere unless the user selects a
cloud provider and grants consent.

### Report and media files

Transcripts, reports, frames and extracted audio are written to the output
directory the user chose. They are **not** encrypted at rest — treat them like
any other file on your disk.

Voiceprint enrollment writes **biometric speaker embeddings** to
`Voiceprints.json` inside the job output folder. These are derived from
voice audio and are sensitive: do not share an output folder that contains
them without saying so. See [docs/PRIVACY.md](docs/PRIVACY.md).

## Hardening the build

The Windows artifacts are **not code-signed**. Users will see SmartScreen and
antivirus warnings when running `AfterClip.exe` or the installer. Verify
downloads against the `SHA256SUMS` file published with each release.
