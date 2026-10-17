@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "REPO=https://github.com/gaelnav1/MusicFit.git"

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

if not exist ".git\" goto :bootstrap

goto :update

:bootstrap
echo [1/4] Esta carpeta aun no esta conectada a GitHub.
echo       Conectando MusicFit por primera vez...
echo.

git init
if errorlevel 1 goto :git_error

git remote remove origin >nul 2>nul
git remote add origin "%REPO%"
if errorlevel 1 goto :git_error

git fetch origin main
if errorlevel 1 goto :git_error

rem Vincula el codigo local con main. Los archivos personales no rastreados
rem dentro de videos/canciones/resultados no se eliminan por un pull normal.
git checkout -B main origin/main --force
if errorlevel 1 goto :git_error

echo.
echo [2/4] Conexion inicial completada.
goto :deps

:update
echo [1/4] Buscando la version mas reciente...
git fetch origin main
if errorlevel 1 goto :git_error

echo.
echo [2/4] Actualizando MusicFit...
git pull --ff-only origin main
if errorlevel 1 goto :git_error

:deps
echo.
echo [3/4] Verificando dependencias de Python...
%PYTHON% -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [AVISO] El codigo se actualizo, pero hubo un problema instalando dependencias.
    echo Puedes intentar manualmente: %PYTHON% -m pip install -r requirements.txt
    pause
    exit /b 1
)

echo.
echo [4/4] Comprobando MusicFit...
%PYTHON% -m py_compile musicfit.py galeria.py thumbnails.py
if errorlevel 1 (
    echo [ERROR] La actualizacion bajo, pero Python detecto un error de sintaxis.
    pause
    exit /b 1
)

echo.
echo ========================================
echo   MusicFit esta actualizado y listo.
echo ========================================
echo.
echo Ejecuta ahora: ejecutar.bat
pause
exit /b 0

:git_error
echo.
echo [ERROR] No se pudo conectar o actualizar desde GitHub.
echo Revisa tu conexion a Internet y que Git funcione correctamente.
echo Si tienes cambios manuales en archivos del programa, guardalos antes de actualizar.
pause
exit /b 1
