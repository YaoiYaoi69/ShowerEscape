@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0SetupGame.ps1"
if errorlevel 1 (
    echo.
    echo Setup fehlgeschlagen. Die Fehlermeldung steht oben.
    pause
    exit /b 1
)
echo.
echo Fertig! Starte PlayGame.cmd zum Spielen.
pause
