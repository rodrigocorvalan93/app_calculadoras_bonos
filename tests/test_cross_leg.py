"""Patas dólar cruzadas (audit H1). El comparador de Mercado/Curvas dejaba pasar
SIN convertir el precio de una pata cruzada (cable sobre un bono MEP-nativo, o MEP
sobre uno cable-nativo) → la TIR salía corrida por el canje (~3,5%). Ahora toda
pata no nativa pasa por fx.normalize_price.
"""
from __future__ import annotations

import pytest

from backend.services.fx import FxSnapshot, normalize_price


def test_cross_leg_normalization_math():
    fx = FxSnapshot(ccl=1450.0, usb=1400.0)
    # pata nativa = no-op (FX-free)
    assert normalize_price(100.0, "USD", "USD", fx) == 100.0
    assert normalize_price(100.0, "USB", "USB", fx) == 100.0
    # bonares (USB nativo) cotizado en la pata cable (USD) → ×CCL/MEP
    assert abs(normalize_price(100.0, "USD", "USB", fx) - 100.0 * 1450.0 / 1400.0) < 1e-9
    # globales (USD nativo) cotizado en la pata MEP (USB) → ×MEP/CCL
    assert abs(normalize_price(100.0, "USB", "USD", fx) - 100.0 * 1400.0 / 1450.0) < 1e-9
    # ARS sobre nativo USD → ÷CCL (lo que ya hacía)
    assert abs(normalize_price(145000.0, "ARS", "USD", fx) - 145000.0 / 1450.0) < 1e-9
    # sin FX, una cruzada no se puede convertir → None (no un precio sin convertir)
    assert normalize_price(100.0, "USD", "USB", FxSnapshot()) is None


@pytest.mark.asyncio
async def test_curve_table_cross_legs_no_crash():
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.services import bond_universe, curves
    from backend.services import marketdata_store as mds, symbols as syms
    bond_universe.ensure_loaded()
    for cv, px in (("globales", 80.0), ("bonares", 70.0)):
        for c in curves.build_curve_codes().get(cv, []):
            mds.get_store().update_from_md(syms.md_symbol(c, "24hs"),
                                           {"LA": {"price": px}, "CL": {"price": px}})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        for curve in ("globales", "bonares"):
            for leg in ("native", "USD", "USB", "ARS"):
                r = await ac.get(f"/curves/table?curve={curve}&plazo=24hs&leg={leg}")
                assert r.status_code == 200, f"{curve}/{leg} -> {r.status_code}"
                assert "Traceback" not in r.text
