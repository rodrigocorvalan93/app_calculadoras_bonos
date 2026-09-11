"""Curvas corporativas en Mercado: como el panel CEDEARs — por defecto sólo
las 30 ONs con más VN operado hoy, búsqueda en toda la curva y "ver todas".
Las soberanas no se tocan."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from backend.routes.curves import CORP_TOP, _vista_corp
from backend.services import bond_universe, curves, marketdata_store, symbols as syms


def _rows(n: int):
    # ordenadas por duration como las deja _rows_for; el VN operado crece con i
    return [{"code": f"ON{i:03d}", "nombre": f"ON Empresa {i} Clase {i}", "duration": i / 10,
             "nominal": float(i), "volume": float(i) * 100, "last": 100.0} for i in range(n)]


def test_vista_corp_recorta_por_volumen_y_conserva_orden() -> None:
    rows = _rows(50)
    vis, meta = _vista_corp(rows, {"total": 50})
    assert len(vis) == CORP_TOP and meta["ocultas"] == 20 and meta["top_n"] == CORP_TOP
    assert [r["code"] for r in vis] == [f"ON{i:03d}" for i in range(20, 50)]   # las 30 más operadas, en orden
    # 'ver todas' y curvas chicas: sin recorte
    assert len(_vista_corp(rows, {}, mas=1)[0]) == 50
    assert _vista_corp(_rows(10), {})[1]["ocultas"] == 0
    # búsqueda en TODA la curva (ticker o nombre), sin recorte
    vis, meta = _vista_corp(rows, {}, q="on00")
    assert meta["buscado"] and [r["code"] for r in vis] == [f"ON00{i}" for i in range(10)]
    vis, _ = _vista_corp(rows, {}, q=" empresa 3 clase ")
    assert [r["code"] for r in vis] == ["ON003"]


@pytest.mark.asyncio
async def test_http_mercado_corp_top30_busqueda_y_ver_todas() -> None:
    from backend.main import app

    bond_universe.ensure_loaded()
    cc = curves.build_curve_codes()
    key = max((k for k in cc if k.startswith("corp_")), key=lambda k: len(cc[k]))
    codes = cc[key]
    assert len(codes) > CORP_TOP
    store = marketdata_store.get_store()
    for i, c in enumerate(codes):                       # VN operado creciente con i
        store.update_from_md(syms.md_symbol(c, "24hs"),
                             {"LA": {"price": 100.0}, "CL": {"price": 99.0}, "NV": 1000.0 * (i + 1), "EV": 1e5 * (i + 1)})
    chico, grande = codes[0], codes[-1]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/mercado/table", params={"curve": key, "only_quoting": "false"})
        assert r.status_code == 200
        assert r.text.count("<tr ") == CORP_TOP and f"top {CORP_TOP} por VN operado" in r.text
        assert f">{grande}<" in r.text and f">{chico}<" not in r.text
        assert f"ver las {len(codes) - CORP_TOP} restantes" in r.text
        # ver todas
        r = await ac.get("/mercado/table", params={"curve": key, "only_quoting": "false", "mas": 1})
        assert r.text.count("<tr ") == len(codes) and "restantes" not in r.text
        # búsqueda: encuentra una ON que quedó afuera del top
        r = await ac.get("/mercado/table", params={"curve": key, "only_quoting": "false", "q": chico})
        assert f">{chico}<" in r.text and "búsqueda en toda la curva" in r.text
        # la página también arranca recortada
        page = await ac.get("/mercado", params={"curve": key, "only_quoting": "false"})
        assert page.text.count("<tr ") == CORP_TOP and "panelTools" in page.text
        # soberanas: intactas
        r = await ac.get("/mercado/table", params={"curve": "cer", "only_quoting": "false"})
        assert "por VN operado" not in r.text
