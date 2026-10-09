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


def test_regenera_el_espejo_con_celdas_basura_en_el_excel(hist_dir) -> None:
    """28/09/2026: "no pude regenerar el parquet (PyLong is too large to fit
    int64)" — una celda con texto en TIREA + una TIREA integral gigante en el
    Excel dejaban a la app sin espejo, releyendo el xlsx entero (7 s) en cada
    carga. Ahora el espejo se regenera con las métricas en float64."""
    from openpyxl import Workbook

    from backend.services import espejo

    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["fecha_hoy", "Código", "TIREA", "TNA", "TEM", "Paridad", "Last Price", "Duration"])
    ws.append(["2026-07-06", "T30E6", 0.32, 0.28, 0.0235, 0.98, 101.5, 0.6])
    ws.append(["2026-07-06", "BB", "s/d", 0.28, 0.0235, 0.98, 100.0, 0.6])     # texto que no es NA
    ws.append(["2026-07-06", "CC", 10 ** 20, 0.28, 0.0235, 0.98, 100.0, 0.6])  # int que no entra en int64
    wb.save(hist_dir / _XLSX)
    raw = pd.read_excel(hist_dir / _XLSX, sheet_name="Sheet1")
    assert str(raw["TIREA"].dtype) == "object"                # el crudo reproduce el caso

    out = historico_byma._load()
    assert out["loaded"] is True and str(out["path"]).endswith(".xlsx")
    assert out["by_code"]["T30E6"]["vals"]["TIREA"][0] == pytest.approx(0.32)
    assert "CC" not in out["by_code"]                          # TIREA absurda: filtrada como siempre
    pq = hist_dir / _PARQUET
    assert pq.is_file() and espejo.espejo_valido(str(pq), str(hist_dir / _XLSX))
    back = pd.read_parquet(pq)
    assert str(back["TIREA"].dtype) == "float64"
    assert back.set_index("Código")["TIREA"].isna().to_dict()["BB"] is True
    assert float(back.set_index("Código").at["CC", "TIREA"]) == 1e20
    # la próxima carga ya va por el espejo, con la misma data
    out2 = historico_byma._load()
    assert str(out2["path"]).endswith(".parquet")
    assert out2["by_code"]["T30E6"]["vals"]["TIREA"][0] == pytest.approx(0.32)


def test_regenera_el_espejo_con_price_date_mixto_en_el_excel(hist_dir) -> None:
    """09/10/2026 (PC de un compañero): "no pude regenerar el parquet (Expected
    bytes, got a 'datetime.datetime' object — Conversion failed for column
    Price Date)". El writer escribe 'Price Date' como texto ISO pero bymaapi /
    una celda tocada a mano la dejan como FECHA de Excel; con las dos en la
    misma columna el lector no podía espejar y releía el xlsx entero en cada
    arranque (y el chip leía las ruedas del Excel, 5 s). El espejo se regenera
    con las columnas de texto en `string`, como las deja el writer."""
    from datetime import datetime

    from openpyxl import Workbook

    from backend.services import espejo

    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["fecha_hoy", "Código", "TIREA", "TNA", "TEM", "Paridad", "Last Price", "Duration",
               "Price Source", "Price Date", "symbol"])
    ws.append(["2026-07-06", "T30E6", 0.32, 0.28, 0.0235, 0.98, 101.5, 0.6,
               "LA", "2026-07-06 16:59:00", "MERV - XMEV - T30E6 - 24hs"])         # writer: texto ISO
    ws.append(["2026-07-07", "T30E6", 0.33, 0.28, 0.0235, 0.98, 101.9, 0.6,
               "LA", datetime(2026, 7, 7, 16, 58), "MERV - XMEV - T30E6 - 24hs"])  # bymaapi: fecha de Excel
    ws.append(["2026-07-07", "AL30", 0.10, 0.09, 0.0075, 0.70, 60.0, 2.1,
               "RC", None, 12345])                                                 # símbolo numérico tipeado
    wb.save(hist_dir / _XLSX)
    raw = pd.read_excel(hist_dir / _XLSX, sheet_name="Sheet1")
    assert str(raw["Price Date"].dtype) == "object" and isinstance(raw["Price Date"].iloc[1], datetime)
    with pytest.raises(Exception):                              # el crudo reproduce el caso
        raw.to_parquet(hist_dir / "crudo.parquet", index=False)

    out = historico_byma._load()
    assert out["loaded"] is True and str(out["path"]).endswith(".xlsx")
    pq = hist_dir / _PARQUET
    assert pq.is_file() and espejo.espejo_valido(str(pq), str(hist_dir / _XLSX))
    back = pd.read_parquet(pq)
    for col in espejo.COLS_TEXTO:
        assert str(back[col].dtype) == "string", col
    assert list(back["Price Date"].astype(object).fillna("")) == ["2026-07-06 16:59:00", "2026-07-07 16:58:00", ""]
    assert list(back["symbol"]) == ["MERV - XMEV - T30E6 - 24hs"] * 2 + ["12345"]
    # la próxima carga ya va por el espejo, con la misma data
    out2 = historico_byma._load()
    assert str(out2["path"]).endswith(".parquet")
    assert out2["by_code"]["T30E6"]["vals"]["TIREA"] == [pytest.approx(0.32), pytest.approx(0.33)]


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
