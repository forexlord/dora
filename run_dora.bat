@echo off
set "DORA_HOME=%~dp0"
if "%DORA_HOME:~-1%"=="\" set "DORA_HOME=%DORA_HOME:~0,-1%"
cd /d "%DORA_HOME%"

rem Prefer project venv so deps (e.g. rich) match pip install -e .
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" -m core.cli
    goto :eof
)
if exist "venv\Scripts\dora.exe" (
    "venv\Scripts\dora.exe"
    goto :eof
)

where dora >nul 2>&1 && dora && goto :eof
py -3 -m core.cli 2>nul && goto :eof
python -m core.cli 2>nul && goto :eof

echo Create venv and install deps once:
echo   py -3 -m venv venv
echo   venv\Scripts\python.exe -m pip install -e .
echo Then double-click this file ^(uses venv automatically^) or run:
echo   venv\Scripts\dora
echo.
echo To start Dora at sign-in ^(hidden, no terminal^):
echo   dora --install-startup
echo Remove from sign-in:
echo   dora --uninstall-startup
pause
