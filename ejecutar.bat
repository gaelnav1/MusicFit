@echo off
chcp 65001 >nul
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
    set "PYTHON=python"
) else (
    set "PYTHON=py"
)

%PYTHON% selector_media.py %*
echo.
pause
