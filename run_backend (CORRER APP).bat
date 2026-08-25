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

echo Directorio actual:
cd
echo.

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

echo Usando Python:
"%PY%" --version
echo.

REM --- Certificado HTTPS local (funciones =OMS.* de Excel) ---
REM Idempotente: si el cert esta vigente no hace nada y sigue al toque.
REM Primera vez: genera certs\ y confia la CA en el usuario actual
REM (certutil, sin admin).
"%PY%" -m backend.tools.https_local
echo.

echo Iniciando FastAPI (uvicorn) en http://127.0.0.1:8000  ...
echo (el puente HTTPS del add-in arranca solo si hay certs)
echo (Ctrl+C para detener)
echo.
"%PY%" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload --timeout-graceful-shutdown 10

echo.
echo Backend se cerro. Codigo de salida: %ERRORLEVEL%
pause
endlocal
