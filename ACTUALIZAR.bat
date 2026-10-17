@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo        MusicFit - ACTUALIZADOR
echo ========================================
echo.

where git >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Git no esta instalado o no esta en PATH.
    echo Instala Git for Windows desde https://git-scm.com/download/win
    pause
    exit /b 1
)

where py >nul 2>nul
if errorlevel 1 (
    where python >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] Python no esta instalado o no esta en PATH.
        pause
        exit /b 1
    )
    set "PYTHON=python"
) else (
    set "PYTHON=py"
)

echo [1/3] Buscando la version mas reciente...
git fetch origin main
if errorlevel 1 goto :git_error

echo.
echo [2/3] Actualizando MusicFit...
git pull --ff-only origin main
if errorlevel 1 goto :git_error

echo.
echo [3/3] Verificando dependencias de Python...
%PYTHON% -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [AVISO] El codigo se actualizo, pero hubo un problema instalando dependencias.
    echo Puedes intentar manualmente: %PYTHON% -m pip install -r requirements.txt
    pause
    exit /b 1
)

echo.
echo ========================================
echo   MusicFit esta actualizado y listo.
echo ========================================
echo.
echo Puedes ejecutar ahora: ejecutar.bat
pause
exit /b 0

:git_error
echo.
echo [ERROR] No se pudo actualizar desde GitHub.
echo Si modificaste archivos del programa localmente, Git puede estar evitando sobrescribirlos.
echo Tus videos y canciones no deberian verse afectados porque estan ignorados por Git.
pause
exit /b 1
