"""Curvas/Mercado: tablas ordenables (click en th) + filtro de texto, todo
client-side (cero requests extra). Acá sólo verificamos que el HTML trae los
hooks que consume app.js (data-sortable / th[data-sort] / data-table-filter)."""
from __future__ import annotations

import pytest

from backend.services import bond_universe, marketdata_store as mds, symbols as syms


@pytest.mark.asyncio
async def test_curvas_mercado_ordenables_y_filtrables() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    bond_universe.ensure_loaded()
    for c in ("TX26", "TZX26"):
        mds.get_store().update_from_md(syms.md_symbol(c, "24hs"), {"LA": {"price": 100.0}, "CL": {"price": 99.0}})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        ct = (await ac.get("/curves/table?curve=cer&plazo=24hs")).text
        mt = (await ac.get("/mercado/table?curve=cer&plazo=24hs")).text
        cp = (await ac.get("/curves")).text
        mp = (await ac.get("/mercado")).text
    # tablas ordenables con id estable (el sorter guarda estado por id y re-aplica tras el swap live)
    assert 'id="curve-tbl"' in ct and "data-sortable" in ct and "<thead>" in ct and "th data-sort" in ct
    assert 'id="mercado-tbl"' in mt and "data-sortable" in mt and "<thead>" in mt and "th data-sort" in mt
    assert "data-sortead" not in ct and "data-sortead" not in mt          # no romper el <thead>
    # filtros client-side en cada página (texto + reglas numéricas ≥/≤ por
    # columna), fuera del contenedor que swapea
    for page, tbl in ((cp, "#curve-tbl"), (mp, "#mercado-tbl")):
        assert 'data-table-filters="%s"' % tbl in page
        assert "data-f-text" in page and "data-f-col" in page and "data-f-add" in page
