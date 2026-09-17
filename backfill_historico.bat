@echo off
REM ============================================================
REM  Reconstruye el historico HACIA ATRAS (corre fuera de la app):
REM    - FX (CCL / MEP / canje) desde ArgentinaDatos
REM    - acciones, CEDEARs y Merval en pesos desde BYMA Open Data
REM  Usa el MISMO entorno que "run_backend (CORRER APP).bat"
REM  (%%LOCALAPPDATA%%\venvs\bonos) y la misma carpeta Delta Bases
REM  (DELTA_BASES_DIR / DELTA_HISTORICO_DIR de secrets.txt).
REM  Nunca pisa una fila que grabo la app; solo agrega fechas anteriores y
REM  deja respaldo (*.bak-fecha-hora) antes de escribir.
REM  Conviene correrlo FUERA de la ventana del cierre (17:00 a 17:30) y con
REM  "Delta - historico_fx.xlsx" cerrado en Excel.
REM ============================================================
setlocal
cd /d "%~dp0"

set "PY=%LOCALAPPDATA%\venvs\bonos\Scripts\python.exe"
if not exist "%PY%" (
  echo [ERROR] No existe el entorno %PY%
  echo Corre primero "run_backend (CORRER APP).bat" una vez ^(crea el entorno^) y volve a intentar.
  pause
  exit /b 1
)
echo Usando Python:
"%PY%" --version
echo.

:menu
echo Que queres hacer?
echo   1^) FX: ver el PLAN ^(dry-run: no escribe nada^)
echo   2^) FX: escribir ^(agrega fechas anteriores, con respaldo^)
echo   3^) Acciones / CEDEARs / Merval desde BYMA ^(ultimos 2 anios; las filas de la app ganan^)
echo   4^) Salir
set "OP="
set /p OP="Opcion [1-4]: "
if "%OP%"=="1" goto fx_plan
if "%OP%"=="2" goto fx_escribir
if "%OP%"=="3" goto acciones
if "%OP%"=="4" goto fin
echo Opcion invalida.
goto menu

:fx_plan
echo.
"%PY%" -m backend.tools.backfill_fx --argentinadatos --dry-run
echo.
goto menu

:fx_escribir
echo.
"%PY%" -m backend.tools.backfill_fx --argentinadatos
echo.
goto menu

:acciones
echo.
echo Bajando de BYMA Open Data ^(163 tickers, tarda unos minutos^)...
"%PY%" -m backend.tools.backfill_acciones --byma
if errorlevel 1 (
  echo.
  echo Si el error fue de TLS ^(cadena incompleta del sitio de BYMA^), reintenta con:
  echo   "%PY%" -m backend.tools.backfill_acciones --byma --tls-inseguro
)
echo.
goto menu

:fin
endlocal
