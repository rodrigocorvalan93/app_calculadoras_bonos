@echo off
cd /d "C:\Users\juan.paolicchi\DELTA ASSET MANAGEMENT S.A\Inversiones - Documentos\Codes\app_calculadoras_bonos"
python -m uvicorn backend.main:app
pause