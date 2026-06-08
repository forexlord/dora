@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update_dora.ps1"
if errorlevel 1 (
    echo Update failed.
    pause
    exit /b 1
)
pause
