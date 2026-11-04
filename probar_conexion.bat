@echo off
REM probar_conexion.bat — diagnostico de la conexion al broker (Latin / LBO / Cocos)
REM Corre probar_conexion.py con el venv de la app (el mismo que arma
REM "run_backend (CORRER APP).bat") y deja el prompt interactivo abierto.
REM Que tocar: el bloque CONFIG de probar_conexion.py (host, usuario, clave, simbolos).
setlocal
cd /d "%~dp0"
set "PY=%LOCALAPPDATA%\venvs\bonos\Scripts\python.exe"
if not exist "%PY%" (
  echo [aviso] no existe el venv de la app en %LOCALAPPDATA%\venvs\bonos - uso el python del PATH
  set "PY=python"
)
"%PY%" -i probar_conexion.py
pause
