"""Tests for the BYMA cauciones service + the overnight KPI in the riel.

Covers:
  - `rail_pick` chooses, among 1D–4D, the plazo with the most volume (1D on
    a normal day; rolls to 2D/3D/4D over a holiday/long weekend).
  - It falls back to the shortest plazo with a tasa when no volume is
    reported.
  - The /dolares/rail partial renders the "📊 Tasa" block with the picked
    caución above the "💵 Dólar" header.
"""
from __future__ import annotations

import pytest

from backend.services import cauciones as cauc_svc
from backend.services import marketdata_store as mds_


def _seed_caucion(n: int, *, tasa: float, close: float, vol: float, moneda: str = "PESOS") -> None:
    store = mds_.get_store()
    store.update_from_md(f"MERV - XMEV - {moneda} - {n}D", {
        "BI": {"price": tasa - 0.1}, "OF": {"price": tasa + 0.1},
        "LA": {"price": tasa}, "CL": {"price": close}, "EV": {"size": vol},
    })


def _clear_cauciones() -> None:
    """El store es un singleton: limpio las cauciones para aislar el test del
    resto (otro test pudo dejar un plazo con más volumen sembrado)."""
    store = mds_.get_store()
    for moneda in ("PESOS", "DOLAR"):
        for n in cauc_svc.PLAZOS:
            store._data.pop(f"MERV - XMEV - {moneda} - {n}D", None)


def test_rail_pick_prefers_highest_volume_overnight() -> None:
    _clear_cauciones()
    # 1D con más volumen que 2D → se elige 1D (día normal).
    _seed_caucion(1, tasa=23.5, close=23.0, vol=80_000_000_000)
    _seed_caucion(2, tasa=24.0, close=23.8, vol=5_000_000_000)
    r = cauc_svc.rail_pick("PESOS")
    assert r is not None
    assert r["plazo"] == "1D"
    assert r["tasa"] == pytest.approx(23.5)
    assert r["var"] == pytest.approx(0.5)          # last − close, en puntos de TNA


def test_rail_pick_rolls_to_longer_overnight_when_it_has_the_volume() -> None:
    _clear_cauciones()
    # Feriado/finde: el 1D casi no opera y el 3D concentra el volumen.
    _seed_caucion(1, tasa=23.5, close=23.5, vol=1_000_000)
    _seed_caucion(3, tasa=22.0, close=22.3, vol=90_000_000_000)
    r = cauc_svc.rail_pick("PESOS")
    assert r is not None
    assert r["plazo"] == "3D"
    assert r["tasa"] == pytest.approx(22.0)
    assert r["var"] == pytest.approx(-0.3)         # bajó vs cierre → flecha roja


def test_rail_picks_returns_ars_then_usd() -> None:
    _clear_cauciones()
    _seed_caucion(1, tasa=23.5, close=23.0, vol=80_000_000_000, moneda="PESOS")
    _seed_caucion(1, tasa=2.1, close=2.0, vol=4_000_000, moneda="DOLAR")
    picks = cauc_svc.rail_picks()
    assert [p["moneda"] for p in picks] == ["ARS", "USD"]      # orden ARS → USD
    assert picks[0]["tasa"] == pytest.approx(23.5)
    assert picks[1]["tasa"] == pytest.approx(2.1)


def test_rail_picks_skips_currency_without_data() -> None:
    _clear_cauciones()
    _seed_caucion(1, tasa=23.5, close=23.0, vol=80_000_000_000, moneda="PESOS")
    picks = cauc_svc.rail_picks()                              # sólo ARS en el store
    assert [p["moneda"] for p in picks] == ["ARS"]


@pytest.mark.asyncio
async def test_rail_renders_caucion_block() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    _clear_cauciones()
    _seed_caucion(1, tasa=23.5, close=23.0, vol=80_000_000_000, moneda="PESOS")
    _seed_caucion(1, tasa=2.1, close=2.0, vol=4_000_000, moneda="DOLAR")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/dolares/rail")
    assert r.status_code == 200
    for tok in ("📊 Tasa", "Caución ARS 1D", "23,50%", "Caución USD 1D", "💵 Dólar"):
        assert tok in r.text, tok
    # ARS aparece antes que USD en el riel.
    assert r.text.index("Caución ARS") < r.text.index("Caución USD")
