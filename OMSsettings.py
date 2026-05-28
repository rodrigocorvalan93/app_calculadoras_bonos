#%% """Constantes globales y parámetros de configuración de OMS."""
from pathlib import Path

BASE_URL: str = "https://api.latinsecurities.matrizoms.com.ar/"
# WA / TC se probaron pero matrizoms rechaza la query si los incluís (tira
# 0 OK / N vacíos para todos los símbolos). El panel intraday calcula VWAP
# desde los trades del día como fallback.
ENTRIES: str = "LA,BI,OF,OP,CL,SE,HI,LO,TV,OI,EV,NV,ACP"
DEPTH: int = 3
MAX_THREADS: int = 14

# Ruta por defecto para el histórico en Excel (se puede sobre‑escribir)
DEFAULT_XLSX = Path.home() / "DELTA ASSET MANAGEMENT S.A" / "Inversiones - Documentos" \
                / "Delta Bases" / "Delta - historico_byma_px_tasas.xlsx"