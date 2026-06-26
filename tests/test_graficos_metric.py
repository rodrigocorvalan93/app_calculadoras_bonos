"""Gráficos · regresión NSS en TEM (además de TIREA) + filtros de outliers.

Cubre (a) los helpers de métrica/filtro de `routes/curves.py`, (b) `nss.estimate`
en modo TEM (fit en espacio TEM, recupera la TIREA anual para las TNAs) y
(c) los endpoints `/graficos/data|nss|estimate` con `metric`/`dmin`/`exclude`.
"""
from __future__ import annotations

import math

import pytest

from backend.routes import curves as cr
from backend.services import nss


# ── helpers de métrica/filtro ────────────────────────────────────────────────
def test_graf_y_metric() -> None:
    assert cr._graf_y(0.40, "tirea") == pytest.approx(40.0)
    assert cr._graf_y(0.40, "tem") == pytest.approx(((1.40) ** (30 / 360) - 1) * 100)
    # entradas no representables → None
    assert cr._graf_y(None, "tirea") is None
    assert cr._graf_y(float("nan"), "tem") is None
    assert cr._graf_y(-1.5, "tem") is None          # base ≤ 0 (TIR ≤ −100%)
    assert cr._graf_y(-1.5, "tirea") == pytest.approx(-150.0)  # TIREA sí es lineal


def test_parse_dmin_and_exclude() -> None:
    assert cr._parse_dmin("0,3") == pytest.approx(0.3)
    assert cr._parse_dmin("1.5") == pytest.approx(1.5)
    assert cr._parse_dmin("") is None
    assert cr._parse_dmin("x") is None
    assert cr._parse_dmin("-1") is None              # no positiva → ignorada
    assert cr._parse_dmin("0") is None
    assert cr._parse_exclude("T30J6, AL30 tx26") == {"T30J6", "AL30", "TX26"}
    assert cr._parse_exclude("") == set()
    assert cr._parse_exclude(None) == set()


def test_graf_pts_filtra_y_convierte() -> None:
    rows = [
        {"code": "AAA", "duration": 0.2, "tirea": 0.50, "moneda": "ARS"},
        {"code": "BBB", "duration": 1.0, "tirea": 0.40, "moneda": "ARS",
         "tirea_bid": 0.41, "tirea_offer": 0.39},
        {"code": "CCC", "duration": 2.0, "tirea": 0.35, "moneda": "USD"},
        {"code": "DDD", "duration": 3.0, "tirea": float("nan"), "moneda": "ARS"},  # tirea NaN → fuera
    ]
    base = cr._graf_pts(rows, "tirea", None, set())
    assert {p[0] for p in base} == {"AAA", "BBB", "CCC"}        # DDD descartado
    # duration mínima descarta el near-maturity (AAA, dur 0,2)
    assert {p[0] for p in cr._graf_pts(rows, "tirea", 0.5, set())} == {"BBB", "CCC"}
    # exclusión manual por código
    assert {p[0] for p in cr._graf_pts(rows, "tirea", None, {"BBB"})} == {"AAA", "CCC"}
    # bid/offer convertidos a la métrica (BBB en TIREA → 41/39 %)
    bbb = next(p for p in base if p[0] == "BBB")
    assert bbb[2] == pytest.approx(40.0) and bbb[4] == pytest.approx(41.0) and bbb[5] == pytest.approx(39.0)
    # en TEM, la y de BBB es la TEM de su TIREA
    bbb_tem = next(p for p in cr._graf_pts(rows, "tem", None, set()) if p[0] == "BBB")
    assert bbb_tem[2] == pytest.approx(((1.40) ** (30 / 360) - 1) * 100)


def test_graf_pts_margen() -> None:
    rows = [
        {"code": "FLOAT1", "duration": 0.5, "tirea": 0.45, "moneda": "ARS", "margen_tna": 0.04},
        {"code": "FLOAT2", "duration": 1.2, "tirea": 0.46, "moneda": "ARS", "margen_tna": 0.055},
        {"code": "FIJA", "duration": 1.0, "tirea": 0.40, "moneda": "ARS", "margen_tna": float("nan")},
    ]
    pts = cr._graf_pts(rows, "margen", None, set())
    assert {p[0] for p in pts} == {"FLOAT1", "FLOAT2"}        # la tasa fija (margen NaN) queda fuera
    f1 = next(p for p in pts if p[0] == "FLOAT1")
    assert f1[2] == pytest.approx(4.0) and f1[4] is None and f1[5] is None   # 4 pp, sin puntas
    # en métrica yield la tasa fija sí entra (no mira margen_tna)
    assert "FIJA" in {p[0] for p in cr._graf_pts(rows, "tirea", None, set())}


# ── nss.estimate en modo TEM ─────────────────────────────────────────────────
def test_nss_estimate_metric_tem() -> None:
    xs = [0.3, 0.6, 1.0, 1.5, 2.0, 2.8, 3.5, 4.2]
    tirea_pct = [40, 38, 36, 34, 33, 32, 31.5, 31]
    tem_pct = [((1 + t / 100) ** (30 / 360) - 1) * 100 for t in tirea_pct]   # mismas obs, en TEM
    e = nss.estimate(1.5, xs, tem_pct, metric="tem")
    assert e is not None
    # round-trip: la TEM mostrada es la de la TIREA recuperada
    assert e["tem"] == pytest.approx((1 + e["tirea"]) ** (30 / 360) - 1, rel=1e-6)
    assert 0.30 < e["tirea"] < 0.40                  # back-out a TIREA anual sano (~34%)
    assert e["tnas"]["365"] == pytest.approx(e["tirea"])
    # coherencia con el fit en TIREA sobre los mismos bonos (cerca, no idéntico)
    e_t = nss.estimate(1.5, xs, tirea_pct, metric="tirea")
    assert abs(e["tirea"] - e_t["tirea"]) < 0.02


def test_nss_eval_clamped() -> None:
    xs = [0.3, 0.6, 1.0, 1.5, 2.0, 2.8]
    ys = [5.0, 4.5, 4.0, 3.6, 3.3, 3.0]              # margen en pp
    e = nss.eval_clamped(1.0, xs, ys)
    assert e is not None and 2.5 < e["value"] < 5.0 and not e["clamped"]
    e2 = nss.eval_clamped(99.0, xs, ys)              # fuera de rango → clip al máx
    assert e2["clamped"] and e2["duration_used"] == pytest.approx(2.8)


# ── endpoints ────────────────────────────────────────────────────────────────
def _seed_cer():
    from backend.services import bond_universe, curves, marketdata_store as mds, symbols as syms
    bond_universe.ensure_loaded()
    codes = curves.build_curve_codes().get("cer", [])
    if len(codes) < 4:
        pytest.skip("curva CER insuficiente")
    store = mds.get_store()
    for i, c in enumerate(codes):
        store.update_from_md(syms.md_symbol(c, "24hs"),
                             {"LA": {"price": 95.0 + i * 0.7}, "CL": {"price": 94.9 + i * 0.7},
                              "EV": 2e7, "NV": 2e5})
    return codes


@pytest.mark.asyncio
async def test_graficos_data_metric_y_filtros() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    _seed_cer()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        tirea = (await ac.get("/graficos/data?curve=cer&only_quoting=false&metric=tirea")).json()
        tem = (await ac.get("/graficos/data?curve=cer&only_quoting=false&metric=tem")).json()
        none = (await ac.get("/graficos/data?curve=cer&only_quoting=false&dmin=999")).json()

    assert tirea["n"] > 0 and tirea["metric"] == "tirea" and tirea["ylabel"] == "TIREA"
    assert tem["n"] == tirea["n"] and tem["metric"] == "tem" and tem["ylabel"] == "TEM"
    # mismas duraciones, distinta escala: las TEM son menores que las TIREA
    t_ys = [v for v in tirea["ars"] + tirea["usd"] if v is not None]
    m_ys = [v for v in tem["ars"] + tem["usd"] if v is not None]
    assert t_ys and m_ys and max(m_ys) < max(t_ys)
    # duration mínima absurda → sin puntos (filtro aplicado)
    assert none["n"] == 0 and none["xs"] == []


@pytest.mark.asyncio
async def test_graficos_data_exclude_reduce_n() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    _seed_cer()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        full = (await ac.get("/graficos/data?curve=cer&only_quoting=false")).json()
        if full["n"] < 2:
            pytest.skip("pocos bonos con cotización")
        victim = next(c for c in full["codes"] if c)
        less = (await ac.get(f"/graficos/data?curve=cer&only_quoting=false&exclude={victim}")).json()
    assert less["n"] == full["n"] - 1
    assert victim not in [c for c in less["codes"] if c]


@pytest.mark.asyncio
async def test_graficos_data_margen_floaters() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.services import bond_universe, curves, marketdata_store as mds, symbols as syms
    bond_universe.ensure_loaded()
    codes = curves.build_curve_codes().get("corp_tamar", [])
    if len(codes) < 4:
        pytest.skip("curva TAMAR insuficiente")
    store = mds.get_store()
    for i, c in enumerate(codes):
        store.update_from_md(syms.md_symbol(c, "24hs"),
                             {"LA": {"price": 100.0 + i * 0.1}, "CL": {"price": 99.9 + i * 0.1},
                              "EV": 2e7, "NV": 2e5})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        j = (await ac.get("/graficos/data?curve=corp_tamar&only_quoting=false&metric=margen")).json()
        est = await ac.get("/graficos/estimate?curve=corp_tamar&only_quoting=false&duration=1,0&metric=margen")
    assert j["metric"] == "margen" and j["ylabel"] == "Margen TNA" and j["n"] > 0
    ys = [v for v in j["ars"] + j["usd"] if v is not None]
    assert ys and all(v == v for v in ys)            # y de margen, todos finitos
    assert est.status_code == 200 and "argen" in est.text   # card o alerta de margen


@pytest.mark.asyncio
async def test_graficos_nss_y_estimate_tem_http() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    _seed_cer()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        nss_html = await ac.get("/graficos/nss?curve=cer&only_quoting=false&metric=tem")
        est = await ac.get("/graficos/estimate?curve=cer&only_quoting=false&duration=1,5&metric=tem&dmin=0,1")
    assert nss_html.status_code == 200 and "Traceback" not in nss_html.text
    assert est.status_code == 200 and "TIR (TIREA)" in est.text
    # el subtítulo del nss marca el espacio del ajuste cuando hay fit
    if "Curva NSS ajustada" in nss_html.text:
        assert "ajuste en TEM" in nss_html.text
