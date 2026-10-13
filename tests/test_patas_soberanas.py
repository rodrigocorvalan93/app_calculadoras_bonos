"""Patas de los soberanos hard-dollar en el histórico (13/10).

`services/patas` (resolver por sufijo), `historico_writer.build_rows` (fila
por pata: cruzada con TIR directa, pesos ÷ FX del día, columnas Pata / FX),
reconstrucción (`_fila_rc` / `_filas_desde_base` / `_fx_desde_filas`), el
cierre completo (tirea en el símbolo de la pata) y los lectores
(`price_action.serie_de`, selector de Históricos, pestaña Base)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from backend.services import cierres, fx_hist, historico_byma, marketdata_store, patas, price_action, pricing
from backend.services import fx as fx_svc
from backend.services import historico_writer as hw
from backend.services import symbols as syms


def _ms() -> str:
    return str(int(datetime.now(hw._TZ).timestamp() * 1000))


def _seed(code: str, last: float, close: float) -> None:
    # el CL del feed viene fechado (ayer): la reconstrucción desde el feed lo exige
    ayer = str(int((datetime.now(hw._TZ) - timedelta(days=1)).timestamp() * 1000))
    marketdata_store.get_store().update_from_md(syms.md_symbol(code, "24hs"), {
        "LA": {"price": last, "date": _ms()}, "CL": {"price": close, "date": ayer}})


def _seed_al30() -> None:
    _seed("AL30", 95_000.0, 94_000.0)
    _seed("AL30D", 68.0, 67.5)
    _seed("AL30C", 66.0, 65.8)
    fx_svc.invalidate()


# ── resolver ─────────────────────────────────────────────────────────────────
def test_resolver_por_sufijo_cubre_las_15_bases_y_nada_mas() -> None:
    s = patas.soberanas()
    assert len(s) == 30 and {p.pata for p in s.values()} == {"ARS", "MEP", "CABLE"}
    assert s["AO27C"] == patas.Pata("AO27C", "AO27D", "CABLE", True, "USB")
    assert s["AO27"] == patas.Pata("AO27", "AO27D", "ARS", False, "USB")
    assert s["GD30D"] == patas.Pata("GD30D", "GD30C", "MEP", True, "USD")
    assert s["GD30"].nativa == "GD30C" and s["GD30"].pata == "ARS" and not s["GD30"].directa
    assert s["AO29"].nativa == "AO29D" and "AO29C" in s            # ISIN placeholder: por sufijo entra igual
    assert "AO27D" not in s and "GD30C" not in s                   # las nativas ya son filas de curva
    assert patas.pata_de("YM34C") is None and patas.pata_de("") is None and patas.pata_de(None) is None
    assert patas.calc_para("AO27C") == "AO27D" and patas.calc_para("TX26") == "TX26"
    assert not any(pricing.bond_meta(k) for k in s if k.endswith(("C", "D")) and s[k].directa)  # cruzadas sin ficha

    class _F:
        ccl, usb = 1439.0, 1397.0

    assert patas.fx_usado(_F(), "USB") == 1397.0 and patas.fx_usado(_F(), "USD") == 1439.0
    assert patas.fx_usado(None, "USB") is None


def test_las_patas_no_entran_a_las_curvas() -> None:
    from backend.services import curves
    cc = curves.build_curve_codes()
    todos = {c for v in cc.values() for c in v}
    assert not (set(patas.soberanas()) & todos)


# ── writer ───────────────────────────────────────────────────────────────────
def test_build_rows_emite_cruzada_directa_y_pesos_por_fx() -> None:
    _seed_al30()
    df = hw.build_rows()
    fx = fx_svc.get_fx("24hs")
    settle = pricing.settlement_date_str("24hs")
    por = {r["Código"]: r for r in df.to_dict("records")}
    assert {"AL30D", "AL30C", "AL30"} <= set(por)
    d, c, a = por["AL30D"], por["AL30C"], por["AL30"]
    # nativa: como siempre (sin pata, sin FX)
    assert d["Pata"] == "" and pd.isna(d["FX"]) and d["Last Price"] == 68.0
    # cruzada: precio crudo del ticker C contra la ficha D (TIR directa)
    assert c["Pata"] == "CABLE" and pd.isna(c["FX"]) and c["symbol"] == "MERV - XMEV - AL30C - 24hs"
    assert c["Last Price"] == 66.0 and c["Close Price"] == 65.8 and c["Price Source"] == "LA"
    esperado = pricing.metrics_for_market_price("AL30D", 66.0, settle)
    assert c["TIREA"] == pytest.approx(esperado["tirea"], rel=1e-9)
    assert c["Duration"] == pytest.approx(esperado["duration"], rel=1e-9)
    assert c["TIREA"] > d["TIREA"]                 # mismo flujo, precio más bajo → TIR más alta
    # pesos: precio ÷ MEP del día, con el FX usado en la fila
    assert a["Pata"] == "ARS" and a["Last Price"] == 95_000.0 and a["FX"] == pytest.approx(fx.usb)
    esperado = pricing.metrics_for_market_price("AL30D", 95_000.0 / fx.usb, settle)
    assert a["TIREA"] == pytest.approx(esperado["tirea"], rel=1e-9)
    assert a["Variación %"] == pytest.approx(95_000.0 / 94_000.0 - 1.0)
    # el DataFrame trae las columnas nuevas y las métricas obligatorias
    assert {"Pata", "FX"} <= set(df.columns) and df[hw._REQUIRED].notna().all().all()


def test_cierre_completo_lleva_la_tir_de_la_pata() -> None:
    _seed_al30()
    df = hw.build_rows()
    rows = {r["symbol"]: r for r in hw.build_cierre_rows(df)}
    r = rows["MERV - XMEV - AL30C - 24hs"]
    assert r["tirea"] is not None and r["codigo_calc"] == "AL30C" and r["price_ref"] == 66.0
    assert rows["MERV - XMEV - AL30 - 24hs"]["tirea"] == pytest.approx(
        pricing.metrics_for_market_price("AL30D", 95_000.0 / fx_svc.get_fx("24hs").usb,
                                         pricing.settlement_date_str("24hs"))["tirea"], rel=1e-9)


def test_reconstruccion_rearma_las_patas_y_resuelve_el_fx_desde_la_base() -> None:
    dia = date(2026, 10, 7)
    settle = hw._settle_24hs(dia)
    cont = {"sin_fx": 0, "sin_calc": 0}
    sym_c, sym_a = syms.md_symbol("AL30C", "24hs"), syms.md_symbol("AL30", "24hs")
    f = hw._fila_rc("AL30C", sym_c, 66.0, None, dia, settle, {}, lambda: None, cont)
    assert f and f["Pata"] == "CABLE" and f["Price Source"] == "RC" and pd.isna(f["FX"]) if f["FX"] is not None else True
    assert f["TIREA"] == pytest.approx(hw._metricas_a_fecha("AL30D", 66.0, settle)["tirea"], rel=1e-9)
    assert cont == {"sin_fx": 0, "sin_calc": 0}
    # pesos sin FX → no se inventa; con FX → ÷ MEP y el FX en la fila
    assert hw._fila_rc("AL30", sym_a, 95_000.0, None, dia, settle, {}, lambda: None, cont) is None
    assert cont["sin_fx"] == 1
    snap = fx_svc.FxSnapshot(ccl=95_000.0 / 66.0, usb=95_000.0 / 68.0, ccl_base="AL30", usb_base="AL30",
                             canje=68.0 / 66.0 - 1.0, bases=1, as_of=0.0)
    f = hw._fila_rc("AL30", sym_a, 95_000.0, None, dia, settle, {(sym_a, "AL30"): 94_000.0}, lambda: snap, cont)
    assert f["Pata"] == "ARS" and f["FX"] == pytest.approx(95_000.0 / 68.0) and f["Close Price"] == 94_000.0
    assert f["TIREA"] == pytest.approx(hw._metricas_a_fecha("AL30D", 68.0, settle)["tirea"], rel=1e-9)
    # con las tres patas en la base, _fx_desde_filas resuelve CCL y MEP
    filas_sig = [{"Código": "AL30", "symbol": sym_a, "close": 95_000.0},
                 {"Código": "AL30C", "symbol": sym_c, "close": 66.0},
                 {"Código": "AL30D", "symbol": syms.md_symbol("AL30D", "24hs"), "close": 68.0}]
    fx = hw._fx_desde_filas(filas_sig)
    assert fx is not None and fx.usb == pytest.approx(95_000.0 / 68.0) and fx.ccl == pytest.approx(95_000.0 / 66.0)
    rows, info = hw._filas_desde_base(dia, filas_sig, settle, {})
    assert {r["Código"] for r in rows} == {"AL30", "AL30C", "AL30D"} and info["sin_fx"] == 0 and info["sin_calc"] == 0
    assert {r["Pata"] for r in rows} == {"ARS", "CABLE", ""}


def test_filas_desde_feed_incluye_las_patas() -> None:
    _seed_al30()
    hoy = datetime.now(hw._TZ).date()
    rows, info = hw._filas_desde_feed(hoy, hw._settle_24hs(hoy), {})
    cods = {r["Código"] for r in rows}
    assert {"AL30D", "AL30C", "AL30"} <= cods
    assert next(r for r in rows if r["Código"] == "AL30C")["Pata"] == "CABLE"


# ── base + lectores ──────────────────────────────────────────────────────────
@pytest.fixture()
def base_con_patas(tmp_path, monkeypatch):
    monkeypatch.setenv("DELTA_HISTORICO_DIR", str(tmp_path))
    monkeypatch.delenv("DELTA_HISTORICO_PATH", raising=False)
    monkeypatch.delenv("DELTA_BASES_DIR", raising=False)
    xlsx = str(tmp_path / hw.HIST_FILENAME)
    dias = [date(2026, 10, 5) + timedelta(days=i) for i in range(5)]
    for i, d in enumerate(dias):
        # filas "viejas" sin Pata/FX conviven con las nuevas
        vieja = pd.DataFrame([{"symbol": "MERV - XMEV - TX26 - 24hs", "Código": "TX26", "Last Price": 1000.0 + i,
                               "Close Price": 999.0, "Variación %": 0.001, "TIREA": 0.3, "TNA": 0.28, "TEM": 0.02,
                               "Paridad": 0.9, "Duration": 1.1, "Price Source": "LA", "Price Date": _ms(),
                               "fecha_hoy": d}])
        hw.append_and_save(vieja, xlsx)
        nuevas = pd.DataFrame([
            {"symbol": "MERV - XMEV - AL30D - 24hs", "Código": "AL30D", "Last Price": 68.0 + i / 10, "Close Price": 67.9,
             "Variación %": 0.001, "TIREA": 0.105, "TNA": 0.10, "TEM": 0.0083, "Paridad": 0.7, "Duration": 2.4,
             "Price Source": "LA", "Price Date": _ms(), "fecha_hoy": d, "Pata": "", "FX": None},
            {"symbol": "MERV - XMEV - AL30C - 24hs", "Código": "AL30C", "Last Price": 66.0 + i / 10, "Close Price": 65.9,
             "Variación %": 0.001, "TIREA": 0.116, "TNA": 0.11, "TEM": 0.0092, "Paridad": 0.68, "Duration": 2.4,
             "Price Source": "LA", "Price Date": _ms(), "fecha_hoy": d, "Pata": "CABLE", "FX": None},
            {"symbol": "MERV - XMEV - AL30 - 24hs", "Código": "AL30", "Last Price": 95_000.0 + i, "Close Price": 94_000.0,
             "Variación %": 0.01, "TIREA": 0.105, "TNA": 0.10, "TEM": 0.0083, "Paridad": 0.7, "Duration": 2.4,
             "Price Source": "LA", "Price Date": _ms(), "fecha_hoy": d, "Pata": "ARS", "FX": 1397.06}])
        hw.append_and_save(nuevas, xlsx)
        part = pd.DataFrame([{"fecha_hoy": d, "symbol": "MERV - XMEV - AL30C - 24hs", "code": "AL30C", "plazo": "24hs",
                              "last": 66.0 + i / 10, "close": 65.9, "opero": True, "tirea": 0.116 + i / 1000},
                             {"fecha_hoy": d, "symbol": "MERV - XMEV - AL30D - 24hs", "code": "AL30D", "plazo": "24hs",
                              "last": 68.0 + i / 10, "close": 67.9, "opero": True, "tirea": 0.105}])
        for col in ("symbol", "code", "plazo"):
            part[col] = part[col].astype("string")
        hw.escribir_particion(part, str(tmp_path), d)
    from backend.services import base_export
    from backend.routes import historico as rh
    base_export.invalidar()
    historico_byma.refresh()
    fx_hist.refresh()
    cierres.refresh()
    cierres.ensure_loaded()
    rh._GRUPOS_CACHE = None
    rh._BASE_CACHE.clear()
    yield tmp_path, dias
    base_export.invalidar()
    historico_byma.refresh()
    cierres.refresh()
    rh._GRUPOS_CACHE = None
    rh._BASE_CACHE.clear()


def test_base_guarda_las_columnas_nuevas_y_el_lector_no_pisa_patas(base_con_patas) -> None:
    tmp, dias = base_con_patas
    pq = pd.read_parquet(tmp / hw.HIST_FILENAME.replace(".xlsx", ".parquet"))
    assert str(pq["Pata"].dtype) == "string" and str(pq["FX"].dtype) == "float64"
    assert set(pq.loc[pq["Código"] == "AL30C", "Pata"]) == {"CABLE"} and pq.loc[pq["Código"] == "TX26", "Pata"].isna().all()
    assert pq.loc[pq["Código"] == "AL30", "FX"].eq(1397.06).all()
    xl = pd.read_excel(tmp / hw.HIST_FILENAME)
    assert "Pata" in xl.columns and "FX" in xl.columns and len(xl) == 20
    # historico_byma: una serie por Código → las tres patas conviven
    assert set(historico_byma.codigos()) == {"TX26", "AL30D", "AL30C", "AL30"}
    f, v = historico_byma.serie_codigo("AL30C", "TIREA")
    assert len(f) == 5 and v[0] == pytest.approx(0.116)
    f, v = historico_byma.serie_codigo("AL30", "Last Price")
    assert len(f) == 5 and v[-1] == 95_004.0


def test_lectores_resuelven_una_pata_sin_ficha(base_con_patas) -> None:
    from backend.routes import historico as rh
    assert not pricing.bond_meta("AL30C")
    s = price_action.serie_de("al30c", "precio")
    assert s and s["ticker"] == "AL30C" and s["fuente"] == "cierres" and len(s["fechas"]) == 5
    s = price_action.serie_de("AL30C", "tir")
    assert s and s["fuente"] == "cierres" and s["ultimo"][-1] == pytest.approx(11.6 + 0.4)   # ×100, último
    s = price_action.serie_de("AL30", "tir")                     # pesos: ficha propia, desde la base
    assert s and s["fuente"] == "base" and s["ultimo"][-1] == pytest.approx(10.5)
    assert price_action.serie_de("YM34C", "precio") is None     # corporativo sin historia: igual que antes
    a = price_action.analizar("AL30C", campo="tir", dias=30)
    assert a["ok"], a.get("motivo")
    grupos, nombres = rh._grupos_especies()
    etiquetas = [g for g, _ in grupos]
    assert "Bonos · patas pesos / C / D (soberanos)" in etiquetas
    assert "AL30C" in nombres and "AL30" in nombres and "AL30D" in nombres


@pytest.mark.asyncio
async def test_http_pestana_base_muestra_la_pata(base_con_patas) -> None:
    from httpx import ASGITransport, AsyncClient
    from backend.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/historicos/base?codigo=AL30C")
        assert r.status_code == 200
        tabla = r.text.split('id="base-tbl"')[1]
        assert "<th data-sort>Pata</th>" in tabla and "<td>CABLE</td>" in tabla and "AL30D" not in tabla
        r = await ac.get("/historicos/base.csv?codigo=AL30")
        assert r.status_code == 200 and ";ARS;1397,06" in r.text
        body = await ac.get("/historicos/comp/body", params={"tickers": "AL30C, AL30D", "campo": "tir", "rango": "1m"})
        assert body.status_code == 200 and "AL30C" in body.text
