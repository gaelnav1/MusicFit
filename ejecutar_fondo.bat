@echo off
chcp 65001 >nul
cd /d "%~dp0"
python musicfit.py --musica-fondo %*
echo.
pause
