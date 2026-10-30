; AfterClip Inno Setup script.
;
; Compile after building the PyInstaller bundle:
;   powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1 -Clean -Zip -Installer
;
; The version is always supplied by the build script, which reads it from
; src/app/version.py -- the single source of truth. Compiling this file by hand
; requires passing both defines explicitly:
;   ISCC.exe /DAppVersion=0.3.0 /DAppVersionInfoVersion=0.3.0.0 packaging\afterclip.iss
;
; The source tree is the one-directory bundle produced by
; packaging\build_windows.ps1 (-Installer drives this automatically).
;
; FFmpeg/FFprobe and openai-whisper are external tools and are intentionally
; NOT bundled (licensing, CUDA/PyTorch size, antivirus concerns). The installer
; links to the setup docs instead.

#ifndef AppVersion
  #error AppVersion is not defined. Build via packaging\build_windows.ps1 -Installer, or pass /DAppVersion=<version>.
#endif

; Windows version resources need exactly four numeric components; a three-part
; AppVersion alone leaves Explorer's Details tab showing a blank FileVersion.
#ifndef AppVersionInfoVersion
  #error AppVersionInfoVersion is not defined. Build via packaging\build_windows.ps1 -Installer, or pass /DAppVersionInfoVersion=<x.x.x.x>.
#endif

#define AppName "AfterClip"
#define AppPublisher "AfterClip"
#define AppExeName "AfterClip.exe"
#define SourceDir "..\release\AfterClip"

[Setup]
; Stable application identity: must never change between releases.
AppId={{8E4C1F2A-3B6D-4F1E-9A2C-7D5B0E1F2A3B}
AppName={#AppName}
AppVersion={#AppVersion}
VersionInfoVersion={#AppVersionInfoVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\release
OutputBaseFilename=AfterClip-{#AppVersion}-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Allow per-user install without admin; let the user elevate for all users.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\{#AppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
