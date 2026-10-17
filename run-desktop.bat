@echo off
cd /d "%~dp0"
set PYTHONWARNINGS=ignore

if not exist ".venv\Scripts\pythonw.exe" (
    echo Virtual environment .venv not found.
    pause
    exit /b 1
)

start "" ".venv\Scripts\pythonw.exe" -m loopbox.desktop %*
