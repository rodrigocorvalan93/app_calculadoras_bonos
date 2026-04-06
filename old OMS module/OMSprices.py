#%% """Funciones de extracción y helpers genéricos."""
from typing import Dict, Optional
import numpy as np
import pandas as pd


def safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    return a / b if (a is not None and b) else None


def last_price(df: pd.DataFrame) -> pd.DataFrame:
    """Extrae último y cierre + variación."""
    out = pd.DataFrame(index=df.index)
    out["last"] = df["LA"].map(lambda x: x.get("price") if isinstance(x, dict) else np.nan)
    out["close"] = df["CL"].map(lambda x: x.get("price") if isinstance(x, dict) else np.nan)
    out["variation"] = (out["last"] / out["close"] - 1)
    return out