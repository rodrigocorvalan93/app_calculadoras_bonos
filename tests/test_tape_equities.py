"""Barra de activos + panel Acciones/CEDEARs + noticias — smoke CI-safe."""
from __future__ import annotations

import pytest

from backend.services import equities, marketdata_store as mds, symbols as syms


def _seed(code: str, px: float, close: float) -> None:
    mds.get_store().update_from_md(syms.md_symbol(code, "24hs"), {
        "BI": {"price": px * 0.999}, "OF": {"price": px * 1.001},
        "LA": {"price": px}, "CL": {"price": close},
        "OP": {"price": close}, "EV": {"size": 1_000_000}, "NV": {"size": 5_000}})


def test_equities_rows() -> None:
    _seed("GGAL", 5400.0, 5300.0)
    r = equities.row_for("GGAL")
    assert r and r["last"] == 5400.0
    assert abs(r["var_pct"] - (5400.0 / 5300.0 - 1) * 100) < 1e-9
    rows = equities.panel_rows("lideres")
    assert any(x["code"] == "GGAL" for x in rows)
    assert "tirea" not in rows[0]                  # sin calculadora


@pytest.mark.asyncio
async def test_equities_tape_news_endpoints() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    _seed("SPY", 42000.0, 41000.0)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        eq = await ac.get("/mercado/table?panel=lideres&plazo=24hs")
        tp = await ac.get("/tape")
        nm = await ac.get("/news/marquee")
        mp = await ac.get("/mercado")
    assert eq.status_code == 200 and "GGAL" in eq.text and "TIREA" not in eq.text
    assert tp.status_code == 200                    # con o sin items, nunca rompe
    assert nm.status_code == 200                    # sin red → vacío, no error
    assert mp.status_code == 200 and 'value="cedears"' in mp.text   # selector de panel
