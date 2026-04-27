"""
fx.py
=====

Cálculo de tipo de cambio implícito (CCL / MEP).
"""

from __future__ import annotations

from typing import Literal

import pandas as pd
import requests

from old.api import mercado_masivo

_POSTURA = Literal["LAST", "BI", "OF"]


def _seleccionar_rutas(postura: _POSTURA) -> tuple[str, str]:
    """Devuelve (ruta_num, ruta_den) según la postura."""
    match postura:
        case "LAST":
            return "LA.price", "LA.price"
        case "BI":
            return "BI[0].price", "OF[0].price"
        case "OF":
            return "OF[0].price", "BI[0].price"
    raise ValueError(postura)  # pragma: no cover


def _caminar_ruta(fila: pd.Series, ruta: str) -> float | None:
    """Acceso ligero a un 'json path' simplificado."""
    obj = fila
    for paso in ruta.split("."):
        if "[" in paso and "]" in paso:
            clave, idx = paso.rstrip("]").split("[")
            obj = obj.get(clave)
            if not obj:
                return None
            obj = obj[int(idx)]
        else:
            obj = obj.get(paso) if isinstance(obj, dict) else None
        if obj is None:
            return None
    return float(obj)


def calcular_par_fx(
    ses: requests.Session,
    bono: str,
    fx: Literal["CCL", "MEP"],
    plazo: Literal["CI", "24hs"],
    postura: _POSTURA = "LAST",
) -> float | None:
    """
    Devuelve el tipo de cambio implícito (o `None` si falta algún precio).
    """
    sufijo = "C" if fx == "CCL" else "D"
    num = f"MERV - XMEV - {bono} - {plazo}"
    den = f"MERV - XMEV - {bono}{sufijo} - {plazo}"

    df = mercado_masivo(ses, [num, den], entradas="LA,BI,OF")
    if df.empty or num not in df.index or den not in df.index:
        return None

    ruta_num, ruta_den = _seleccionar_rutas(postura)
    p_num = _caminar_ruta(df.loc[num], ruta_num)
    p_den = _caminar_ruta(df.loc[den], ruta_den)

    return p_num / p_den if p_num and p_den else None
