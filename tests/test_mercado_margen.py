"""Mercado: switch TIREA ↔ margen s/benchmark en las 3 columnas de tasa.

El margen sale del MISMO dict de métricas cacheado que la TIR (se calculaba
adentro y se descartaba) — el switch no agrega cálculo: el server sólo cambia
qué campo renderiza, y ?ym= entra en la key del seq-cache como cualquier query.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from backend.services import bond_universe, curves, pricing


def _floater_code() -> str:
    bond_universe.ensure_loaded()
    for c in curves.build_curve_codes().get("tamar") or []:
        return c
    pytest.skip("sin bonos TAMAR en el universo")


def test_margen_viene_del_mismo_calculo() -> None:
    from backend.routes.curves import _tirea_margen_at

    code = _floater_code()
    tir, mgn = _tirea_margen_at(code, 100.0)
    assert tir is not None and tir == tir
    assert mgn is not None and mgn == mgn        # floater benchmarkeado → margen finito
    m = pricing.metrics_for_market_price(code, 100.0, None)
    assert tir == m.get("tirea") and mgn == m.get("margen_tna")
    # sin precio no hay nada que valuar
    assert _tirea_margen_at(code, None) == (None, None)


@pytest.mark.asyncio
async def test_mercado_table_switch_ym() -> None:
    bond_universe.ensure_loaded()
    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/mercado/table", params={
            "curve": "tamar", "only_quoting": "false", "ym": "margen"})
        assert r.status_code == 200
        assert "Mgn@Last" in r.text and "Bid Mgn" in r.text
        assert "margen TNA s/TAMAR-BADLAR" in r.text
        r2 = await ac.get("/mercado/table", params={
            "curve": "tamar", "only_quoting": "false"})
        assert r2.status_code == 200
        assert "TIREA@Last" in r2.text and "Mgn@Last" not in r2.text
        # la página trae el selector con persistencia (localStorage m_ym)
        page = await ac.get("/mercado")
        assert page.status_code == 200
        assert 'name="ym"' in page.text and "m_ym" in page.text
