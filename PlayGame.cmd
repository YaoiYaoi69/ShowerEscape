@echo off
setlocal
cd /d "%~dp0"
if not exist ".runtime\python312\pythonw.exe" (
    echo Python fehlt. Bitte zuerst SetupGame.cmd ausfuehren.
    pause
    exit /b 1
)
start "" ".runtime\python312\pythonw.exe" game.py
