"""Histórico px/tasas en Parquet: la app lee el espejo .parquet cuando está
al día (lectura ~100× más rápida que el Excel) y cae al Excel — regenerando
el espejo — cuando el Excel es más nuevo (bymaapi viejo / edición a mano).
"""
from __future__ import annotations

import os
import time
from datetime import date

import pandas as pd
import pytest

from backend.services import historico_byma

_XLSX = "Delta - historico_byma_px_tasas.xlsx"
_PARQUET = "Delta - historico_byma_px_tasas.parquet"


def _df(tirea: float) -> pd.DataFrame:
    return pd.DataFrame({
        "fecha_hoy": [date(2026, 7, 6), date(2026, 7, 7)],
        "Código": ["T30E6", "T30E6"],
        "TIREA": [tirea, tirea + 0.001],
        "TNA": [0.28, 0.281],
        "TEM": [0.0235, 0.0236],
        "Paridad": [0.98, 0.981],
        "Last Price": [101.5, 101.9],
        "Duration": [0.6, 0.6],
    })


@pytest.fixture()
def hist_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("DELTA_HISTORICO_PATH", raising=False)
    monkeypatch.delenv("DELTA_BASES_DIR", raising=False)
    monkeypatch.setenv("DELTA_HISTORICO_DIR", str(tmp_path))
    return tmp_path


def test_reads_parquet_when_fresh(hist_dir) -> None:
    _df(0.32).to_excel(hist_dir / _XLSX, index=False, sheet_name="Sheet1")
    _df(0.55).to_parquet(hist_dir / _PARQUET, index=False)   # más nuevo (recién escrito)
    out = historico_byma._load()
    assert out["loaded"] is True
    assert str(out["path"]).endswith(".parquet")
    tirea = out["by_code"]["T30E6"]["vals"]["TIREA"][0]
    assert tirea == pytest.approx(0.55)                      # vino del parquet


def test_falls_back_to_newer_xlsx_and_regenerates_mirror(hist_dir) -> None:
    _df(0.55).to_parquet(hist_dir / _PARQUET, index=False)
    old = time.time() - 3600.0                               # parquet viejo (1 h)
    os.utime(hist_dir / _PARQUET, (old, old))
    _df(0.32).to_excel(hist_dir / _XLSX, index=False, sheet_name="Sheet1")
    out = historico_byma._load()
    assert out["loaded"] is True
    assert str(out["path"]).endswith(".xlsx")                # el Excel más nuevo manda
    assert out["by_code"]["T30E6"]["vals"]["TIREA"][0] == pytest.approx(0.32)
    # ... y el espejo quedó regenerado con la data del Excel.
    assert pd.read_parquet(hist_dir / _PARQUET)["TIREA"].iloc[0] == pytest.approx(0.32)


def test_parquet_only_works_without_xlsx(hist_dir) -> None:
    _df(0.44).to_parquet(hist_dir / _PARQUET, index=False)
    out = historico_byma._load()
    assert out["loaded"] is True
    assert str(out["path"]).endswith(".parquet")
    assert out["by_code"]["T30E6"]["vals"]["TIREA"][0] == pytest.approx(0.44)


def test_nothing_found_keeps_legacy_error(hist_dir) -> None:
    out = historico_byma._load()
    assert out["loaded"] is False
    assert "Excel histórico" in (out["error"] or "")
