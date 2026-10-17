@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo   MusicFit - GENERAR VARIANTES VIDEO
echo ========================================
echo.

if "%~1"=="" (
    echo Arrastra un video encima de este archivo .bat
    echo o ejecuta:
    echo   generar_variantes_video.bat ruta\video.mp4
    echo.
    pause
    exit /b 1
)

where py >nul 2>nul
if errorlevel 1 (
    set "PYTHON=python"
) else (
    set "PYTHON=py"
)

where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo [ERROR] ffmpeg no esta instalado o no esta en PATH.
    pause
    exit /b 1
)

where ffprobe >nul 2>nul
if errorlevel 1 (
    echo [ERROR] ffprobe no esta instalado o no esta en PATH.
    pause
    exit /b 1
)

echo Video: %~1
echo.
set /p VARIANTS=Cuantas variantes quieres generar? [4]: 
if "%VARIANTS%"=="" set "VARIANTS=4"

echo.
echo Generando %VARIANTS% variantes...
%PYTHON% slightly_change.py "%~1" --variants %VARIANTS%
if errorlevel 1 (
    echo.
    echo [ERROR] No se pudieron generar las variantes.
    pause
    exit /b 1
)

echo.
echo ========================================
echo             TERMINADO
echo ========================================
echo Revisa la carpeta: variantes
pause
