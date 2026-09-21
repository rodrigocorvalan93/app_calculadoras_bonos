"""cierres._build con un valor desbordado: rentafija.py sube TODO RuntimeWarning
a error a nivel proceso y el "overflow encountered in cast" (float64 → float32
de un 1e39 en `volume`) pasaba a excepción → la matriz entera no se armaba (5D
de Mercado y price action de bonos vacíos en esa PC). Ahora la celda queda NaN
y el resto de la matriz sale igual."""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from backend.services import cierres


def test_valor_desbordado_no_voltea_la_matriz() -> None:
    df = pd.DataFrame({
        "fecha_hoy": ["2026-09-17", "2026-09-17", "2026-09-18", "2026-09-18"],
        "symbol": ["A - 24hs", "B - 24hs", "A - 24hs", "B - 24hs"],
        "code": ["A", "B", "A", "B"],
        "plazo": ["24hs"] * 4,
        "last": [100.0, 200.0, 101.0, 202.0],
        "volume": [1e6, 1e39, 2e6, float("inf")],        # 1e39 no entra en float32; inf tampoco
        "high": [100.5, "basura", 101.5, None],
        "opero": [True, True, True, False],
    })
    with warnings.catch_warnings():
        warnings.filterwarnings("error", category=RuntimeWarning)   # como rentafija.py
        m = cierres._build(df)
    assert m is not None and m.fechas == ["2026-09-17", "2026-09-18"] and m.simbolos == ["A - 24hs", "B - 24hs"]
    assert m.mat["last"].dtype == np.float64 and m.mat["volume"].dtype == np.float32
    assert m.mat["last"][1, 1] == 202.0 and m.mat["last"][0, 0] == 100.0
    assert m.mat["volume"][0, 0] == np.float32(1e6) and m.mat["volume"][1, 0] == np.float32(2e6)
    assert np.isnan(m.mat["volume"][0, 1]) and np.isnan(m.mat["volume"][1, 1])   # 1e39 e inf → NaN
    assert m.mat["high"][0, 0] == np.float32(100.5) and np.isnan(m.mat["high"][0, 1]) and np.isnan(m.mat["high"][1, 1])
    assert bool(m.opero[1, 1]) is False and bool(m.opero[0, 0]) is True
