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
    # celda Var %: color fuerte + barrita de magnitud (100/99 − 1 = 1,01 % sobre
    # el tope de 2 % → 51 %). Misma celda en Curvas y en la macro de Mercado.
    assert 'class="var-cell var-up" style="--vw:51%">1,01%</td>' in ct
    assert 'class="grp var-cell var-up" style="--vw:51%">1,01%</td>' in mt
    assert "background-color: rgba(" not in ct and "background-color: rgba(" not in mt   # el heat viejo no vuelve


def test_filtros_var_cls_y_var_w() -> None:
    from backend.locale_ar import var_cls, var_w

    assert var_cls(0.85) == "var-up" and var_cls(-0.3) == "var-down"
    assert var_cls(0.0) == "" and var_cls(0.004) == "" and var_cls(-0.004) == ""   # 0,00 % no se pinta
    assert var_cls(None) == "" and var_cls(float("nan")) == "" and var_cls("x") == ""
    assert var_w(0.5, 2.0) == 25 and var_w(-1.0, 2.0) == 50 and var_w(7.3, 2.0) == 100
    assert var_w(2.5, 5.0) == 50 and var_w(0.0) == 0
    assert var_w(None) == 0 and var_w(float("nan")) == 0 and var_w("x") == 0 and var_w(1.0, 0.0) == 0
