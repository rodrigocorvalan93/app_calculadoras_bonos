"""Gráficos: tramos dmin/dmax, overlay de segunda curva, fuente CAFCI y
forwards de margen TNA."""
from __future__ import annotations

import pytest

from backend.routes import curves as rc
from backend.services import bond_universe


def _rows_sint(n=8, margen=False):
    out = []
    for i in range(n):
        r = {"code": f"B{i}", "tirea": 0.30 + 0.01 * i, "duration": 0.5 + 0.5 * i,
             "moneda": "ARS", "tirea_bid": None, "tirea_offer": None, "volume": 100.0}
        if margen:
            r["margen_tna"] = 0.04 + 0.005 * i
        out.append(r)
    return out


def test_graf_pts_dmax_corta_el_tramo() -> None:
    rows = _rows_sint(8)
    pts = rc._graf_pts(rows, "tirea", 1.0, set(), 3.0)     # tramo 1y–3y
    assert pts and all(1.0 <= p[1] <= 3.0 for p in pts)
    assert len(pts) < 8


def test_forwards_matrix_margen_lineal() -> None:
    rows = _rows_sint(3, margen=True)
    m = rc._forwards_matrix(rows, metric="margen")
    assert m["n"] == 3
    # celda (0,1): (m2·t2 − m1·t1)/(t2 − t1)
    m1, t1 = 0.04, 0.5
    m2, t2 = 0.045, 1.0
    esperado = (m2 * t2 - m1 * t1) / (t2 - t1)
    txt = m["rows"][0]["cells"][1]["txt"]
    assert txt != "·"
    from backend.locale_ar import fmt_pct
    assert txt == fmt_pct(esperado, 2)
    # sin margen → matriz vacía (no usa la TIR de contrabando)
    m0 = rc._forwards_matrix(_rows_sint(3, margen=False), metric="margen")
    assert m0["n"] == 0


def test_graf_pts_cafci(monkeypatch) -> None:
    from backend.services import cafci, curves

    bond_universe.ensure_loaded()
    codes = (curves.build_curve_codes().get("cer") or [])[:3]
    if len(codes) < 3:
        pytest.skip("curva cer chica")
    fake = {"loaded": True, "path": "x.xlsx", "fecha": "20260806",
            "rows": [{"byma": codes[0], "tir": 8.5, "mod_dur": 1.2, "moneda": "U$S"},
                     {"byma": codes[1], "tir": 9.1, "mod_dur": 2.4, "moneda": "$"},
                     {"byma": codes[2], "tir": 7.0, "mod_dur": None, "moneda": "$"},
                     {"byma": "OTRO", "tir": 5.0, "mod_dur": 3.0, "moneda": "$"}]}
    monkeypatch.setattr(cafci, "ensure_loaded", lambda: fake)
    monkeypatch.setattr(rc, "_CAFCI_IDX", None)
    pts = rc._graf_pts_cafci("cer", "tirea", None, None, set())
    assert len(pts) == 2                                    # sin mod_dur queda afuera
    por_code = {p[0]: p for p in pts}
    assert por_code[codes[0]][2] == pytest.approx(8.5)      # TIR % directa
    assert por_code[codes[0]][3] == "USD"                   # U$S → pata USD
    assert por_code[codes[1]][3] == "ARS"
    # margen no aplica al vector
    assert rc._graf_pts_cafci("cer", "margen", None, None, set()) == []
    # dmax también corta acá
    assert len(rc._graf_pts_cafci("cer", "tirea", None, 2.0, set())) == 1


@pytest.mark.asyncio
async def test_graficos_data_overlay_y_fuente(monkeypatch) -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.services import cafci, curves, marketdata_store as mds, symbols as syms

    bond_universe.ensure_loaded()
    table = curves.build_curve_codes()
    for i, c in enumerate((table.get("cer") or [])[:6]):
        mds.get_store().update_from_md(syms.md_symbol(c, "24hs"),
                                       {"LA": {"price": 1100.0 + i * 9}})
    for i, c in enumerate((table.get("lecap") or [])[:6]):
        mds.get_store().update_from_md(syms.md_symbol(c, "24hs"),
                                       {"LA": {"price": 92.0 + i * 2}})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        solo = await ac.get("/graficos/data", params={"curve": "cer"})
        comp = await ac.get("/graficos/data", params={"curve": "cer", "curve2": "lecap"})
        # multi + cap: 'cer' se descarta (== principal), quedan a lo sumo 3
        multi = await ac.get("/graficos/data", params={
            "curve": "cer", "curve2": "lecap,cer,lecap"})
        dm = await ac.get("/graficos/data", params={"curve": "cer", "dmin": "1", "dmax": "3"})
        est = await ac.get("/graficos/estimate",
                           params={"curve": "cer", "duration": "1,5", "dmax": "3"})
    js = solo.json()
    assert solo.status_code == 200 and "ars2" not in js
    assert js.get("cmps") == [] and isinstance(js.get("meta"), dict)   # sola: sin comparaciones
    # meta por punto para el tooltip: cada código tiene tir/dur (u otras claves)
    if js.get("codes"):
        code = next((c for c in js["codes"] if c), None)
        if code:
            assert code in js["meta"] and "tir" in js["meta"][code] and "dur" in js["meta"][code]
    j = comp.json()
    assert comp.status_code == 200
    if j.get("cmps"):                                   # con lecap con data
        c0 = j["cmps"][0]
        assert len(c0["vals"]) == len(j["xs"]) and len(c0["codes"]) == len(j["xs"])
        assert "label" in c0 and len(c0["nss"]) in (0, len(j["xs"]))
    jm = multi.json()
    assert multi.status_code == 200 and len(jm.get("cmps", [])) <= 3   # dedup + cap
    jd = dm.json()
    assert all(1.0 <= x <= 3.0 for x in jd["xs"]) or jd["n"] == 0
    assert est.status_code == 200


@pytest.mark.asyncio
async def test_forwards_table_metric_margen_endpoint() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/forwards/table",
                         params={"curve": "tasa_variable", "fw-metric": "margen"})
        r2 = await ac.get("/forwards/table", params={"curve": "cer", "fw-metric": "margen"})
        page = await ac.get("/forwards", params={"only_quoting": "false"})
    # tasa_variable puede no existir como key — lo importante: nunca 500 y el
    # mensaje/título hablan de MARGEN cuando la métrica es margen.
    assert r.status_code == 200 and r2.status_code == 200
    assert "MARGEN" in r2.text or "margen" in r2.text
    assert page.status_code == 200 and 'name="fw-metric"' in page.text


@pytest.mark.asyncio
async def test_graficos_page_trae_controles_nuevos() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        p = await ac.get("/graficos")
    assert p.status_code == 200
    for frag in ('name="dmax"', 'name="fuente"', 'name="curve2"', "Vector CAFCI"):
        assert frag in p.text


@pytest.mark.asyncio
async def test_locate_fuente_switch_en_yas_y_comparador() -> None:
    """El widget compartido de 'ubicación en la curva' (YAS y Comparador)
    trae el selector BYMA/CAFCI, con BYMA como default (primera opción)."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    bond_universe.ensure_loaded()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        y = await ac.post("/yas/recompute", data={"code": "GD30", "mode": "precio",
                                                  "value": "78,5"})
        c = await ac.get("/comparador/result", params={
            "a": "TX26", "b": "TX28", "mode": "precio",
            "val_a": "1.100", "val_b": "1.500"})
    assert y.status_code == 200 and c.status_code == 200
    for r in (y, c):
        if "locate-box" in r.text:                       # con curva y métricas sanas
            assert 'class="locate-fuente"' in r.text
            assert r.text.index('value="byma"') < r.text.index('value="cafci"')
