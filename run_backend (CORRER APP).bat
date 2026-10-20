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

REM PORT viaja al proceso: el banner muestra el puerto real y la app chequea
REM que no haya otra instancia antes de cargar nada.
set "PORT=8000"

REM --- Si la app YA esta corriendo (otra ventana / servicio), no arrancar una
REM segunda: uvicorn moriria al final del arranque con "solo se permite un
REM uso de cada direccion de socket". Solo se abre el navegador (igual que el
REM .command de Mac). curl viene con Windows 10+; sin curl se sigue normal. ---
curl -s -o NUL --max-time 1 http://127.0.0.1:%PORT%/healthz >NUL 2>&1
if not errorlevel 1 (
  echo La app ya esta corriendo en http://127.0.0.1:%PORT% - abriendo el navegador.
  echo ^(para reiniciarla: Ctrl+C en la ventana donde corre y volver a abrir este .bat^)
  start "" http://127.0.0.1:%PORT%
  timeout /t 3 >nul
  exit /b 0
)

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
REM --- .pyc FUERA de la carpeta sincronizada (15/10): sin esto cada PC
REM     escribia __pycache__ adentro del clon y OneDrive los repartia a todas
REM     (un set por version de Python, copias en conflicto, bajadas al importar).
REM     Python los regenera solo; el chequeo de OneDrive borra los viejos.
set "PYTHONPYCACHEPREFIX=%LOCALAPPDATA%\bonos\pycache"
if not exist "%PY%" (
  echo Primera vez en esta PC: creando entorno en %VENVDIR% ...
  %PYBASE% -m venv "%VENVDIR%"
  if errorlevel 1 (
    echo [ERROR] No se pudo crear el entorno virtual.
    pause
    exit /b 1
  )
)

REM --- Archivos a peticion de OneDrive (carpeta del codigo sincronizada) ---
REM Un archivo NUEVO del repo llega a las otras PCs como marcador "solo en la
REM nube" y, si OneDrive no lo entrega al leerlo, Python muere al importar con
REM "OSError: [Errno 22] Invalid argument" (Pablo, 13/10). Esto baja lo que
REM falte (requirements.txt incluido: pip lo lee en el paso siguiente), deja la
REM carpeta "Mantener siempre en este dispositivo" y corta con un mensaje claro
REM si OneDrive no responde. Fuera de OneDrive no hace nada. Solo usa la
REM biblioteca estandar: corre aunque las dependencias no esten instaladas.
"%PY%" -m backend.tools.onedrive
if errorlevel 4 if not errorlevel 5 (
  echo.
  echo [ERROR] Hay archivos del codigo que OneDrive todavia no bajo a esta PC
  echo         ^(Archivos a peticion: figuran "solo en la nube"^). Asi la app no arranca.
  echo   1^) Fijate que OneDrive este abierto y sincronizando ^(icono de la nube
  echo      en la barra, sin pausa ni error, con sesion iniciada^).
  echo   2^) Boton derecho sobre la carpeta del codigo ^> "Mantener siempre en este dispositivo"
  echo      y espera a que termine de bajar.
  echo   3^) Volver a abrir este .bat.
  echo.
  pause
  exit /b 4
)
if errorlevel 1 (
  echo.
  echo [ERROR] El chequeo previo de archivos fallo ^(ver arriba^).
  echo   Si dice "OSError: [Errno 22] Invalid argument", es OneDrive: abrilo, boton derecho
  echo   sobre la carpeta del codigo ^> "Mantener siempre en este dispositivo", esperar y reabrir.
  echo   Si es otro error de Python, mandalo tal cual.
  echo.
  pause
  exit /b 1
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
set "OMS_RELOAD="
if /i "%~1"=="dev" set "RELOAD=--reload"
if /i "%~1"=="reload" set "RELOAD=--reload"
if defined RELOAD set "OMS_RELOAD=1"

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

"%PY%" -m uvicorn backend.main:app --host 127.0.0.1 --port %PORT% %RELOAD% --timeout-graceful-shutdown 10 --timeout-keep-alive 75

echo.
echo Backend se cerro. Codigo de salida: %ERRORLEVEL%
pause
endlocal
