# Run from the Dora project folder:  .\update_dora.ps1
# Updates the editable pip install and re-runs --install-startup (refreshes launcher paths).

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Updating Dora (pip install -e . --upgrade)..." -ForegroundColor Cyan
$py = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
if (Test-Path $py) {
    & $py -m pip install -e . --upgrade
} else {
    py -3 -m pip install -e . --upgrade
}

Write-Host "`nRe-registering Windows sign-in shortcut..." -ForegroundColor Cyan
if (Test-Path $py) {
    & $py -m core.cli --install-startup
} else {
    py -3 -m core.cli --install-startup
}

Write-Host "`nDone. Restart Dora or sign out/in to load the new build." -ForegroundColor Green
