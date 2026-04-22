"""
transformaciones.py
===================

Utilidades de DataFrame:
- `aplanar_df`
- `procesa_futuros_data`
"""

from __future__ import annotations

from datetime import datetime as dt
from typing import Sequence

import pandas as pd


def aplanar_df(
    df: pd.DataFrame,
    lados: Sequence[str] = ("BI", "OF", "LA", "CL", "EV"),
) -> pd.DataFrame:
    """
    Convierte el market-data anidado en un DataFrame plano.
    """
    pilas: list[pd.DataFrame] = []

    for lado in lados:
        if lado not in df.columns:
            continue

        serie = df[lado].dropna()
        if serie.empty:
            continue

        tmp = (
            pd.json_normalize(serie)
            .assign(symbol=serie.index, lado=lado)
            .rename(columns=lambda c: c.replace(".", "_"))
        )
        pilas.append(tmp)

    return pd.concat(pilas, ignore_index=True)


def procesa_futuros_data(
    la_futuros: pd.DataFrame,
    vencimientos: pd.DataFrame,
    a3500: float,
) -> pd.DataFrame:
    """
    Une LA futures + vencimientos y calcula tasas.
    """
    df = la_futuros.merge(vencimientos, on="symbol", how="left")
    df["maturityDate"] = pd.to_datetime(df["maturityDate"], format="%Y%m%d")
    df["días_al_vto"] = (df["maturityDate"] - dt.today()).dt.days

    df["tasa_directa"] = df["price"] / a3500 - 1
    df["TNA"] = df["tasa_directa"] * (365 / df["días_al_vto"])
    df["TEA"] = (1 + df["tasa_directa"]) ** (365 / df["días_al_vto"]) - 1

    return df.sort_values("días_al_vto", ascending=True).reset_index(drop=True)
