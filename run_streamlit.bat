@echo off
REM ============================================================
REM  Corre la app LEGACY de Streamlit (OMSweb_app.py)
REM  Portable: usa la carpeta de este .bat, anda en cualquier PC
REM ============================================================
setlocal

REM Carpeta donde vive este .bat (con backslash final)
cd /d "%~dp0"

echo Directorio actual:
cd
echo.

REM --- Python del sistema ---
set "PY=python"

echo Usando Python: %PY%
"%PY%" --version
echo.

echo Iniciando Streamlit...
"%PY%" -m streamlit run OMSweb_app.py

echo.
echo Streamlit se cerro. Codigo de salida: %ERRORLEVEL%
pause
endlocal
