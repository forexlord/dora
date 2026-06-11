# Maintainer: build Dora-windows.zip for GitHub Releases (no venv, no downloaded models).
$ErrorActionPreference = "Stop"
$Root = (Split-Path $PSScriptRoot -Parent).TrimEnd('\')
$OutZip = Join-Path $Root "Dora-windows.zip"
$Stage = Join-Path $Root ".release-stage"

if (Test-Path $Stage) { Remove-Item $Stage -Recurse -Force }
New-Item -ItemType Directory -Path $Stage | Out-Null

try {
    # robocopy logs progress to stderr; do not treat that as a terminating error (CI uses pwsh).
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & robocopy $Root $Stage /E /NFL /NDL /NJH /NJS /NC /NS /NP `
        /XD venv .git .release-stage __pycache__ .pytest_cache .mypy_cache .ruff_cache `
        dora_assistant.egg-info models tools `
        /XF Dora-windows.zip *.pyc *.pyo 2>&1 | Out-Null
    $robocopyExit = $LASTEXITCODE
    $ErrorActionPreference = $prevEap
    if ($robocopyExit -gt 7) {
        throw "robocopy failed (exit $robocopyExit)"
    }

    $staged = Get-ChildItem -Path $Stage -Force
    if (-not $staged) {
        throw "Release stage is empty: $Stage"
    }

    if (Test-Path $OutZip) { Remove-Item $OutZip -Force }
    Push-Location $Stage
    try {
        Compress-Archive -Path * -DestinationPath $OutZip -Force
    } finally {
        Pop-Location
    }

    if (-not (Test-Path $OutZip)) {
        throw "Zip was not created: $OutZip"
    }
    Write-Host "Created: $OutZip ($((Get-Item $OutZip).Length) bytes)" -ForegroundColor Green
} finally {
    if (Test-Path $Stage) { Remove-Item $Stage -Recurse -Force -ErrorAction SilentlyContinue }
}
