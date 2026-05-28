#%% """Constantes globales y parámetros de configuración de OMS."""
from pathlib import Path

BASE_URL: str = "https://api.latinsecurities.matrizoms.com.ar/"
# WA = Weighted Average Price (VWAP intradía si la API lo expone)
# TC = Trade Count (cantidad de operaciones del día)
ENTRIES: str = "LA,BI,OF,OP,CL,SE,HI,LO,TV,OI,EV,NV,ACP,WA,TC"
DEPTH: int = 3
MAX_THREADS: int = 14

# Ruta por defecto para el histórico en Excel (se puede sobre‑escribir)
DEFAULT_XLSX = Path.home() / "DELTA ASSET MANAGEMENT S.A" / "Inversiones - Documentos" \
                / "Delta Bases" / "Delta - historico_byma_px_tasas.xlsx"