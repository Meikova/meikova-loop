@echo off
cd /d "%~dp0"
echo [1/3] Kiem tra PyInstaller trong .venv...
if not exist ".venv\Scripts\pyinstaller.exe" (
    echo Cai dat PyInstaller...
    ".venv\Scripts\python.exe" -m pip install pyinstaller
)

echo [2/3] Build MashLoop Desktop Executable...
".venv\Scripts\pyinstaller.exe" --noconfirm mashloop.spec

echo [3/3] Hoan tat! File chay nam tai: dist\MashLoop\MashLoop.exe
pause
