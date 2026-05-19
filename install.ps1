#Requires -Version 5.1
<#
.SYNOPSIS
  Installs Dora on Windows (no git clone required).

.DESCRIPTION
  Copies Dora to %LOCALAPPDATA%\Dora\app, creates a venv, installs Python deps,
  downloads the Vosk speech model, installs/pulls Ollama + AI model, sets DORA_HOME,
  and creates Desktop + Start Menu shortcuts.

.PARAMETER AddToStartup
  Also register Dora to start at Windows sign-in (background).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File install.ps1
  powershell -ExecutionPolicy Bypass -File install.ps1 -AddToStartup
#>
param(
    [switch]$AddToStartup
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) {
    Write-Host "`n==> $msg" -ForegroundColor Cyan
}

function Find-PythonExe {
    $candidates = @(
        @{ Exe = "py"; Args = @("-3.12") },
        @{ Exe = "py"; Args = @("-3.11") },
        @{ Exe = "py"; Args = @("-3.10") },
        @{ Exe = "py"; Args = @("-3") },
        @{ Exe = "python"; Args = @() }
    )
    foreach ($c in $candidates) {
        try {
            $pyArgs = $c.Args + @(
                "-c",
                "import sys; print(str(sys.version_info.major) + '.' + str(sys.version_info.minor))"
            )
            $ver = & $c.Exe @pyArgs 2>$null
            if ($LASTEXITCODE -ne 0 -or -not $ver) { continue }
            $parts = $ver.Trim().Split(".")
            $maj = [int]$parts[0]
            $min = [int]$parts[1]
            if ($maj -gt 3 -or ($maj -eq 3 -and $min -ge 10)) {
                return @{ Launcher = $c.Exe; VersionArgs = $c.Args }
            }
        } catch {
            continue
        }
    }
    return $null
}

function Invoke-Python($py, [string[]]$PythonArgs) {
    $all = @()
    if ($py.VersionArgs) { $all += $py.VersionArgs }
    $all += $PythonArgs
    & $py.Launcher @all
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed (exit $LASTEXITCODE): $($py.Launcher) $($all -join ' ')"
    }
}

function Set-UserEnv([string]$Name, [string]$Value) {
    [Environment]::SetEnvironmentVariable($Name, $Value, "User")
    Set-Item -Path "Env:$Name" -Value $Value
}

function New-Shortcut($TargetPath, $Arguments, $WorkingDirectory, $ShortcutPath, $Description) {
    $shell = New-Object -ComObject WScript.Shell
    $sc = $shell.CreateShortcut($ShortcutPath)
    $sc.TargetPath = $TargetPath
    if ($Arguments) { $sc.Arguments = $Arguments }
    $sc.WorkingDirectory = $WorkingDirectory
    $sc.Description = $Description
    $sc.Save()
}

$SourceDir = $PSScriptRoot
if (-not (Test-Path (Join-Path $SourceDir "config.json"))) {
    Write-Host "ERROR: Run this installer from the Dora folder (config.json not found)." -ForegroundColor Red
    exit 1
}

$InstallRoot = Join-Path $env:LOCALAPPDATA "Dora"
$AppDir = Join-Path $InstallRoot "app"
$LauncherDir = $InstallRoot

Write-Host @"

  Dora — Windows voice assistant installer
  ----------------------------------------
"@ -ForegroundColor Green

Write-Step "Installing to $AppDir"

New-Item -ItemType Directory -Force -Path $AppDir | Out-Null

$excludeDirs = @("venv", ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "egg-info")
$excludeNames = @("*.pyc", "*.pyo", "dora_assistant.egg-info")

# robocopy returns 0-7 for success
$robolog = Join-Path $env:TEMP "dora-install-robocopy.log"
$null = robocopy $SourceDir $AppDir /E /NFL /NDL /NJH /NJS /NC /NS /NP `
    /XD venv .git __pycache__ .pytest_cache .mypy_cache .ruff_cache dora_assistant.egg-info models `
    /XF *.pyc *.pyo
if ($LASTEXITCODE -gt 7) {
    throw "Failed to copy files to $AppDir (robocopy exit $LASTEXITCODE). See $robolog"
}

Write-Step "Checking Python 3.10+"
$py = Find-PythonExe
if (-not $py) {
    Write-Host "Python 3.10+ not found. Trying winget…" -ForegroundColor Yellow
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
            [System.Environment]::GetEnvironmentVariable("Path", "User")
        $py = Find-PythonExe
    }
}
if (-not $py) {
    Write-Host @"
ERROR: Python 3.10 or newer is required.
Install from https://www.python.org/downloads/ (check 'Add Python to PATH'), then run this installer again.
"@ -ForegroundColor Red
    exit 1
}
Write-Host "  Using: $($py.Launcher) $($py.VersionArgs -join ' ')" -ForegroundColor Gray

Write-Step "Creating virtual environment"
$venvPython = Join-Path $AppDir "venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Invoke-Python $py @("-m", "venv", (Join-Path $AppDir "venv"))
}

$venvPy = @{ Launcher = $venvPython; VersionArgs = @() }

Write-Step "Installing Dora (Python packages)"
Invoke-Python $venvPy @("-m", "pip", "install", "--upgrade", "pip", "wheel")
Invoke-Python $venvPy @("-m", "pip", "install", (Join-Path $AppDir "."))

Write-Step "Downloading speech model and AI (may take several minutes)"
Invoke-Python $venvPy @((Join-Path $AppDir "scripts\first_run_setup.py"))

Write-Step "Setting DORA_HOME"
Set-UserEnv "DORA_HOME" $AppDir

Write-Step "Creating shortcuts"
$DoraExe = Join-Path $AppDir "venv\Scripts\dora.exe"
$BackgroundExe = Join-Path $AppDir "venv\Scripts\dora-background.exe"

$launchBat = Join-Path $LauncherDir "Start Dora.bat"
@"
@echo off
set "DORA_HOME=$AppDir"
cd /d "$AppDir"
"$DoraExe"
pause
"@ | Set-Content -Path $launchBat -Encoding ASCII

$desktop = [Environment]::GetFolderPath("Desktop")
$startMenu = Join-Path ([Environment]::GetFolderPath("Programs")) "Dora"
New-Item -ItemType Directory -Force -Path $startMenu | Out-Null

New-Shortcut -TargetPath $DoraExe -Arguments "" -WorkingDirectory $AppDir `
    -ShortcutPath (Join-Path $desktop "Dora.lnk") -Description "Dora voice assistant"
New-Shortcut -TargetPath $launchBat -Arguments "" -WorkingDirectory $LauncherDir `
    -ShortcutPath (Join-Path $startMenu "Dora.lnk") -Description "Dora voice assistant"
New-Shortcut -TargetPath (Join-Path $AppDir "venv\Scripts\dora-background.exe") -Arguments "" `
    -WorkingDirectory $AppDir -ShortcutPath (Join-Path $startMenu "Dora (background).lnk") `
    -Description "Dora voice assistant (no window)"

if ($AddToStartup) {
    Write-Step "Registering sign-in startup"
    $env:DORA_HOME = $AppDir
    Push-Location $AppDir
    try {
        & $DoraExe --install-startup
    } finally {
        Pop-Location
    }
}

Write-Host @"

  Installation complete!
  ----------------------
  Install folder:  $AppDir
  DORA_HOME:         $AppDir
  Desktop shortcut:  Dora
  Logs:              $InstallRoot\dora.log (after first run)

  Double-click "Dora" on your desktop, or run:
    $launchBat

  Say "Dora" or "hey Dora" when you hear the ready message.

"@ -ForegroundColor Green
