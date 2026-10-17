@echo off
chcp 65001 >nul
cd /d "%~dp0"
python musicfit.py %*
echo.
pause
