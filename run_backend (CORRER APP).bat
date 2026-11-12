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
REM falte DEL CODIGO (lo que git versiona + certs/ data/ secrets.txt;
REM requirements.txt incluido: pip lo lee en el paso siguiente), deja
REM "Mantener siempre en este dispositivo" solo sobre las carpetas del codigo
REM (backend/, tests/, .git/...) -- lo vecino (proyecto_cauciones_ml,
REM exportaciones sueltas) queda en la nube (11/11) -- y corta con un mensaje
REM claro si OneDrive no responde. Fuera de OneDrive no hace nada. Solo usa la
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

REM --- Clon sano (12/11): lo que OneDrive dejo distinto al repo vuelve a ser el repo ---
REM Dos PCs arrancaron con un especies.py que OneDrive dejo a medias (NameError:
REM S13N6) y una copia en conflicto especies-DAM-NB-RC.py al lado: la app quedo
REM sin universo de bonos. Esto restaura los archivos VERSIONADOS que difieren
REM del repo (git checkout), salvo especies.py (lo edita el desk a mano) y lo que
REM la app reescribe; borra copias en conflicto identicas al repo; y chequea
REM especies.py ANTES de importarlo. Si especies.py esta roto, pregunta si
REM restaurarlo desde el repo (el actual se guarda en %LOCALAPPDATA%\bonos\conflictos).
REM REPO_SANO=0 en secrets.txt lo apaga; REPO_AUTOPULL=1 ademas trae la rama.
"%PY%" -m backend.tools.repo_sano
if errorlevel 4 if not errorlevel 5 (
  echo.
  echo [ERROR] El especies.py de esta PC esta roto ^(ver arriba^): asi la app arranca sin bonos.
  echo         Si nadie cargo fichas a mano en esta PC, conviene restaurarlo desde el repo.
  echo         El archivo actual se guarda en %%LOCALAPPDATA%%\bonos\conflictos por si hace falta.
  choice /C SN /N /T 60 /D N /M "Restaurar especies.py desde el repo? [S/N] (N en 60 s) "
  if errorlevel 2 (
    echo   Queda como esta. Para arreglarlo a mano: git diff especies.py / git checkout -- especies.py
    echo.
    pause
    exit /b 4
  )
  "%PY%" -m backend.tools.repo_sano --restaurar-especies
  if errorlevel 1 (
    echo [ERROR] No se pudo restaurar especies.py ^(ver arriba^).
    pause
    exit /b 4
  )
)

REM --- Carpetas de DATOS sincronizadas por OneDrive (Delta Bases / Carteras / CAFCI) ---
REM En una PC nueva la biblioteca "Inversiones - Documentos" llega entera como
REM marcadores "solo en la nube": la app arrancaba con cientos de "[Errno 22]"
REM y Posiciones / Matriz vacias (04/11). Esto deja "Mantener siempre en este
REM dispositivo" SOLO sobre lo que la app lee (archivos de la raiz de Delta
REM Bases, cierres\, Carteras; la historia CAFCI y las exportaciones viejas
REM quedan en la nube: 11/11, antes bajaba 34 GB a cada PC) y baja AHORA lo
REM que la app necesita al arrancar. ONEDRIVE_PIN_DATOS=0 en secrets.txt =
REM sin pin; =todo = la biblioteca entera. Nunca corta el arranque: solo avisa.
"%PY%" -m backend.tools.onedrive --datos
if errorlevel 4 if not errorlevel 5 (
  echo.
  echo [AVISO] Hay archivos de las bases ^(Delta Bases / Carteras / CAFCI^) que OneDrive
  echo         todavia no bajo a esta PC. La app arranca igual, pero Posiciones, Matriz e
  echo         Historicos van a estar vacios hasta que OneDrive termine de bajarlos
  echo         ^(icono de la nube sin pausa, con sesion iniciada^). Despues: boton
  echo         "actualizar" en la pestana, o volver a abrir este .bat.
  echo.
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
