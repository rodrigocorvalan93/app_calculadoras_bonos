"""Futuros de dólar (DLR) — símbolos, parseo de vto, tasa implícita y endpoint."""
from __future__ import annotations

from datetime import date

import pytest

from backend.services import futuros as fut


def test_symbols_and_vto() -> None:
    mn, my = fut.symbols("min"), fut.symbols("may")
    assert mn and mn[0].startswith("DLR/") and not mn[0].endswith("M")
    assert my and my[0].endswith("M")
    v = fut._parse_vto("DLR/FEB26")
    assert v == date(2026, 2, 28)
    assert fut._parse_vto("DLR/FEB26M") == date(2026, 2, 28)
    assert fut._parse_vto("basura") is None


def test_implied_rate_math() -> None:
    td, tna, tem = fut._impl(110.0, 100.0, 365)      # +10% en 1 año
    assert td == pytest.approx(0.10)
    assert tna == pytest.approx(0.10)                # lineal: 0.10·365/365
    assert tem is not None and tem > 0
    assert fut._impl(None, 100.0, 30) == (None, None, None)
    assert fut._impl(110.0, None, 30) == (None, None, None)


def test_rows_from_store() -> None:
    from backend.services import marketdata_store as mds
    sym = fut.symbols("may")[0]
    sp = fut.spot() or 1000.0
    mds.get_store().update_from_md(sym, {"LA": {"price": sp * 1.03}, "CL": {"price": sp * 1.02}})
    r = next((x for x in fut.rows("may") if x["code"] == sym), None)
    assert r is not None and r["dias"] is not None
    assert r["tna"] is not None and r["last"] == pytest.approx(sp * 1.03)


@pytest.mark.asyncio
async def test_futuros_endpoint() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        p = await ac.get("/futuros")
        t = await ac.get("/futuros/table")
    assert p.status_code == 200 and "Spot A3500" in p.text and "Mayorista" in p.text
    assert t.status_code == 200
