@echo off
title Dora Installer
cd /d "%~dp0"
echo.
echo  Dora Installer - this will download everything needed and set up shortcuts.
echo  You may be asked to allow Python or the microphone later.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
if errorlevel 1 (
    echo.
    echo  Installation failed. See messages above.
    pause
    exit /b 1
)
echo.
pause
