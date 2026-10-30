#Requires -Version 5.1
<#
.SYNOPSIS
    Builds the AfterClip Windows release bundle with PyInstaller.

.DESCRIPTION
    Installs the runtime + build dependencies (including the optional
    voiceprint extra), then produces a one-directory bundle under
    release\AfterClip\. The executable version resource is generated from
    app\version.py by the spec, so it always matches the package version. Use
    -Zip to also emit a distributable archive and -Installer to compile the
    Inno Setup installer (requires ISCC.exe), which receives the same version
    as a four-part VersionInfoVersion derived from app\version.py.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1 -Clean -Zip -Installer
#>
[CmdletBinding()]
param(
    [string]$Python = "python",
    [switch]$Clean,
    [switch]$Zip,
    [switch]$Installer
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$distPath = Join-Path $root "release"
$workPath = Join-Path $root "build\pyinstaller"

Push-Location $root
try {
    Write-Host "Installing runtime + build dependencies..."
    & $Python -m pip install --upgrade ".[build,voiceprint]"
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed ($LASTEXITCODE)." }

    $pyiArgs = @(
        "packaging\AfterClip.spec",
        "--noconfirm",
        "--distpath", $distPath,
        "--workpath", $workPath
    )
    if ($Clean) { $pyiArgs += "--clean" }

    Write-Host "Running PyInstaller..."
    & $Python -m PyInstaller @pyiArgs
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed ($LASTEXITCODE)." }

    $versionOutput = & $Python -c "import sys; sys.path.insert(0, 'src'); from app.version import __version__, version_info_version; print(__version__); print(version_info_version())"
    $version = $versionOutput[0].Trim()
    $versionInfoVersion = $versionOutput[1].Trim()
    $bundle = Join-Path $distPath "AfterClip"
    $exe = Join-Path $bundle "AfterClip.exe"
    if (-not (Test-Path -LiteralPath $exe)) { throw "Expected executable not found: $exe" }

    Write-Host "Built $exe (version $version)."

    if ($Zip) {
        $archive = Join-Path $distPath "AfterClip-$version-win64.zip"
        if (Test-Path -LiteralPath $archive) { Remove-Item -LiteralPath $archive -Force }
        Compress-Archive -Path (Join-Path $bundle "*") -DestinationPath $archive
        Write-Host "Packaged $archive."
    }

    if ($Installer) {
        $iscc = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
        if (-not $iscc) {
            $candidates = @(
                "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
                "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
            )
            $found = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
            if ($found) { $iscc = @{ Source = $found } }
        }
        if (-not $iscc) {
            throw "Inno Setup compiler (ISCC.exe) not found. Install Inno Setup 6 or add it to PATH."
        }
        Write-Host "Compiling installer with $($iscc.Source)..."
        & $iscc.Source "/DAppVersion=$version" "/DAppVersionInfoVersion=$versionInfoVersion" (Join-Path $root "packaging\afterclip.iss")
        if ($LASTEXITCODE -ne 0) { throw "ISCC failed ($LASTEXITCODE)." }
        $setup = Join-Path $distPath "AfterClip-$version-setup.exe"
        if (-not (Test-Path -LiteralPath $setup)) { throw "Expected installer not found: $setup" }
        Write-Host "Built $setup."
    }
}
finally {
    Pop-Location
}
