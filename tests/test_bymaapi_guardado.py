"""bymaapi (guardado manual de cierres): default de host LBO, credenciales
pareadas con el broker activo y write endurecido — delegado a
backend.services.historico_writer.append_and_save (atómico + reintentos ante
lock + consolidación del journal local de la app)."""
from __future__ import annotations

import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

bymaapi = pytest.importorskip("bymaapi")     # import pesado (universo completo)


def test_base_url_default_lbo(monkeypatch) -> None:
    monkeypatch.delenv("OMS_BASE_URL", raising=False)
    monkeypatch.delenv("PRIMARY_BASE_URL", raising=False)
    assert bymaapi._resolver_base_url() == "https://api.lbo.xoms.com.ar/"
    # sigue al broker activo de la APP (misma clave de secrets), con "/" final
    monkeypatch.setenv("PRIMARY_BASE_URL", "https://api.lbo.xoms.com.ar")
    assert bymaapi._resolver_base_url() == "https://api.lbo.xoms.com.ar/"
    # el override explícito de bymaapi manda sobre todo
    monkeypatch.setenv("OMS_BASE_URL", "https://api.latinsecurities.matrizoms.com.ar/")
    assert "latinsecurities" in bymaapi._resolver_base_url()


def test_credenciales_pareadas_con_host(monkeypatch) -> None:
    for k in ("OMS_USER", "OMS_PASS", "PRIMARY_USER", "PRIMARY_PASS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("PRIMARY_USER", "lbo_u")
    monkeypatch.setenv("PRIMARY_PASS", "lbo_p")
    monkeypatch.setenv("OMS_USER", "latin_u")
    monkeypatch.setenv("OMS_PASS", "latin_p")
    monkeypatch.setattr(bymaapi, "BASE_URL", "https://api.lbo.xoms.com.ar/")
    assert bymaapi._resolver_credenciales() == ("lbo_u", "lbo_p")
    monkeypatch.setattr(bymaapi, "BASE_URL", "https://api.latinsecurities.matrizoms.com.ar/")
    assert bymaapi._resolver_credenciales() == ("latin_u", "latin_p")
    # fallback cruzado: sin PRIMARY_*, el host LBO usa las OMS_* igual
    monkeypatch.delenv("PRIMARY_USER")
    monkeypatch.delenv("PRIMARY_PASS")
    monkeypatch.setattr(bymaapi, "BASE_URL", "https://api.lbo.xoms.com.ar/")
    assert bymaapi._resolver_credenciales() == ("latin_u", "latin_p")


def _df_cierre(fecha: date) -> pd.DataFrame:
    tz = ZoneInfo("America/Argentina/Buenos_Aires")
    return pd.DataFrame({
        "symbol": ["MERV - XMEV - T30E6 - 24hs", "MERV - XMEV - TX26j - 24hs"],
        "Código": ["T30E6", "TX26j"],
        "Last Price": [101.5, 99.8],
        "Close Price": [100.0, 99.0],
        "Variación %": ["+1.50%", "+0.81%"],
        "TIREA": ["32.10%", "31.50%"],
        "TNA": ["28.00%", "27.40%"],
        "TEM": ["2.35%", "2.30%"],
        "Paridad": [0.98, 0.97],
        "Duration": [0.6, 0.9],
        "Price Source": ["LA", "LA"],
        # tz-aware A PROPÓSITO: el write tiene que normalizarlo (openpyxl
        # muere con "Excel does not support datetimes with timezones")
        "Price Date": [pd.Timestamp(datetime(2026, 8, 31, 15, 0, tzinfo=tz))] * 2,
        "fecha_hoy": [fecha, fecha],
    })


def test_guardar_directo_tolera_celdas_basura(tmp_path) -> None:
    """Fallback legacy (write directo): un Excel viejo con texto en TIREA y una
    TIREA integral gigante mataba el espejo parquet ("PyLong is too large to
    fit int64") — el Excel quedaba bien pero la app releía el xlsx entero.
    Ahora el espejo sale con las métricas en float64 y firmado."""
    from openpyxl import Workbook

    from backend.services import espejo

    xlsx = str(tmp_path / "Delta - historico_byma_px_tasas.xlsx")
    wb = Workbook()
    ws = wb.active
    cols = ["symbol", "Código", "Last Price", "Close Price", "Variación %", "TIREA", "TNA", "TEM",
            "Paridad", "Duration", "Price Source", "Price Date", "fecha_hoy"]
    ws.append(cols)
    ws.append(["MERV - XMEV - AA - 24hs", "AA", 100.0, 99.0, 0.01, 0.31, 0.28, 0.023, 0.98, 0.6, "LA", "1", "2026-09-24"])
    ws.append(["MERV - XMEV - BB - 24hs", "BB", 100.0, 99.0, 0.01, "s/d", 0.28, 0.023, 0.98, 0.6, "LA", "1", "2026-09-24"])
    ws.append(["MERV - XMEV - CC - 24hs", "CC", 100.0, 99.0, 0.01, 10 ** 20, 0.28, 0.023, 0.98, 0.6, "LA", "1", "2026-09-24"])
    wb.save(xlsx)

    nuevo = pd.DataFrame({
        "symbol": ["MERV - XMEV - T30E6 - 24hs"], "Código": ["T30E6"],
        "Last Price": [101.5], "Close Price": [100.0], "Variación %": [0.015],
        "TIREA": [0.321], "TNA": [0.28], "TEM": [0.0235], "Paridad": [0.98], "Duration": [0.6],
        "Price Source": ["LA"], "Price Date": ["1"], "fecha_hoy": [date(2026, 9, 25)],
    })
    bymaapi._guardar_excel_directo(nuevo, xlsx)
    pq = xlsx.replace(".xlsx", ".parquet")
    assert os.path.isfile(pq) and espejo.espejo_valido(pq, xlsx)
    back = pd.read_parquet(pq).set_index("Código")
    assert str(back["TIREA"].dtype) == "float64"
    assert back.at["T30E6", "TIREA"] == 0.321 and float(back.at["CC", "TIREA"]) == 1e20
    assert pd.isna(back.at["BB", "TIREA"])                     # el texto no entra al espejo
    assert len(pd.read_excel(xlsx)) == 4                       # el Excel (canónico) quedó como siempre


def test_guardar_excel_endurecido(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HISTORICO_JOURNAL_DIR", str(tmp_path / "journal"))
    xlsx = str(tmp_path / "Delta - historico_byma_px_tasas.xlsx")
    bymaapi.guardar_excel(_df_cierre(date(2026, 8, 31)), xlsx)
    back = pd.read_excel(xlsx)
    assert len(back) == 2
    assert back["TIREA"].max() < 1.0                        # "% string" → fracción
    assert sorted(back["Proy"].tolist()) == [0, 1]          # sufijo j
    assert os.path.isfile(xlsx.replace(".xlsx", ".parquet"))    # espejo del backend
    # re-guardar el MISMO día → dedup keep-last del backend, no duplica
    bymaapi.guardar_excel(_df_cierre(date(2026, 8, 31)), xlsx)
    assert len(pd.read_excel(xlsx)) == 2
