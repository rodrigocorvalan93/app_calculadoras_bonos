"""Tests for the Dólares monitor (backend/services/dolares.py + routes).

Covers:
  - `fx_rows` builds the implicit USD/USB table off the store with the
    bid/offer/last ratio convention (ARS leg ÷ cable/MEP leg).
  - `canje_rows` returns CCL/MEP − 1 with bid < last < offer ordering.
  - `official_fx` prefers a live `DLR/SPOT` (bidirectional) over the A3500
    crawl — so a spot trading below its close shows a NEGATIVE variation.
  - `puntas` + the FX operation math.
  - HTTP smoke for /dolares, /dolares/tables, /dolares/oficial,
    /dolares/rail, /dolares/calc.
"""
from __future__ import annotations

import pytest

from backend.services import bond_universe
from backend.services import dolares as dx
from backend.services import fx as fx_svc
from backend.services import marketdata_store as mds_
from backend.services import symbols as syms_


def _base() -> str:
    bond_universe.ensure_loaded()
    bases = fx_svc.fx_bases()
    if not bases:
        pytest.skip("no globales/bonares bases in especies.py")
    return bases[0]


def _seed(base: str, *, ars=74.55, c=0.0501, d=0.0506) -> None:
    store = mds_.get_store()
    store.update_from_md(syms_.md_symbol(base, "24hs"), {
        "BI": {"price": ars - 0.15}, "OF": {"price": ars + 0.25},
        "LA": {"price": ars}, "CL": {"price": ars - 0.35}})
    store.update_from_md(syms_.md_symbol(base + "C", "24hs"), {
        "BI": {"price": c - 0.0001}, "OF": {"price": c + 0.0001},
        "LA": {"price": c}, "CL": {"price": c}, "EV": {"size": 42_000_000}})
    store.update_from_md(syms_.md_symbol(base + "D", "24hs"), {
        "BI": {"price": d - 0.0001}, "OF": {"price": d + 0.0001},
        "LA": {"price": d}, "CL": {"price": d}, "EV": {"size": 12_000_000}})
    dx._cache.clear()


def test_fx_rows_ratio_convention() -> None:
    base = _base()
    _seed(base)
    rows = dx.fx_rows("USD", "24hs")
    row = next((r for r in rows if r["base"] == base), None)
    assert row is not None
    # last = ARS.last / cable.last ; bid = ARS.bid / cable.offer ; offer = ARS.offer / cable.bid
    assert row["last"] == pytest.approx(74.55 / 0.0501)
    assert row["bid"] == pytest.approx((74.55 - 0.15) / (0.0501 + 0.0001))
    assert row["offer"] == pytest.approx((74.55 + 0.25) / (0.0501 - 0.0001))
    assert row["bid"] < row["last"] < row["offer"]      # spread sane
    assert row["vol_usd_m"] == pytest.approx(42.0)      # cable-leg $ volume / 1e6


def test_canje_is_ccl_over_mep_with_bid_offer() -> None:
    base = _base()
    _seed(base)                       # d (MEP price) > c (cable price) → CCL > MEP → canje > 0
    rows = dx.canje_rows("24hs")
    row = next((r for r in rows if r["base"] == base), None)
    assert row is not None
    ccl, mep = 74.55 / 0.0501, 74.55 / 0.0506
    assert row["last"] == pytest.approx(ccl / mep - 1.0)
    assert row["last"] > 0                              # cable más caro que el MEP
    assert row["bid"] < row["last"] < row["offer"]      # canje tiene bid/offer, no sólo last


def test_official_spot_is_bidirectional() -> None:
    """DLR/SPOT por debajo de su close → variación NEGATIVA (la flecha baja).
    Esto arregla el A3500, que casi siempre marca para arriba."""
    store = mds_.get_store()
    store.update_from_md(dx.SPOT_SYMBOL, {"LA": {"price": 1405.0}, "CL": {"price": 1412.0}})
    dx._cache.clear()
    ofi = dx.official_fx()
    assert ofi["source"] == "DLR/SPOT"
    assert ofi["last"] == pytest.approx(1405.0)
    assert ofi["var_pct"] is not None and ofi["var_pct"] < 0


def test_puntas_and_operation_math() -> None:
    base = _base()
    _seed(base)
    p = dx.puntas(base, "USD", "24hs")
    assert p["last"] == pytest.approx(74.55 / 0.0501)
    # Comprar USD: pago bono ARS al offer, vendo pata cable al bid.
    px_a, px_u = p["ars_offer"], p["usd_bid"]
    usd_qty = 10_000.0
    vn = usd_qty * 100.0 / px_u
    ars = vn * px_a / 100.0
    assert ars > 0 and vn > 0
    # TC efectivo = ARS pagados / USD obtenidos = offer implícito.
    assert ars / usd_qty == pytest.approx(p["offer"])


@pytest.mark.asyncio
async def test_dolares_endpoints() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    base = _base()
    _seed(base)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        for url in ("/dolares", "/dolares/tables?plazo=ambos", "/dolares/oficial",
                    "/dolares/rail", f"/dolares/calc?base={base}&leg=USD&plazo=24hs&side=comprar&modo=usd&cantidad=10000"):
            r = await ac.get(url)
            assert r.status_code == 200, url
            assert r.text  # non-empty HTML
