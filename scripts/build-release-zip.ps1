# Maintainer: build Dora-windows.zip for GitHub Releases (no venv, no downloaded models).
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$OutZip = Join-Path $Root "Dora-windows.zip"
$Stage = Join-Path $env:TEMP "dora-release-stage"

if (Test-Path $Stage) { Remove-Item $Stage -Recurse -Force }
New-Item -ItemType Directory -Path $Stage | Out-Null

$null = robocopy $Root $Stage /E /NFL /NDL /NJH /NJS /NC /NS /NP `
    /XD venv .git __pycache__ .pytest_cache .mypy_cache .ruff_cache dora_assistant.egg-info models `
    /XF Dora-windows.zip *.pyc *.pyo
if ($LASTEXITCODE -gt 7) { throw "robocopy failed: $LASTEXITCODE" }

if (Test-Path $OutZip) { Remove-Item $OutZip -Force }
Compress-Archive -Path (Join-Path $Stage "*") -DestinationPath $OutZip -Force
Remove-Item $Stage -Recurse -Force
Write-Host "Created: $OutZip" -ForegroundColor Green
