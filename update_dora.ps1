# Sync project code into the installed copy, upgrade packages, migrate config.
# Run from the git/project folder:  .\update_dora.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$InstallRoot = Join-Path $env:LOCALAPPDATA "Dora"
$AppDir = Join-Path $InstallRoot "app"
$InstalledPython = Join-Path $AppDir "venv\Scripts\python.exe"
$DevPython = Join-Path $PSScriptRoot "venv\Scripts\python.exe"

function Sync-ToInstalledCopy {
    if (-not (Test-Path (Join-Path $AppDir "config.json"))) {
        Write-Host "No installed copy at $AppDir - updating this folder only." -ForegroundColor Yellow
        return $false
    }
    Write-Host "Syncing code to installed copy: $AppDir" -ForegroundColor Cyan
    $null = robocopy $PSScriptRoot $AppDir /E /NFL /NDL /NJH /NJS /NC /NS /NP `
        /XD venv .git __pycache__ .pytest_cache .mypy_cache .ruff_cache dora_assistant.egg-info models tools `
        /XF *.pyc *.pyo Dora-windows.zip config.json permissions.json
    if ($LASTEXITCODE -gt 7) {
        throw "robocopy failed (exit $LASTEXITCODE)"
    }
    return $true
}

function Install-Packages($PythonExe, $AppPath) {
    Write-Host "pip install -e $AppPath" -ForegroundColor Cyan
    & $PythonExe -m pip install --upgrade pip wheel
    & $PythonExe -m pip install -e $AppPath --upgrade
}

function Migrate-InstalledConfig($PythonExe) {
    $cfg = Join-Path $AppDir "config.json"
    Write-Host "Migrating config: $cfg" -ForegroundColor Cyan
    $env:DORA_HOME = $AppDir
    Push-Location $AppDir
    try {
        & $PythonExe scripts\migrate_config.py
    } finally {
        Pop-Location
    }
}

$synced = Sync-ToInstalledCopy

if ($synced -and (Test-Path $InstalledPython)) {
    Install-Packages $InstalledPython $AppDir
    Migrate-InstalledConfig $InstalledPython
    Write-Host ""
    Write-Host "Re-registering Windows sign-in shortcut..." -ForegroundColor Cyan
    Push-Location $AppDir
    try {
        & $InstalledPython -m core.cli --install-startup
    } finally {
        Pop-Location
    }
} elseif (Test-Path $DevPython) {
    Install-Packages $DevPython $PSScriptRoot
    & $DevPython -m core.cli --install-startup
} else {
    py -3 -m pip install -e $PSScriptRoot --upgrade
}

Write-Host ""
Write-Host "Done." -ForegroundColor Green
Write-Host "Restart Dora (Desktop shortcut). Startup should show:" -ForegroundColor Green
Write-Host "  Speech recognition: faster-whisper (small.en)" -ForegroundColor Green
Write-Host ""
Write-Host "If you still see Vosk, edit:" -ForegroundColor Green
Write-Host "  $AppDir\config.json" -ForegroundColor Green
Write-Host "  set stt_engine to whisper in that file, then restart." -ForegroundColor Green
