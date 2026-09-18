@echo off
REM ============================================================
REM  Corre el backend FastAPI (backend.main:app) localmente.
REM  Portable: anda en cualquier PC del equipo sin preparar nada:
REM    1) busca Python (py launcher o python del PATH);
REM    2) crea/usa un venv POR MAQUINA en %%LOCALAPPDATA%%\venvs\bonos
REM       (fuera de OneDrive: un venv adentro de la carpeta sincronizada
REM       se corrompe y ensucia el sync de todo el equipo);
REM    3) instala/actualiza dependencias solo si requirements.txt cambio.
REM  Navegador:       http://127.0.0.1:8000
REM  Add-in de Excel: https://localhost:8443  (puente TLS: Office
REM                   exige HTTPS para las funciones =OMS.*)
REM ============================================================
setlocal

REM Carpeta donde vive este .bat (raiz del proyecto)
cd /d "%~dp0"
title YieldVertex

echo ============================================================
echo   YieldVertex  -  arranque local (Windows)
echo ============================================================
echo   Carpeta : %CD%

REM --- 1) Python base: py launcher (instalador oficial) o python del PATH ---
set "PYBASE="
py -3 --version >nul 2>&1
if not errorlevel 1 set "PYBASE=py -3"
if not defined PYBASE (
  python --version >nul 2>&1
  if not errorlevel 1 set "PYBASE=python"
)
if not defined PYBASE (
  echo [ERROR] No se encontro Python en esta PC.
  echo.
  echo Instalarlo con UNA de estas opciones y volver a correr este .bat:
  echo   a^) en PowerShell:  winget install -e --id Python.Python.3.12
  echo   b^) https://www.python.org/downloads/  ^(tildar "Add python.exe to PATH"^)
  echo.
  pause
  exit /b 1
)

REM --- 2) venv por maquina, FUERA de OneDrive ---
set "VENVDIR=%LOCALAPPDATA%\venvs\bonos"
set "PY=%VENVDIR%\Scripts\python.exe"
if not exist "%PY%" (
  echo Primera vez en esta PC: creando entorno en %VENVDIR% ...
  %PYBASE% -m venv "%VENVDIR%"
  if errorlevel 1 (
    echo [ERROR] No se pudo crear el entorno virtual.
    pause
    exit /b 1
  )
)

REM --- 3) dependencias: instalar solo si backend\requirements.txt cambio ---
fc /b "backend\requirements.txt" "%VENVDIR%\requirements.instalado" >nul 2>&1
if errorlevel 1 (
  echo Instalando/actualizando dependencias ^(1-3 min la primera vez^)...
  "%PY%" -m pip install --upgrade pip >nul 2>&1
  "%PY%" -m pip install -r "backend\requirements.txt"
  if errorlevel 1 (
    echo [ERROR] La instalacion de dependencias fallo. Revisar la salida de pip.
    pause
    exit /b 1
  )
  copy /y "backend\requirements.txt" "%VENVDIR%\requirements.instalado" >nul
)

for /f "delims=" %%v in ('"%PY%" --version') do set "PYVER=%%v"
echo   Python  : %PYVER%  ^(entorno %VENVDIR%^)

REM --- Modo de ejecucion ---
REM Default: ESTABLE, sin auto-reload. Con la carpeta compartida por OneDrive,
REM cada git pull del equipo hace llegar archivos de a uno y el auto-reload
REM reiniciaba la app (~1 min de arranque) una y otra vez, en plena rueda.
REM Para DESARROLLAR (auto-reload al editar especies.py, backend\, etc.):
REM   "run_backend (CORRER APP).bat" dev
set "RELOAD="
if /i "%~1"=="dev" set "RELOAD=--reload"
if /i "%~1"=="reload" set "RELOAD=--reload"

if defined RELOAD (
  echo   Modo    : DEV, auto-reload al tocar un .py
) else (
  echo   Modo    : estable, sin auto-reload  ^(dev: "run_backend ^(CORRER APP^).bat" dev^)
  echo             tras un git pull o un cambio en especies.py: Ctrl+C y volver a abrir
)
echo   App     : http://127.0.0.1:8000
echo   Add-in  : https://localhost:8443  ^(Excel =OMS.*, solo si hay certs^)
echo   Ctrl+C para detener
echo ------------------------------------------------------------

REM --- Certificado HTTPS local (funciones =OMS.* de Excel) ---
REM Idempotente: si el cert esta vigente no hace nada y sigue al toque.
REM Primera vez: genera certs\ y confia la CA en el usuario actual
REM (certutil, sin admin).
"%PY%" -m backend.tools.https_local

REM PORT viaja al proceso para que el banner de la app muestre el puerto real.
set "PORT=8000"
"%PY%" -m uvicorn backend.main:app --host 127.0.0.1 --port %PORT% %RELOAD% --timeout-graceful-shutdown 10

echo.
echo Backend se cerro. Codigo de salida: %ERRORLEVEL%
pause
endlocal
