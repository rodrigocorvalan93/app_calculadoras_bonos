"""Histórico de caución (series diarias): memo del último pick válido del día,
merge por columna al guardar la fila FX, cobertura por serie en la pestaña y
conteo visible de ruedas guardadas en Acciones."""
from __future__ import annotations

import re
from datetime import date, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest
from httpx import ASGITransport, AsyncClient

from backend.locale_ar import fmt_date, hoy_ba
from backend.services import cauciones as cauc_svc, fx_hist, historico_writer as hw
from backend.services import marketdata_store as mds


@pytest.fixture()
def store_propio(monkeypatch):
    st = mds.MarketDataStore()
    monkeypatch.setattr(mds, "_store", st)
    cauc_svc.reset_memo()
    yield st
    cauc_svc.reset_memo()


@pytest.fixture()
def hist_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DELTA_HISTORICO_DIR", str(tmp_path))
    monkeypatch.delenv("DELTA_HISTORICO_PATH", raising=False)
    monkeypatch.delenv("DELTA_BASES_DIR", raising=False)
    fx_hist.refresh()
    yield tmp_path
    fx_hist.refresh()


def _fx(monkeypatch, ccl: float):
    from backend.services import dolares, fx as fx_svc
    monkeypatch.setattr(fx_svc, "get_fx", lambda plazo="24hs": SimpleNamespace(
        ccl=ccl, usb=ccl - 30.0, canje=ccl / (ccl - 30.0) - 1.0, ccl_base="GD30"))
    monkeypatch.setattr(dolares, "official_fx", lambda: {"last": 1350.0})


def test_hist_row_cae_al_ultimo_pick_valido_de_hoy(store_propio, monkeypatch) -> None:
    store_propio.update_from_md("MERV - XMEV - PESOS - 2D",
                                {"LA": {"price": 31.0, "size": 4e6, "date": "9"}, "HI": 32.0, "LO": 30.0,
                                 "NV": 3.65e9, "EV": 3.65e9 + 1e7 * 0.31 * 2})
    assert cauc_svc.rail_pick("PESOS")["_n"] == 2                 # el riel la vio operando hoy
    assert cauc_svc.ultimo_hoy("PESOS")["tasa"] == 31.0
    # a la hora del autosave el store ya no la tiene como "de hoy" (degradó a cierre)
    monkeypatch.setattr(cauc_svc, "_last_es_de_hoy", lambda snap: False)
    assert cauc_svc.rail_pick("PESOS")["es_cierre"] is True
    r = cauc_svc.hist_row("PESOS")
    assert r and r["plazo_d"] == 2 and r["tna"] == 31.0 and r["monto"] == pytest.approx(3.65e9 + 1e7 * 0.31 * 2)
    assert "memo hoy=sí" in cauc_svc.diagnostico("PESOS")
    # sin nada visto hoy → None y el diagnóstico lo dice
    cauc_svc.reset_memo()
    assert cauc_svc.hist_row("PESOS") is None
    assert "cierre=True" in cauc_svc.diagnostico("PESOS")
    monkeypatch.setattr(mds, "_store", mds.MarketDataStore())
    assert "sin snapshots" in cauc_svc.diagnostico("PESOS")


def test_guardar_fx_no_pisa_la_caucion_con_vacio(hist_env, monkeypatch) -> None:
    _fx(monkeypatch, 1500.0)
    monkeypatch.setattr(cauc_svc, "hist_row", lambda moneda="PESOS": (
        {"plazo_d": 1, "tna": 31.0, "vwap": 30.9, "monto": 5e9} if moneda == "PESOS" else None))
    assert hw._guardar_fx(str(hist_env))["filas"] == 1
    # segundo guardado del MISMO día sin caución (17:01 con el feed degradado):
    # actualiza el CCL y conserva la caución de la mañana
    _fx(monkeypatch, 1520.0)
    monkeypatch.setattr(cauc_svc, "hist_row", lambda moneda="PESOS": None)
    assert hw._guardar_fx(str(hist_env))["filas"] == 1
    pq = hist_env / hw.FX_FILENAME.replace(".xlsx", ".parquet")
    back = pd.read_parquet(pq)
    assert len(back) == 1 and back.iloc[0]["ccl"] == 1520.0
    assert back.iloc[0]["caucion_tna"] == 31.0 and back.iloc[0]["caucion_plazo_d"] == 1
    assert back.iloc[0]["caucion_tna_vwap"] == 30.9 and pd.isna(back.iloc[0]["caucion_usd_tna"])
    # cobertura por serie (lo que muestra la pestaña)
    fx_hist.refresh()
    st = fx_hist.status()
    assert st["loaded"] and st["n"] == 1
    assert st["series"]["caucion_tna"]["n"] == 1 and st["series"]["caucion_usd_tna"]["n"] == 0
    assert st["series"]["ccl"]["n"] == 1 and st["series"]["caucion_tna"]["ultimo"] == st["dmax"]


def test_recaptura_reintenta_la_fila_fx(hist_env, monkeypatch) -> None:
    from backend.config import settings
    llamadas = []
    monkeypatch.setattr(settings, "historico_base_writer", True)
    monkeypatch.setattr(hw, "build_rows", lambda plazo="24hs": None)
    monkeypatch.setattr(hw, "_guardar_cierre", lambda *a, **k: {"filas": 3, "opero": 40, "path": "x"})
    monkeypatch.setattr(hw, "_guardar_acciones", lambda hist_dir: None)
    monkeypatch.setattr(hw, "_guardar_fx", lambda hist_dir: llamadas.append(hist_dir) or {"filas": 1})
    res = hw.recapturar_cierre(force=True)
    assert res["ok"] and res["fx"] is True and llamadas == [str(hist_env)]


@pytest.mark.asyncio
async def test_pestanas_muestran_cobertura_y_ruedas(hist_env, monkeypatch) -> None:
    from backend.main import app
    from backend.services import acciones_hist, cierres

    hoy = hoy_ba()
    dias = [hoy - timedelta(days=k) for k in (8, 7, 6, 1, 0)]
    fx = pd.DataFrame({"fecha_hoy": dias, "ccl": [1500.0 + i for i in range(5)], "mep": [1470.0] * 5,
                       "canje": [0.02] * 5, "oficial_a3500": [1350.0] * 5, "ccl_base": ["GD30"] * 5,
                       "caucion_plazo_d": [1, None, None, None, None], "caucion_tna": [31.0, None, None, None, None],
                       "caucion_tna_vwap": [None] * 5, "caucion_monto": [5e9, None, None, None, None]})
    fx.to_parquet(hist_env / "Delta - historico_fx.parquet", index=False)
    rows = [{"fecha_hoy": d, "ticker": t, "panel": "L", "ultimo": 100.0 + i, "volumen": 1e9}
            for i, d in enumerate(dias) for t in ("GGAL", "YPFD")]
    pd.DataFrame(rows).to_parquet(hist_env / hw.ACCIONES_FILENAME, index=False)
    fx_hist.refresh()
    acciones_hist.refresh()
    cierres.refresh()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
            s = (await ac.get("/historicos/series-diarias?serie=caucion_tna")).text
            assert "Con dato" in s and "5 días guardados" in s
            assert re.search(r"Caución \$ o/n TNA cierre\s*<b>1</b>", s) and f"(último {dias[0].isoformat()})" in s
            assert re.search(r"CCL implícito\s*<b>5</b>", s)
            assert "sd-cob-warn" in s
            a = (await ac.get("/historicos/acciones?ticker=GGAL&dias=30")).text
            assert "Guardado:" in a and "acciones <b>5</b> ruedas" in a and "<b>2</b> especies" in a
            assert "Pocas ruedas todavía" in a and "backfill_acciones" in a
            assert fmt_date(dias[0].isoformat()) in a
    finally:
        fx_hist.refresh()
        acciones_hist.refresh()
        cierres.refresh()


def test_fmt_date_iso() -> None:
    assert fmt_date("2026-09-09") == "09/09/2026" and fmt_date("2026-09-09T17:01:00") == "09/09/2026"
    assert fmt_date(date(2026, 9, 9)) == "09/09/2026" and fmt_date("basura") == "basura"
