@echo off
cd /d "C:\Users\juan.paolicchi\DELTA ASSET MANAGEMENT S.A\Inversiones - Documentos\Codes\app_calculadoras_bonos"
echo Directorio actual:
cd
echo.
echo Probando Python...
python --version
echo.
echo Iniciando Streamlit...
python -m streamlit run OMSweb_app.py
pause