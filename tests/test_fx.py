"""Tests for the implicit-FX keystone (backend/services/fx.py).

Covers:
  - `to_cable_usd` math for the three quote legs (ARS / USB / USD).
  - `compute_fx` derives CCL + USB from store prices and picks the
    top-volume base as the reference.
  - `fx_leg_symbols` includes the C and D legs (so the WS seeds them).
  - `GET /market/fx` returns well-formed JSON (HTTP smoke).
"""
from __future__ import annotations

import pytest

from backend.services import bond_universe
from backend.services import fx as fx_svc
from backend.services import marketdata_store as mds_
from backend.services import symbols as syms_


def test_to_cable_usd_three_legs() -> None:
    fx = fx_svc.FxSnapshot(ccl=1000.0, usb=950.0)
    # cable (C / USD): already on the target basis → unchanged.
    assert fx_svc.to_cable_usd(70.0, "USD", fx) == 70.0
    assert fx_svc.to_cable_usd(70.0, "C", fx) == 70.0
    # ARS (…O): price / CCL.
    assert fx_svc.to_cable_usd(70000.0, "ARS", fx) == 70.0
    assert fx_svc.to_cable_usd(70000.0, "O", fx) == 70.0
    # USB / MEP (…D): price * USB / CCL  (MEP → ARS → cable).
    assert fx_svc.to_cable_usd(70.0, "USB", fx) == pytest.approx(70.0 * 950.0 / 1000.0)
    assert fx_svc.to_cable_usd(70.0, "D", fx) == pytest.approx(66.5)
    # Missing reference → None; bad price → None.
    assert fx_svc.to_cable_usd(70.0, "ARS", fx_svc.FxSnapshot()) is None
    assert fx_svc.to_cable_usd(None, "USD", fx) is None
    assert fx_svc.to_cable_usd(-5, "USD", fx) is None
    assert fx_svc.to_cable_usd(70.0, "???", fx) is None


def test_fx_leg_symbols_include_c_and_d() -> None:
    bond_universe.ensure_loaded()
    bases = fx_svc.fx_bases()
    if not bases:
        pytest.skip("no globales/bonares bases in especies.py")
    b = bases[0]
    symbols = fx_svc.fx_leg_symbols("24hs")
    assert any(s.endswith(f"{b}C - 24hs") for s in symbols)
    assert any(s.endswith(f"{b}D - 24hs") for s in symbols)


def test_compute_fx_from_store() -> None:
    bond_universe.ensure_loaded()
    bases = fx_svc.fx_bases()
    if not bases:
        pytest.skip("no globales/bonares bases in especies.py")
    base = bases[0]
    store = mds_.get_store()
    # ARS + cable (C) + MEP (D) legs, with a dominant volume on the USD
    # legs so this base is the reference in both tables.
    store.update_from_md(syms_.md_symbol(base, "24hs"), {"LA": {"price": 70000.0}})
    store.update_from_md(syms_.md_symbol(base + "C", "24hs"), {"LA": {"price": 70.0}, "EV": 9e15})
    store.update_from_md(syms_.md_symbol(base + "D", "24hs"), {"LA": {"price": 71.5}, "EV": 9e15})

    fx_svc.invalidate()
    snap = fx_svc.compute_fx("24hs")
    assert snap.ccl == pytest.approx(70000.0 / 70.0)   # 1000
    assert snap.usb == pytest.approx(70000.0 / 71.5)
    assert snap.ccl_base == base
    assert snap.usb_base == base
    assert snap.canje == pytest.approx(snap.ccl / snap.usb - 1.0)

    # And the round-trip: a D-leg price normalizes to cable-USD via this snap.
    assert fx_svc.to_cable_usd(71.5, "D", snap) == pytest.approx(71.5 * snap.usb / snap.ccl)


@pytest.mark.asyncio
async def test_market_fx_endpoint() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/market/fx")
    assert r.status_code == 200
    body = r.json()
    for k in ("ccl", "usb", "canje", "bases"):
        assert k in body
