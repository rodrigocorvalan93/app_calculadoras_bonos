"""guardar_excel de bymaapi.py — regresiones del guardado diario de la base
de px/tasas:

  - Windows: 'Excel does not support datetimes with timezones' mataba el
    guardado entero cuando alguna columna traía Timestamps tz-aware.
  - pandas 3 (Copy-on-Write): el replace('nan%', ...) inplace sobre la
    columna era chained assignment y no hacía nada.

Importar bymaapi entero tarda ~27 s (carga índices + universo), así que acá
se extraen SOLO las funciones bajo test del fuente real vía ast — lo que se
ejecuta es el código commiteado, sin el costo del import.
"""
from __future__ import annotations

import ast
import os
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parent.parent


def _load_funcs(*names: str) -> dict:
    tree = ast.parse((_REPO / "bymaapi.py").read_text(encoding="utf-8"))
    ns: dict = {"pd": pd, "np": np, "os": os, "datetime": datetime, "date": date}
    picked = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert len(picked) == len(names), f"esperaba {names} en bymaapi.py, encontré {[p.name for p in picked]}"
    for node in picked:
        mod = ast.Module(body=[node], type_ignores=[])
        exec(compile(mod, "bymaapi.py", "exec"), ns)  # noqa: S102 — código propio del repo
    return ns


def _df_base() -> pd.DataFrame:
    # Columnas mínimas que guardar_excel exige (dropna subset) + una columna
    # de timestamps TZ-AWARE como las que rompían el guardado en Windows.
    ts = pd.Timestamp("2026-07-06 15:30:00", tz="America/Argentina/Buenos_Aires")
    return pd.DataFrame({
        "symbol": ["MERV - XMEV - T30E6 - 24hs", "MERV - XMEV - S31L6 - 24hs"],
        "Código": ["T30E6", "S31L6j"],
        "fecha_hoy": [date(2026, 7, 6), date(2026, 7, 6)],
        "Last Price": [101.5, 99.8],
        "TIREA": ["32,10%", "31,50%"],
        "TNA": ["28,00%", "27,40%"],
        "TEM": ["2,35%", "2,30%"],
        "Paridad": [0.98, 0.97],
        "Duration": [0.6, 0.9],
        "hora_dato": [ts, ts],                      # tz-aware → antes moría acá
    })


def test_guardar_excel_con_timezones_no_muere(tmp_path) -> None:
    ns = _load_funcs("_sin_timezones", "guardar_excel")
    dest = tmp_path / "Delta - historico_byma_px_tasas.xlsx"
    ns["guardar_excel"](_df_base(), str(dest))
    assert dest.is_file(), "el guardado murió (antes: 'Excel does not support datetimes with timezones')"
    back = pd.read_excel(dest)
    assert len(back) == 2
    assert back["hora_dato"].dt.tz is None          # quedó naive, misma hora de pared
    assert back["hora_dato"].iloc[0].hour == 15
    assert list(back["Proy"]) == [0, 1]             # sufijo 'j' → proyectado


def test_guardar_excel_escribe_espejo_parquet(tmp_path) -> None:
    ns = _load_funcs("_sin_timezones", "guardar_excel")
    dest = tmp_path / "Delta - historico_byma_px_tasas.xlsx"
    ns["guardar_excel"](_df_base(), str(dest))
    pq = tmp_path / "Delta - historico_byma_px_tasas.parquet"
    assert pq.is_file(), "el espejo parquet no se escribió"
    back = pd.read_parquet(pq)
    assert len(back) == 2
    assert list(back["Código"]) == ["T30E6", "S31L6j"]
    # mismas filas que el Excel (espejo fiel de la base)
    assert back["TIREA"].iloc[0] == pytest.approx(0.3210)


def test_guardar_excel_concatena_con_existente(tmp_path) -> None:
    ns = _load_funcs("_sin_timezones", "guardar_excel")
    dest = tmp_path / "hist.xlsx"
    ns["guardar_excel"](_df_base(), str(dest))
    df2 = _df_base()
    df2["fecha_hoy"] = [date(2026, 7, 7), date(2026, 7, 7)]
    ns["guardar_excel"](df2, str(dest))
    back = pd.read_excel(dest)
    assert len(back) == 4                            # 2 fechas × 2 bonos, sin pisarse


def test_sin_timezones_no_toca_columnas_normales() -> None:
    ns = _load_funcs("_sin_timezones")
    df = pd.DataFrame({"a": [1.5], "b": ["texto"], "c": [date(2026, 7, 6)]})
    out = ns["_sin_timezones"](df)
    pd.testing.assert_frame_equal(out, df)


def test_operados_hoy_guard_anti_dedo() -> None:
    # Salvaguarda del guardado manual: sólo cuentan operaciones (LA) DE HOY.
    # Un finde/feriado/las 23h de un día sin rueda → ~0 → doble confirmación.
    ns = _load_funcs("_operados_hoy")
    hoy = pd.Timestamp.now(tz="America/Argentina/Buenos_Aires")
    ayer = hoy - pd.Timedelta(days=1)
    df = pd.DataFrame({
        "Price Source": ["LA", "LA", "CL", "LA", None],
        "Price Date":   [hoy,  ayer, hoy,  pd.NaT, hoy],
    })
    assert ns["_operados_hoy"](df) == 1          # sólo el LA con fecha de hoy

    # Sin columnas de fuente (flujo viejo) → 0: el guard pide confirmar, nunca revienta.
    assert ns["_operados_hoy"](pd.DataFrame({"symbol": ["X"]})) == 0
    assert ns["_operados_hoy"](pd.DataFrame()) == 0
