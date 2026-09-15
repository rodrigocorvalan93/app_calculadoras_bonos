"""Históricos → Acciones (price action): cierre diario de acciones / CEDEARs /
Merval en parquet (writer), lectura cacheada, análisis (canal de tendencia,
mín/máx, percentil/z, retornos, distribución vs normal, ÷ FX, vs Merval),
la pestaña HTTP y el backfill por CSV."""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest
from httpx import ASGITransport, AsyncClient

from backend.services import acciones_hist, equities, fx_hist, historico_writer as hw, price_action

_TZ = ZoneInfo("America/Argentina/Buenos_Aires")


def _ruedas(n: int, fin: date = date(2026, 9, 11)) -> list:
    out, d = [], fin
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return list(reversed(out))


@pytest.fixture()
def base_acciones(tmp_path, monkeypatch):
    monkeypatch.setenv("DELTA_HISTORICO_DIR", str(tmp_path))
    monkeypatch.delenv("DELTA_HISTORICO_PATH", raising=False)
    monkeypatch.delenv("DELTA_BASES_DIR", raising=False)
    dias = _ruedas(130)
    rng = np.random.default_rng(7)
    rows = []
    for t, p0, panel, drift in (("GGAL", 5000.0, "L", 0.002), ("YPFD", 40000.0, "L", 0.0),
                                ("SPY", 30000.0, "C", 0.001), ("MERVAL", 2_000_000.0, "I", 0.0015)):
        px = p0 * np.cumprod(1 + drift + rng.normal(0, 0.02, len(dias)))
        for d, p in zip(dias, px):
            rows.append({"fecha_hoy": d, "ticker": t, "panel": panel, "ultimo": float(p),
                         "apertura": float(p), "maximo": float(p * 1.01), "minimo": float(p * 0.99),
                         "cierre_ant": None, "vwap": float(p), "volumen": 1e9, "nominal": 1e5})
    pd.DataFrame(rows).to_parquet(tmp_path / hw.ACCIONES_FILENAME, index=False)
    # FX diario para las mismas fechas (un hueco de CCL en el 2º día → forward-fill)
    n = len(dias)
    fx = pd.DataFrame({"fecha_hoy": dias, "ccl": [1400.0 + i for i in range(n)],
                       "mep": [1390.0 + i for i in range(n)], "canje": [0.007] * n,
                       "oficial_a3500": [1300.0 + i for i in range(n)], "ccl_base": ["GD30"] * n})
    fx.loc[1, "ccl"] = None
    fx.to_parquet(tmp_path / "Delta - historico_fx.parquet", index=False)
    acciones_hist.refresh()
    fx_hist.refresh()
    yield tmp_path, dias
    acciones_hist.refresh()
    fx_hist.refresh()


# ── lectura ──────────────────────────────────────────────────────────────
def test_reader_indexa_por_ticker_y_ordena_por_panel(base_acciones) -> None:
    st = acciones_hist.status()
    assert st["loaded"] and st["n_tickers"] == 4 and st["n_dias"] == 130 and st["merval"]
    assert [t["ticker"] for t in acciones_hist.tickers()] == ["GGAL", "YPFD", "SPY", "MERVAL"]
    s = acciones_hist.serie("ggal")
    assert s["n"] == 130 and len(s["fechas"]) == 130 and s["panel"] == "L"
    assert acciones_hist.serie("NOEXISTE") is None
    # sin carpeta → nada cargado, la pestaña degrada
    acciones_hist.refresh()


# ── análisis ─────────────────────────────────────────────────────────────
def test_analizar_precio_canal_minmax_percentil(base_acciones) -> None:
    pa = price_action.analizar("GGAL", "ars", "precio", 90)
    assert pa["ok"] and pa["n"] == 90 and pa["n_total"] == 130 and pa["hasta"] == "2026-09-11"
    st = pa["nivel"]
    assert st["min"] <= st["ultimo"] <= st["max"] and 0.0 <= st["percentil"] <= 1.0
    assert st["sigma_tend"] > 0 and st["z_tend"] is not None and st["r2"] is not None
    assert st["mdd"] <= 0.0 and abs(st["ret_ventana"]) < 500
    # retornos: 90 (el primero contra la rueda previa a la ventana)
    assert pa["retornos"]["n"] == 90 and pa["retornos"]["vol_anual"] > 0
    g = pa["geom"]
    assert g["modo"] == "precio" and g["band1"] and g["band2"] and g["poly"].count(",") == 90
    assert g["overlay"] and len(g["xlabels"]) == 5
    # histograma de niveles: las cuentas suman las 90 ruedas, normal con μ/σ
    h = pa["hist"]
    assert sum(h["counts"]) == 90 and h["sd"] > 0 and 0 < h["dentro_1s"] <= 100
    assert pa["geom_hist"]["bars"] and pa["geom_hist"]["curva"]
    # tabla: más reciente primero, Δ real
    t = pa["tabla"]
    assert t[0]["fecha"] == "2026-09-11" and t[-1]["var"] is not None and len(t) == 90
    # vs Merval
    c = pa["cmp"]
    assert c["n"] == 90 and c["beta"] is not None and -1 <= c["corr"] <= 1
    assert "_overlay" not in c and "_tend" not in st


def test_analizar_retornos_ventanas_y_errores(base_acciones) -> None:
    pa = price_action.analizar("YPFD", "ars", "retornos", 60)
    assert pa["ok"] and pa["modo"] == "retornos"
    g = pa["geom"]
    assert len(g["bars"]) == 60 and len(g["lineas"]) == 5 and g["zero_y"]
    assert sum(pa["hist"]["counts"]) == 60                     # histograma de retornos
    # desde/hasta tienen prioridad sobre la ventana
    r = price_action.analizar("YPFD", "ars", "precio", 30, "2026-08-03", "2026-08-14")
    assert r["ok"] and r["desde"] == "2026-08-03" and r["hasta"] == "2026-08-14" and r["n"] == 10
    # "todo"
    assert price_action.analizar("YPFD", "ars", "precio", 0)["n"] == 130
    # errores claros
    assert not price_action.analizar("NOEXISTE")["ok"]
    assert "ruedas" in price_action.analizar("YPFD", "ars", "precio", 30, "2030-01-01", "2030-01-02")["motivo"]
    # el Merval no se compara consigo mismo; comparar=False tampoco
    assert price_action.analizar("MERVAL")["cmp"] is None
    assert price_action.analizar("GGAL", comparar=False)["cmp"] is None


def test_analizar_dividido_por_fx(base_acciones, monkeypatch) -> None:
    from backend.services import historico
    dias = base_acciones[1]
    ggal = acciones_hist.serie("GGAL")
    # ÷ CCL: el último = precio / CCL del mismo día; el hueco del 2º día se
    # rellena con el CCL previo (forward-fill acotado) → no se pierde la rueda
    pa = price_action.analizar("GGAL", "ccl", "precio", 0)
    assert pa["ok"] and pa["n"] == 130 and pa["base_label"] == "÷ CCL"
    assert pa["nivel"]["ultimo"] == pytest.approx(float(ggal["ultimo"][-1]) / (1400.0 + 129))
    assert pa["tabla"][-2]["valor"] == pytest.approx(float(ggal["ultimo"][1]) / 1400.0)   # 2º día: CCL del 1º
    # el Merval se divide por el MISMO FX → β/ρ siguen calculándose
    assert pa["cmp"]["n"] == 130
    # ÷ MEP y ÷ A3500 (BCRA vacío → cae al oficial del archivo FX)
    assert price_action.analizar("GGAL", "mep")["nivel"]["ultimo"] == pytest.approx(float(ggal["ultimo"][-1]) / (1390.0 + 129))
    monkeypatch.setattr(historico, "series_points", lambda *a, **k: {"label": "", "points": []})
    a35 = price_action.analizar("GGAL", "a3500")
    assert a35["ok"] and a35["nivel"]["ultimo"] == pytest.approx(float(ggal["ultimo"][-1]) / (1300.0 + 129))
    # A3500 del BCRA cuando existe (gana sobre el archivo)
    monkeypatch.setattr(historico, "series_points",
                        lambda *a, **k: {"label": "A3500", "points": [[d.isoformat(), 1000.0] for d in dias]})
    assert price_action.analizar("GGAL", "a3500")["nivel"]["ultimo"] == pytest.approx(float(ggal["ultimo"][-1]) / 1000.0)
    # sin serie FX en esas fechas → motivo claro, no explota
    monkeypatch.setattr(price_action, "fx_por_fecha", lambda base: {"2020-01-01": 100.0})
    r = price_action.analizar("GGAL", "ccl")
    assert not r["ok"] and "÷ CCL" in r["motivo"]


def _particiones_bono(env_dir, dias, code: str = "TX26", p0: float = 1500.0, t0: float = 0.30) -> None:
    """Particiones del cierre completo para un bono: precio lineal (+2 por
    rueda) y TIREA lineal (+0,1 pp por rueda), con nominal."""
    from backend.services import cierres
    sym = f"MERV - XMEV - {code} - 24hs"
    for i, d in enumerate(dias):
        df = pd.DataFrame([{"fecha_hoy": d, "symbol": sym, "code": code, "plazo": "24hs",
                            "last": p0 + i * 2.0, "close": p0 + i * 2.0 - 1.0, "opero": True,
                            "tirea": t0 + i * 0.001, "nominal": 5e5 + i}])
        for col in ("symbol", "code", "plazo"):
            df[col] = df[col].astype("string")
        hw.escribir_particion(df, str(env_dir), d)
    cierres.refresh()


def test_bonos_precio_y_tir(base_acciones, monkeypatch) -> None:
    from backend.services import cierres, historico_byma as hb
    tmp, dias = base_acciones
    _particiones_bono(tmp, dias[-40:])
    try:
        pa = price_action.analizar("TX26", "ars", "precio", 30)
        assert pa["ok"] and pa["fuente"] == "cierres" and pa["panel"] == "B" and not pa["es_tir"]
        assert pa["n"] == 30 and pa["nivel"]["ultimo"] == pytest.approx(1500.0 + 39 * 2.0)
        assert pa["cmp"] is None                                   # bonos: sin Merval
        assert pa["tabla"][0]["volumen"] == pytest.approx(5e5 + 39)
        assert pa["nivel"]["mdd"] is not None and pa["u_delta"] == "%"
        # TIR: nivel en %, Δ en pp, sin ÷ FX, sin drawdown, pendiente en pp/rueda
        pt = price_action.analizar("TX26", "ccl", "retornos", 30, campo="tir")
        assert pt["ok"] and pt["es_tir"] and pt["base"] == "ars" and pt["u_delta"] == " pp" and pt["u_nivel"] == "%"
        assert pt["nivel"]["ultimo"] == pytest.approx((0.30 + 39 * 0.001) * 100)
        assert pt["nivel"]["ret_ventana"] == pytest.approx(29 * 0.1)
        assert pt["nivel"]["mdd"] is None and pt["nivel"]["pend_pct"] == pytest.approx(0.1, abs=1e-6)
        assert pt["retornos"]["n"] == 30 and pt["retornos"]["media"] == pytest.approx(0.1)
        assert pt["tabla"][0]["var"] == pytest.approx(0.1, abs=1e-9) and pt["tabla"][0]["var_pct"] is None
        assert sum(pt["hist"]["counts"]) == 30 and pt["geom"]["modo"] == "retornos"
        # sin cierre completo para el bono → cae a la base px/tasas (precio y TIR)
        hb._cache = {"loaded": True, "ver": "t", "by_code": {"TX28": {
            "base": "TX28", "dates": [d.isoformat() for d in dias[-20:]],
            "vals": {"Last Price": [100.0 + i for i in range(20)], "TIREA": [0.4 + i / 1000 for i in range(20)]}}}}
        try:
            assert hb.codigos() == ["TX28"]
            pb = price_action.analizar("TX28", "ars", "precio", 10)
            assert pb["ok"] and pb["fuente"] == "base" and pb["nivel"]["ultimo"] == 119.0 and pb["n"] == 10
            pbt = price_action.analizar("TX28", campo="tir")
            assert pbt["ok"] and pbt["fuente"] == "base" and pbt["nivel"]["ultimo"] == pytest.approx(41.9)
            # proyectado (…j): la TIR va por la base (el cierre completo guarda la variante base)
            from backend.services import bond_universe
            jc = next((c for c in bond_universe.all_codes() if c.endswith("j")), None)
            if jc:
                hb._cache["by_code"][jc] = {"base": jc[:-1], "dates": [d.isoformat() for d in dias[-20:]],
                                            "vals": {"TIREA": [0.2] * 20, "Last Price": [1.0] * 20}}
                pj = price_action.analizar(jc, campo="tir")
                assert pj["ok"] and pj["fuente"] == "base" and pj["nivel"]["ultimo"] == pytest.approx(20.0)
        finally:
            hb._cache = None
        # una acción no tiene TIR; un ticker sin ficha ni serie → motivo claro
        r = price_action.analizar("GGAL", campo="tir")
        assert not r["ok"] and "TIR" in r["motivo"]
        assert not price_action.analizar("ZZZZ9")["ok"]
    finally:
        cierres.refresh()


def test_series_planas_no_cuelgan(base_acciones) -> None:
    """Serie plana (precio que no operó / TIR fija): el ajuste lineal deja
    residuos de ~1e-14 en el canal ±σ y `_nice_ticks` elegía un paso menor
    al ULP del nivel → `v += step` no avanzaba (loop infinito en CI con
    numpy 2.5). Ahora: σ = 0 (sin z-scores de ruido), eje de ±1 % alrededor
    del nivel, histograma con ancho y ticks finitos."""
    from backend.services import historico_byma as hb
    from backend.services.svg_charts import _nice_ticks
    assert _nice_ticks(0.0, 1.0, 5) == [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
    assert _nice_ticks(20.0, 20.0) == [20.0]
    assert _nice_ticks(19.99999999999999, 20.0) == [19.99999999999999]     # rango = ruido
    assert _nice_ticks(20.0 - 3.552713678800501e-15, 20.0 + 1e-15) == [20.0 - 3.552713678800501e-15]
    assert 3 <= len(_nice_ticks(1234.5, 1259.19, 5)) <= 8
    _, dias = base_acciones
    fechas = [d.isoformat() for d in dias[-40:]]
    hb._cache = {"loaded": True, "ver": "t", "by_code": {"TX28": {
        "base": "TX28", "dates": fechas,
        "vals": {"Last Price": [1234.5] * 40, "TIREA": [0.2] * 40}}}}
    try:
        for n in (20, 40):
            for campo, modo in (("precio", "precio"), ("precio", "retornos"), ("tir", "precio"), ("tir", "retornos")):
                r = price_action.analizar("TX28", "ars", modo, n, campo=campo)
                assert r["ok"] and r["n"] == n and r["fuente"] == "base", (n, campo, modo, r.get("motivo"))
                nv = r["nivel"]
                assert nv["sigma_tend"] == 0.0 and nv["z_tend"] is None and nv["z"] is None and nv["desvio"] == 0.0
                assert nv["ultimo"] == pytest.approx(20.0 if campo == "tir" else 1234.5)
                assert r["retornos"]["desvio"] == 0.0 and r["retornos"]["vol_anual"] is None
                assert r["retornos"]["z_ultimo"] is None and r["retornos"]["skew"] is None
                g = r["geom"]
                assert g["modo"] == modo and 1 <= len(g["yticks"]) <= 12
                assert all(math.isfinite(t["v"]) and math.isfinite(t["y"]) for t in g["yticks"])
                if modo == "precio":
                    assert g["band1"] is None and g["band2"] is None
                    lo_t, hi_t = g["yticks"][0]["v"], g["yticks"][-1]["v"]
                    assert lo_t <= nv["ultimo"] <= hi_t and hi_t - lo_t < nv["ultimo"] * 0.03
                h = r["hist"]
                assert h["sd"] == 0.0 and h["hi"] > h["lo"] and sum(h["counts"]) == h["n"]
                assert all(math.isfinite(float(x)) for x in r["geom_hist"]["curva"].replace(",", " ").split())
    finally:
        hb._cache = None


# ── writer: filas del día desde el store + append con dedup ──────────────
def test_build_rows_y_append_dedup(tmp_path, monkeypatch) -> None:
    from backend.services import marketdata_store

    store = marketdata_store.get_store()
    ahora = datetime.now(_TZ)
    hoy_ms = str(int(ahora.timestamp() * 1000))
    ayer_ms = str(int((ahora - timedelta(days=1)).timestamp() * 1000))
    store.update_from_md("MERV - XMEV - GGAL - 24hs", {
        "LA": {"price": 5100.0, "size": 10, "date": hoy_ms}, "OP": 5000.0, "HI": 5150.0, "LO": 4980.0,
        "CL": 5050.0, "EV": 2.5e9, "NV": 5e5})
    store.update_from_md("MERV - XMEV - YPFD - 24hs", {"LA": {"price": 41000.0, "size": 1, "date": ayer_ms}})
    store.update_from_md("MERV - XMEV - I.MERVAL - 24hs", {"IV": {"price": 2_100_000.0, "date": hoy_ms}})
    monkeypatch.setattr(equities, "_merval_sym", None)
    rows = hw.build_acciones_rows()
    por = {r["ticker"]: r for r in rows}
    assert "GGAL" in por and "MERVAL" in por and "YPFD" not in por     # YPFD: last de ayer (pegajoso)
    g = por["GGAL"]
    assert g["panel"] == "L" and g["ultimo"] == 5100.0 and g["maximo"] == 5150.0
    assert g["vwap"] == pytest.approx(2.5e9 / 5e5) and g["volumen"] == 2.5e9
    assert por["MERVAL"]["panel"] == "I" and por["MERVAL"]["ultimo"] == 2_100_000.0
    # append: dedup por (fecha, ticker) y la nueva pisa a la vieja
    pq = str(tmp_path / hw.ACCIONES_FILENAME)
    r1 = hw.append_acciones(pd.DataFrame([g]), pq)
    g2 = dict(g, ultimo=5200.0)
    r2 = hw.append_acciones(pd.DataFrame([g2]), pq)
    assert r1["filas"] == 1 and r2["filas"] == 1 and r2["hoy"] == 1
    assert pd.read_parquet(pq)["ultimo"].iloc[0] == 5200.0
    # backfill: lo que ya capturó la app gana
    viejo = dict(g, ultimo=1.0)
    r3 = hw.append_acciones(pd.DataFrame([viejo, dict(g, fecha_hoy=date(2026, 1, 5), ultimo=3000.0)]),
                            pq, gana_previo=True)
    df = pd.read_parquet(pq)
    assert r3["filas"] == 2 and float(df[df["fecha_hoy"] == ahora.date()]["ultimo"].iloc[0]) == 5200.0
    # el reader lo ve
    monkeypatch.setenv("DELTA_HISTORICO_DIR", str(tmp_path))
    acciones_hist.refresh()
    try:
        assert acciones_hist.serie("GGAL")["n"] == 2
    finally:
        acciones_hist.refresh()


# ── HTTP ─────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_http_pestana_acciones(base_acciones, monkeypatch) -> None:
    from backend.main import app
    from backend.routes import historico as rh

    rh._AC_CACHE.clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        page = await ac.get("/historicos")
        assert page.status_code == 200
        assert 'id="hist-acciones"' in page.text and "Acciones (price action)" in page.text
        assert 'hx-get="/historicos/acciones"' in page.text
        r = await ac.get("/historicos/acciones", params={"ticker": "GGAL", "dias": "90"})
        assert r.status_code == 200
        for frag in ('name="ticker"', 'name="base"', 'name="modo"', 'name="cmp"', "pa-band1", "pa-band2",
                     "pa-tend", "pa-overlay", "Distribución vs normal", "pa-normal", "pa-hist",
                     'id="pa-tbl"', "vs Merval", 'value="GGAL" selected', "canal de tendencia"):
            assert frag in r.text, frag
        assert r.text.count("<svg") == 2
        # cache: misma combinación → mismo HTML sin recomputar
        r2 = await ac.get("/historicos/acciones", params={"ticker": "GGAL", "dias": "90"})
        assert r2.text == r.text and len(rh._AC_CACHE) >= 1
        # retornos: barras + líneas ±σ; ÷ CCL en el título y la tabla
        rr = await ac.get("/historicos/acciones", params={"ticker": "SPY", "modo": "retornos", "base": "ccl", "cmp": "0"})
        assert rr.status_code == 200 and "pa-bar" in rr.text and "pa-sig2" in rr.text
        assert "÷ CCL" in rr.text and "retornos diarios" in rr.text and "pa-overlay" not in rr.text
        # ticker desconocido → default (GGAL) sin romper; ventana imposible → aviso
        rd = await ac.get("/historicos/acciones", params={"ticker": "NOEXISTE"})
        assert rd.status_code == 200 and 'value="GGAL" selected' in rd.text
        rv = await ac.get("/historicos/acciones", params={"ticker": "GGAL", "desde": "2030-01-01"})
        assert rv.status_code == 200 and "ruedas" in rv.text and "<svg" not in rv.text
        # bonos: entran por el cierre completo (precio) y con campo=tir la TIR en pp
        from backend.services import cierres
        _particiones_bono(base_acciones[0], base_acciones[1][-40:])
        rh._GRUPOS_CACHE = ()
        rh._AC_CACHE.clear()
        rb = await ac.get("/historicos/acciones", params={"ticker": "TX26", "campo": "tir", "dias": "30"})
        assert rb.status_code == 200 and "Bonos ·" in rb.text and 'value="TX26" selected' in rb.text
        assert 'name="campo"' in rb.text and 'value="tir" selected' in rb.text
        for frag in ("TX26 · TIR", "Δ TIR en la ventana", " pp", "no aplica a bonos", "canal de tendencia"):
            assert frag in rb.text, frag
        rp = await ac.get("/historicos/acciones", params={"ticker": "TX26", "dias": "30"})
        assert rp.status_code == 200 and "TX26 · último" in rp.text and "precio ARS" in rp.text
        # sin archivos → aviso con el backfill, sin form
        rh._AC_CACHE.clear()
        rh._GRUPOS_CACHE = ()
        monkeypatch.setenv("DELTA_HISTORICO_DIR", str(base_acciones[0] / "vacio"))
        (base_acciones[0] / "vacio").mkdir()
        acciones_hist.refresh()
        cierres.refresh()
        rs = await ac.get("/historicos/acciones")
        assert rs.status_code == 200 and "Todavía no hay series" in rs.text and "backfill_acciones" in rs.text


# ── backfill CSV ─────────────────────────────────────────────────────────
def test_backfill_csv(tmp_path) -> None:
    from backend.tools import backfill_acciones as bf

    csv = tmp_path / "cierres.csv"
    csv.write_text("Fecha;Ticker;Cierre;Volumen\n10/09/2026;ggal;5.432,50;1.000.000\n"
                   "2026-09-11;GGAL;5500;\n11/09/2026;MERVAL;2.100.000,5;\nbasura;;;\n", encoding="utf-8")
    df = bf.importar_csv(str(csv))
    assert len(df) == 3 and set(df["ticker"]) == {"GGAL", "MERVAL"}
    g = df[df["ticker"] == "GGAL"].sort_values("fecha_hoy")
    assert g["ultimo"].tolist() == [5432.5, 5500.0] and g["volumen"].iloc[0] == 1_000_000.0
    assert g["fecha_hoy"].iloc[0] == date(2026, 9, 10) and g["panel"].iloc[0] == "L"
    assert df[df["ticker"] == "MERVAL"]["panel"].iloc[0] == "I"
    # UDF de BYMA → filas; formatos raros → vacío sin explotar
    udf = {"s": "ok", "t": [1757548800, 1757635200], "c": [5400.0, 5500.0], "v": [1e6, None]}
    filas = bf._parse_udf(udf)
    assert [r["ultimo"] for r in filas] == [5400.0, 5500.0] and filas[1]["volumen"] is None
    assert bf._parse_udf({"s": "no_data"}) == [] and bf._parse_udf("x") == []
