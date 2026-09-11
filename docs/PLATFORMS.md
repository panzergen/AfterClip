# Platform Support

AfterClip is Windows-first. Phase 3 adds the seams that let the same code run
on macOS and Linux; those platforms are usable from source but are not yet
release-quality.

| Area | Windows | macOS | Linux |
| --- | --- | --- | --- |
| Runtime | Primary, release target | Experimental (source) | Experimental (source) |
| Packaging | PyInstaller onedir (`packaging/`) | Not started | Not started |
| Installer | Inno Setup (planned) | `.app`/`.dmg` (planned) | AppImage/`.deb` (planned) |
| Secret storage | Credential Manager | Keychain | Secret Service / KWallet |
| Data dir | `%LOCALAPPDATA%\AfterClip` | `~/Library/Application Support/AfterClip` | `$XDG_DATA_HOME/AfterClip` or `~/.local/share/AfterClip` |
| Workspace (Input/Output) | `%USERPROFILE%\AfterClip` (frozen) | `~/AfterClip` (frozen) | `~/AfterClip` (frozen) |
| External tools | FFmpeg/FFprobe/Whisper on `PATH` | same | same |
| Fatal-crash report | `crash.log` via faulthandler | same | same |
| Recording (system audio) | WASAPI (auto-disabled when absent) | Not implemented | Not implemented |

`AFTERCLIP_HOME` overrides the workspace directory on every platform.

## Path resolution

`app/app_paths.py` picks the per-user data directory with `sys.platform`:

- **Windows:** `%LOCALAPPDATA%\AfterClip`
- **macOS:** `~/Library/Application Support/AfterClip`
- **Linux/other posix:** `$XDG_DATA_HOME/AfterClip`, falling back to
  `~/.local/share/AfterClip`

Settings, logs and the crash report all live under this directory. Frozen
builds additionally place the Input/Output workspace at `~/AfterClip` (or
`AFTERCLIP_HOME`) because there is no repository beside the executable.

## Secret storage

`infrastructure/secrets.py::KeyringSecretStore` wraps `keyring`, which selects
the native backend:

- **Windows:** Credential Manager (`keyring.backends.Windows`)
- **macOS:** Keychain (`keyring.backends.macOS`)
- **Linux:** Secret Service or KWallet (`keyring.backends.SecretService`)

When no backend is available (for example a headless Linux session), `get`
degrades to `None` and `set`/`delete` raise a clear `SecretStoreUnavailable`
error, which the Settings screen surfaces instead of crashing. Secrets are
registered with the log redaction filter and never written to disk in
plaintext.

## Settings schema

`settings.json` carries a `version` field. `infrastructure/settings.py` reads
legacy (unversioned) files as v0 and migrates them in memory, persisting the
upgrade on the next write or when `SettingsController` calls `migrate()`.
A settings file written by a *newer* app version is rejected rather than
clobbered.

## Known gaps

- macOS/Linux have no packaging, installer or release smoke coverage yet.
- Linux system-audio capture and macOS screen/audio capture are unimplemented.
- Code signing/notarization is not configured on any platform.
