"""Análisis de créditos — degradación sin json, filtros y endpoints.

credit_scores.json no está en CI: se inyecta estado sintético en el servicio.
"""
from __future__ import annotations

import pytest

from backend.services import credito


def test_filters() -> None:
    saved = dict(credito._state)
    credito._state.update({
        "inited": True, "available": True, "error": None,
        "issuers": [
            {"Emisor": "YPF", "Ticker": "YPFD", "Sector": "Energía", "Score": 4.0, "ONs cargadas": 3},
            {"Emisor": "Genneia", "Ticker": "GNNA", "Sector": "Energía", "Score": 2.0, "ONs cargadas": 0},
            {"Emisor": "Loma", "Ticker": "LOMA", "Sector": "Materiales", "Score": 3.5, "ONs cargadas": 1},
        ],
    })
    try:
        assert {r["Ticker"] for r in credito.issuers(score_min=3.0)} == {"YPFD", "LOMA"}
        assert {r["Ticker"] for r in credito.issuers(sector=["Energía"])} == {"YPFD", "GNNA"}
        assert {r["Ticker"] for r in credito.issuers(solo_ons=True)} == {"YPFD", "LOMA"}
        assert set(credito.sectors()) == {"Energía", "Materiales"}
    finally:
        credito._state.clear()
        credito._state.update(saved)


@pytest.mark.asyncio
async def test_creditos_endpoints() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    saved = dict(credito._state)
    credito._state.update({
        "inited": True, "available": True, "error": None,
        "issuers": [{"Emisor": "YPF SA", "Ticker": "YPFD", "Sector": "Energía", "Score": 4.0,
                     "Solvencia": 4.5, "Liquidez": 3.5, "Net Debt/EBITDA": 1.8, "EBITDA/Interest": 5.0,
                     "Current Ratio": 1.3, "Pasivo/PN": 1.1, "DFN (USD M)": 7000, "EBITDA (USD M)": 4500,
                     "ONs cargadas": 3, "Last Q": "3Q25", "Comentario": "ok"}],
    })
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            p = await ac.get("/creditos")
            t = await ac.get("/creditos/table?score_min=3.0")
            d = await ac.get("/creditos/detail?ticker=YPFD")
        assert p.status_code == 200
        assert t.status_code == 200 and "YPF SA" in t.text
        assert d.status_code == 200
    finally:
        credito._state.clear()
        credito._state.update(saved)
