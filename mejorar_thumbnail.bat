@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo     MusicFit - THUMBNAIL IMPROVER
echo ========================================
echo.

if "%~1"=="" (
    echo Arrastra una imagen encima de este archivo .bat
    echo o ejecuta:
    echo   mejorar_thumbnail.bat ruta\imagen.png
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

%PYTHON% thumbnail_improver.py "%~1"
if errorlevel 1 (
    echo.
    echo [ERROR] No se pudieron generar las variantes.
    pause
    exit /b 1
)

echo.
echo Revisa la carpeta: thumbnails_mejorados
pause
