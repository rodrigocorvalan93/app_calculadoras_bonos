"""Per-leg curve pricing (backend/routes/curves.py).

A multi-leg bond (globales / cable / MEP) can be priced off any BYMA leg:
  - native / USD (cable) / USB (MEP) feed the native ficha directly → fx-free.
  - ARS (pesos) is the only leg that needs the FX (price ÷ native rate).

Exercised against the globales, which already follow the norm (`GD30C`
DIRTY cable ficha exists today), with prices injected into the store.
"""
from __future__ import annotations

import numpy as np
import pytest

from backend.routes import curves as curves_route
from backend.services import bond_universe, curves
from backend.services import fx as fx_svc
from backend.services import marketdata_store as mds_
from backend.services import symbols as syms_


def _globales_native() -> str:
    """A globales DIRTY `…C` cable ficha — skip if none. Robusto a bonos nuevos
    en la curva que NO siguen la convención …C (p.ej. BDC36): tomar el 1º que
    realmente termina en C, no `codes[0]` a secas."""
    bond_universe.ensure_loaded()
    codes = curves.build_curve_codes().get("globales") or []
    code = next((c for c in codes if c.endswith("C")), None)
    if code is None:
        pytest.skip("no globales …C cable ficha in especies.py")
    return code


def test_usd_and_usb_legs_are_fx_free() -> None:
    code = _globales_native()          # e.g. GD30C
    base = code[:-1]
    store = mds_.get_store()
    store.update_from_md(syms_.md_symbol(code, "24hs"), {"LA": {"price": 70.0}})        # cable
    store.update_from_md(syms_.md_symbol(base + "D", "24hs"), {"LA": {"price": 71.0}})  # MEP

    # No FX snapshot passed → still computes (fx-free) for native/USD/USB.
    for leg, sym_price in (("native", 70.0), ("USD", 70.0), ("USB", 71.0)):
        row = curves_route._row_for_code(code, "24hs", leg=leg, fx=None)
        assert row is not None, leg
        assert np.isfinite(row["tirea"]), f"{leg} should price fx-free"
        assert row["leg"] == leg

    # The USB leg used the GD30D price (71), the cable legs used 70 → the
    # two yields differ (different venues), proving the leg actually routed.
    usd = curves_route._row_for_code(code, "24hs", leg="USD", fx=None)
    usb = curves_route._row_for_code(code, "24hs", leg="USB", fx=None)
    assert usd["tirea"] != usb["tirea"]


def test_ars_leg_needs_fx() -> None:
    code = _globales_native()          # GD30C, Moneda USD (cable native)
    base = code[:-1]
    store = mds_.get_store()
    # Globales pesos ticker is the base (no suffix).
    store.update_from_md(syms_.md_symbol(base, "24hs"), {"LA": {"price": 70000.0}})

    # With CCL = 1000 → 70000/1000 = 70 → finite TIREA (matches cable basis).
    fx = fx_svc.FxSnapshot(ccl=1000.0, usb=950.0)
    row = curves_route._row_for_code(code, "24hs", leg="ARS", fx=fx)
    assert row is not None
    assert np.isfinite(row["tirea"])
    assert row["last"] == 70000.0  # the displayed price stays the pesos quote

    # Without a CCL, the pesos price can't be normalized → no TIREA.
    row_nofx = curves_route._row_for_code(code, "24hs", leg="ARS", fx=fx_svc.FxSnapshot())
    assert row_nofx is not None
    assert not np.isfinite(row_nofx["tirea"] if row_nofx["tirea"] is not None else float("nan"))


@pytest.mark.asyncio
async def test_curves_table_leg_param_http() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    code = _globales_native()
    base = code[:-1]
    mds_.get_store().update_from_md(syms_.md_symbol(base + "D", "24hs"), {"LA": {"price": 71.0}})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/curves/table?curve=globales&plazo=24hs&leg=USB&only_quoting=false")
    assert r.status_code == 200
    assert "leg USB" in r.text
