#Requires -Version 5.1
<#
.SYNOPSIS
    Builds the AfterClip Windows release bundle with PyInstaller.

.DESCRIPTION
    Installs the runtime + build dependencies, then produces a one-directory
    bundle under release\AfterClip\. The executable version resource is
    generated from app\version.py by the spec, so it always matches the
    package version. Use -Zip to also emit a distributable archive.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1 -Clean -Zip
#>
[CmdletBinding()]
param(
    [string]$Python = "python",
    [switch]$Clean,
    [switch]$Zip
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$distPath = Join-Path $root "release"
$workPath = Join-Path $root "build\pyinstaller"

Push-Location $root
try {
    Write-Host "Installing runtime + build dependencies..."
    & $Python -m pip install --upgrade ".[build]"
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

    $version = (& $Python -c "import sys; sys.path.insert(0, 'src'); from app.version import __version__; print(__version__)").Trim()
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
}
finally {
    Pop-Location
}
