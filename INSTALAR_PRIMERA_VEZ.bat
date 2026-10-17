@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo     MusicFit - INSTALACION INICIAL
echo ========================================
echo.

where git >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Git no esta instalado o no esta en PATH.
    echo Instala Git for Windows desde https://git-scm.com/download/win
    pause
    exit /b 1
)

if not exist .git (
    echo [1/5] Inicializando Git en esta carpeta...
    git init
    if errorlevel 1 goto :git_error

    echo [2/5] Conectando con GitHub...
    git remote remove origin >nul 2>nul
    git remote add origin https://github.com/gaelnav1/MusicFit.git
    if errorlevel 1 goto :git_error

    echo [3/5] Descargando la version oficial...
    git fetch origin main
    if errorlevel 1 goto :git_error

    echo [4/5] Sincronizando archivos del programa...
    git checkout -B main origin/main
    if errorlevel 1 goto :git_error
) else (
    echo [1/5] Git ya estaba configurado.
    echo [2/5] Descargando cambios...
    git fetch origin main
    if errorlevel 1 goto :git_error
    echo [3/5] Actualizando...
    git reset --hard origin/main
    if errorlevel 1 goto :git_error
    echo [4/5] Sincronizacion lista.
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

echo [5/5] Instalando/verificando dependencias...
%PYTHON% -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [AVISO] El codigo quedo instalado, pero fallo alguna dependencia.
    echo Prueba manualmente: %PYTHON% -m pip install -r requirements.txt
    pause
    exit /b 1
)

echo.
echo ========================================
echo   MusicFit quedo conectado a GitHub.
echo ========================================
echo.
echo A partir de ahora usa ACTUALIZAR.bat para traer mis cambios.
echo Para probar el programa usa ejecutar.bat
pause
exit /b 0

:git_error
echo.
echo [ERROR] No se pudo completar la instalacion/sincronizacion con GitHub.
pause
exit /b 1
