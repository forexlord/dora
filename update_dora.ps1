# Sync project code into the installed copy, upgrade packages, migrate config.
# Run from the git/project folder:  .\update_dora.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$InstallRoot = Join-Path $env:LOCALAPPDATA "Dora"
$AppDir = Join-Path $InstallRoot "app"
$InstalledPython = Join-Path $AppDir "venv\Scripts\python.exe"
$InstalledPythonw = Join-Path $AppDir "venv\Scripts\pythonw.exe"
$DevPython = Join-Path $PSScriptRoot "venv\Scripts\python.exe"

function Stop-DoraProcesses {
    param([string]$AppPath)
    $stopped = $false
    $names = @("dora-background", "dora")
    foreach ($name in $names) {
        $procs = Get-Process -Name $name -ErrorAction SilentlyContinue
        if ($procs) {
            $stopped = $true
            Write-Host "Stopping $name..." -ForegroundColor Yellow
            $procs | Stop-Process -Force -ErrorAction SilentlyContinue
        }
    }
    $venvScripts = Join-Path $AppPath "venv\Scripts"
    $escapedApp = [regex]::Escape($AppPath)
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $exe = $_.ExecutablePath
        $cmd = $_.CommandLine
        if (-not $exe) { return $false }
        if ($exe -like "$venvScripts\python.exe" -or $exe -like "$venvScripts\pythonw.exe") {
            return $true
        }
        if ($cmd -and $cmd -match $escapedApp -and $cmd -match "core\.cli") {
            return $true
        }
        return $false
    } | ForEach-Object {
        $stopped = $true
        Write-Host "Stopping PID $($_.ProcessId) ($($_.Name))..." -ForegroundColor Yellow
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
    if ($stopped) {
        Start-Sleep -Seconds 2
        Write-Host "Dora stopped." -ForegroundColor Green
    } else {
        Write-Host "No running Dora process found." -ForegroundColor DarkGray
    }
}

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
    if ($LASTEXITCODE -ne 0) {
        throw "pip install failed (exit $LASTEXITCODE). Quit Dora and run update again."
    }
}

function Migrate-InstalledConfig($PythonExe) {
    $cfg = Join-Path $AppDir "config.json"
    Write-Host "Migrating config: $cfg" -ForegroundColor Cyan
    $env:DORA_HOME = $AppDir
    $pyCode = @"
import sys
sys.path.insert(0, r'$AppDir')
from core.config import load_dora_config
cfg = load_dora_config(r'$cfg', persist_migrations=True)
print('Config migration complete.')
print(f'  stt_engine={cfg.stt_engine!r}')
print(f'  whisper_model={cfg.whisper_model!r}')
print(f'  config_schema_version={cfg.config_schema_version}')
"@
    & $PythonExe -c $pyCode
    if ($LASTEXITCODE -ne 0) {
        throw "Config migration failed (exit $LASTEXITCODE)."
    }
}

$synced = Sync-ToInstalledCopy

if ($synced -and (Test-Path $InstalledPython)) {
    Write-Host ""
    Write-Host "Stopping Dora before upgrade (required to replace running files)..." -ForegroundColor Cyan
    Stop-DoraProcesses -AppPath $AppDir
    Install-Packages $InstalledPython $AppDir
    Migrate-InstalledConfig $InstalledPython
    Write-Host ""
    Write-Host "Re-registering Windows sign-in shortcut..." -ForegroundColor Cyan
    $env:DORA_HOME = $AppDir
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
Write-Host "Start Dora again from the Desktop shortcut or sign-in startup." -ForegroundColor Green
Write-Host "Startup should show: Speech recognition: faster-whisper (small.en)" -ForegroundColor Green
Write-Host ""
Write-Host "Wake phrase: hey Dora (see $AppDir\config.json)" -ForegroundColor Green
