@echo off
setlocal
cd /d "%~dp0"

echo Updating Dora (editable install + refresh startup launcher)...
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" -m pip install -e . --upgrade
) else (
    py -3 -m pip install -e . --upgrade 2>nul || python -m pip install -e . --upgrade
)

echo.
echo Re-registering Windows sign-in shortcut (updates paths if Python/venv moved)...
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" -m core.cli --install-startup
) else (
    py -3 -m core.cli --install-startup
)

echo.
echo Done. Restart Dora or sign out and back in to use the new build.
pause
