@echo off
REM ============================================================
REM  Corre el NUEVO backend FastAPI (backend.main:app) localmente
REM  Portable: usa la carpeta de este .bat, anda en cualquier PC
REM  Navegador:       http://127.0.0.1:8000
REM  Add-in de Excel: https://localhost:8443  (puente TLS: Office
REM                   exige HTTPS para las funciones =OMS.* --
REM                   el manifest se baja de esa URL)
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

REM --- Certificado HTTPS local (funciones =OMS.* de Excel) ---
REM Idempotente: si el cert esta vigente no hace nada y sigue al toque.
REM Primera vez: genera certs\ y confia la CA en el usuario actual
REM (certutil, sin admin). Si falta el paquete `cryptography` avisa como
REM instalarlo y la app arranca igual (solo http, sin funciones =OMS.*).
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
