"""Históricos → Comparar (COMP): varios activos en un gráfico, rebasados a 100
(o variación % / nivel), alineados a la unión de ruedas, con cuadro del rango;
la pestaña HTTP (controles + cuerpo) y su cache por firma."""
from __future__ import annotations

import json
import re
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from httpx import ASGITransport, AsyncClient

from backend.services import acciones_hist, bond_universe, cierres, comp, fx_hist, historico_writer as hw


def _ruedas(n: int, fin: date = date(2026, 9, 11)) -> list:
    out, d = [], fin
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return list(reversed(out))


@pytest.fixture()
def base_comp(tmp_path, monkeypatch):
    """Acciones (GGAL / YPFD / SPY / MERVAL, 130 ruedas), FX diario (CCL con un
    hueco) y un bono (TX26) en el cierre completo SÓLO en ruedas alternadas de
    las últimas 60 — para probar la unión de fechas y los huecos."""
    monkeypatch.setenv("DELTA_HISTORICO_DIR", str(tmp_path))
    monkeypatch.delenv("DELTA_HISTORICO_PATH", raising=False)
    monkeypatch.delenv("DELTA_BASES_DIR", raising=False)
    dias = _ruedas(130)
    rng = np.random.default_rng(11)
    rows = []
    for t, p0, panel, drift in (("GGAL", 5000.0, "L", 0.002), ("YPFD", 40000.0, "L", 0.0),
                                ("SPY", 30000.0, "C", 0.001), ("MERVAL", 2_000_000.0, "I", 0.0015)):
        px = p0 * np.cumprod(1 + drift + rng.normal(0, 0.02, len(dias)))
        for d, p in zip(dias, px):
            rows.append({"fecha_hoy": d, "ticker": t, "panel": panel, "ultimo": float(p),
                         "apertura": float(p), "maximo": float(p * 1.01), "minimo": float(p * 0.99),
                         "cierre_ant": None, "vwap": float(p), "volumen": 1e9, "nominal": 1e5})
    pd.DataFrame(rows).to_parquet(tmp_path / hw.ACCIONES_FILENAME, index=False)
    n = len(dias)
    fx = pd.DataFrame({"fecha_hoy": dias, "ccl": [1400.0 + i for i in range(n)],
                       "mep": [1390.0 + i for i in range(n)], "canje": [0.007] * n,
                       "oficial_a3500": [1300.0 + i for i in range(n)], "ccl_base": ["GD30"] * n})
    fx.loc[1, "ccl"] = None
    fx.to_parquet(tmp_path / "Delta - historico_fx.parquet", index=False)
    # bono en el cierre completo: ruedas alternadas de las últimas 60
    bono_dias = dias[-60::2]
    for i, d in enumerate(bono_dias):
        df = pd.DataFrame([{"fecha_hoy": d, "symbol": "MERV - XMEV - TX26 - 24hs", "code": "TX26", "plazo": "24hs",
                            "last": 1000.0 + 5.0 * i, "close": 1000.0 + 5.0 * (i - 1), "opero": True,
                            "tirea": 0.30 + i / 1000.0}])
        for col in ("symbol", "code", "plazo"):
            df[col] = df[col].astype("string")
        hw.escribir_particion(df, str(tmp_path), d)
    bond_universe.ensure_loaded()
    acciones_hist.refresh()
    fx_hist.refresh()
    cierres.refresh()
    cierres.ensure_loaded()
    yield tmp_path, dias, bono_dias
    acciones_hist.refresh()
    fx_hist.refresh()
    cierres.refresh()


def test_parse_y_default_tickers() -> None:
    assert comp.parse_tickers("GGAL, al30d TX26 ggal;SPY") == ["GGAL", "al30d", "TX26", "SPY"]
    assert comp.parse_tickers("") == [] and comp.parse_tickers(None) == []
    assert len(comp.parse_tickers(" ".join(f"T{i}" for i in range(30)))) == comp.MAX_TICKERS
    assert comp.default_tickers(["AL30D", "GGAL", "MERVAL", "YPFD"]) == ["GGAL", "YPFD", "MERVAL"]
    assert comp.default_tickers(["AL30D", "TX26", "ZZ"]) == ["AL30D", "TX26"]
    assert comp.default_tickers(["A", "B", "C"]) == ["A", "B"] and comp.default_tickers([]) == []


def test_comparar_base100_union_y_stats(base_comp) -> None:
    _, dias, bono_dias = base_comp
    r = comp.comparar(["GGAL", "SPY", "TX26", "NOEXISTE"], rango="3m")
    assert r["ok"] and r["faltantes"] == ["NOEXISTE"] and r["sin_rango"] == []
    assert [s["ticker"] for s in r["series"]] == ["GGAL", "SPY", "TX26"]
    assert r["modo"] == "base" and r["campo"] == "precio" and r["base"] == "ars"
    # unión de ruedas: 92 días calendario hacia atrás desde la última rueda, todas con dato de acciones
    fin = dias[-1]
    esperadas = [d for d in dias if d >= fin - timedelta(days=92)]
    assert r["fechas"] == [d.isoformat() for d in esperadas] and r["n"] == len(esperadas)
    assert len(r["x"]) == r["n"] and r["x"] == sorted(r["x"])
    for s in r["series"]:
        assert len(s["y"]) == r["n"]
        primero = next(v for v in s["y"] if v is not None)
        assert primero == pytest.approx(100.0)
    # el bono sólo tiene ruedas alternadas → null en las que faltan, y su rebase
    # es en SU primera rueda con dato del rango
    tx = r["series"][2]
    assert tx["fuente"] == "cierres" and tx["fuente_label"] == "Cierre completo"
    assert any(v is None for v in tx["y"]) and tx["stats"]["desde"] >= esperadas[0].isoformat()
    st = tx["stats"]
    assert st["var_pct"] == pytest.approx((st["fin"] / st["inicio"] - 1.0) * 100.0)
    assert st["max"] == st["fin"] and st["min"] == st["inicio"] and st["dd_pct"] == pytest.approx(0.0)
    assert st["n"] == len([d for d in bono_dias if d >= esperadas[0]])
    # acciones: la serie rebasada es precio / precio inicial × 100
    g = r["series"][0]
    assert g["fuente"] == "acciones" and g["stats"]["vol_anual"] is not None and g["stats"]["vol_anual"] > 0
    assert g["y"][-1] == pytest.approx(g["stats"]["fin"] / g["stats"]["inicio"] * 100.0, rel=1e-5)
    assert all(a["color"] != b["color"] for a, b in zip(r["series"], r["series"][1:]))


def test_comparar_modos_moneda_y_tir(base_comp) -> None:
    # variación %: arranca en 0; nivel: precio tal cual
    p = comp.comparar(["GGAL"], modo="pct", rango="1m")
    assert next(v for v in p["series"][0]["y"] if v is not None) == pytest.approx(0.0)
    n = comp.comparar(["GGAL"], modo="nivel", rango="1m")
    assert n["series"][0]["y"][0] == pytest.approx(n["series"][0]["stats"]["inicio"])
    # ÷ CCL: el nivel queda dividido por el FX del día (con forward-fill en el hueco)
    a = comp.comparar(["GGAL"], modo="nivel", rango="todo")
    c = comp.comparar(["GGAL"], modo="nivel", base="ccl", rango="todo")
    assert c["base"] == "ccl" and c["series"][0]["y"][0] == pytest.approx(a["series"][0]["y"][0] / 1400.0)
    assert c["series"][0]["y"][1] == pytest.approx(a["series"][0]["y"][1] / 1400.0)     # hueco → FX anterior
    assert c["series"][0]["y"][2] == pytest.approx(a["series"][0]["y"][2] / 1402.0)
    # desde/hasta mandan sobre el rango
    d0, d1 = a["fechas"][10], a["fechas"][20]
    w = comp.comparar(["GGAL", "SPY"], rango="1m", desde=d0, hasta=d1)
    assert w["fechas"][0] == d0 and w["fechas"][-1] == d1 and w["n"] == 11
    # TIR (bonos): nivel en %, Δ en pp, sin ÷ FX ni vol; una acción no tiene TIR
    t = comp.comparar(["TX26", "GGAL"], campo="tir", modo="base", base="ccl", rango="6m")
    assert t["campo"] == "tir" and t["modo"] == "nivel" and t["base"] == "ars"
    assert t["faltantes"] == ["GGAL"] and [s["ticker"] for s in t["series"]] == ["TX26"]
    st = t["series"][0]["stats"]
    assert st["inicio"] == pytest.approx(30.0 + 0.0) or st["inicio"] > 29.0        # 0.30 → 30 %
    assert st["delta_pp"] == pytest.approx(st["fin"] - st["inicio"]) and st["var_pct"] is None
    assert st["vol_anual"] is None and st["dd_pct"] is None
    # nada con historia → ok False, faltantes completos
    z = comp.comparar(["NADA", "TAMPOCO"])
    assert z["ok"] is False and z["faltantes"] == ["NADA", "TAMPOCO"] and z["series"] == []


@pytest.mark.asyncio
async def test_http_comp_pestana_cuerpo_y_cache(base_comp) -> None:
    from backend.main import app
    from backend.routes import historico as rh

    rh._COMP_CACHE.clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        page = await ac.get("/historicos")
        assert page.status_code == 200 and 'id="hist-comp"' in page.text and "Comparar (COMP)" in page.text
        full = await ac.get("/historicos/comp")
        assert full.status_code == 200
        # controles + datalist con las especies con historia + cuerpo con el JSON embebido
        assert 'id="hc-comp-form"' in full.text and 'hx-get="/historicos/comp/body"' in full.text
        assert '<datalist id="hc-comp-list">' in full.text and '<option value="TX26">' in full.text
        assert 'value="GGAL YPFD MERVAL"' in full.text                    # default: líderes + Merval
        m = re.search(r'<script type="application/json" id="hist-comp-data">(.*?)</script>', full.text, re.S)
        assert m, "falta el JSON embebido"
        j = json.loads(m.group(1))
        assert j["ok"] and [s["ticker"] for s in j["series"]] == ["GGAL", "YPFD", "MERVAL"]
        assert 'id="comp-tbl"' in full.text and "comp-dot" in full.text
        # el cuerpo solo, con activos elegidos y un ticker sin historia
        body = await ac.get("/historicos/comp/body", params={"tickers": "ggal, TX26 NOEXISTE", "modo": "pct", "rango": "3m"})
        assert body.status_code == 200 and "<datalist" not in body.text
        assert "Sin historia guardada para <b>NOEXISTE</b>" in body.text
        assert 'id="hist-comp-uplot"' in body.text and "Variación %" in body.text
        m2 = re.search(r'id="hist-comp-data">(.*?)</script>', body.text, re.S)
        j2 = json.loads(m2.group(1))
        assert j2["modo"] == "pct" and [s["ticker"] for s in j2["series"]] == ["GGAL", "TX26"]
        assert "var-cell" in body.text                                     # Var % con barrita
        # TIR: columna Δ pp y sin Desde máx / Vol
        tir = await ac.get("/historicos/comp/body", params={"tickers": "TX26", "campo": "tir"})
        assert tir.status_code == 200 and "Δ pp" in tir.text and "Desde máx" not in tir.text
        # cache por parámetros normalizados (mismo set en otro orden de mayúsculas → mismo HTML)
        again = await ac.get("/historicos/comp/body", params={"tickers": "GGAL TX26 NOEXISTE", "modo": "pct", "rango": "3m"})
        assert again.text == body.text
        assert any(k[1] == "GGAL TX26 NOEXISTE" for k in rh._COMP_CACHE)
        # parámetros inválidos caen a defaults, nunca 500
        raro = await ac.get("/historicos/comp/body", params={"tickers": "GGAL", "modo": "x", "rango": "y", "base": "z", "desde": "ayer"})
        assert raro.status_code == 200 and "Base 100" in raro.text
