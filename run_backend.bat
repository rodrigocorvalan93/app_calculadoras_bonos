@echo off
REM ============================================================
REM  Corre el NUEVO backend FastAPI (backend.main:app) localmente
REM  Portable: usa la carpeta de este .bat, anda en cualquier PC
REM  Abrir en el navegador: http://127.0.0.1:8000
REM ============================================================
setlocal

REM Carpeta donde vive este .bat (raiz del proyecto)
cd /d "%~dp0"

echo Directorio actual:
cd
echo.

REM --- Python del sistema ---
set "PY=python"

echo Usando Python: %PY%
"%PY%" --version
echo.

echo Iniciando FastAPI (uvicorn) en http://127.0.0.1:8000  ...
echo (Ctrl+C para detener)
echo.
"%PY%" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

echo.
echo Backend se cerro. Codigo de salida: %ERRORLEVEL%
pause
endlocal
