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


def test_native_dollar_code_join_por_isin() -> None:
    """La especie en pesos de un hard-dollar resuelve su ficha NATIVA por ISIN
    (los tickers no siempre comparten raíz: BPOC7 ↔ BPC7D)."""
    from backend.services import pricing

    bond_universe.ensure_loaded()
    assert pricing.native_dollar_code("AL30") == "AL30D"    # bonar → MEP
    assert pricing.native_dollar_code("GD30") == "GD30C"    # global → cable
    assert pricing.native_dollar_code("BPOC7") == "BPC7D"   # BOPREAL: raíz distinta
    assert pricing.native_dollar_code("AL30D") is None      # la nativa no se toca
    assert pricing.native_dollar_code("TX26") is None       # bono ARS no se toca


def test_especie_pesos_hard_dollar_divide_por_fx_de_pago(monkeypatch) -> None:
    """Caso de la captura del usuario: Libro · AL30 con TIR @ LAST -100% en
    todo el book — el precio ARS crudo de la especie en pesos entraba a la
    calculadora del bono en dólares. Ahora el precio se divide por el FX de la
    MONEDA DE PAGO (AL30 paga MEP → ÷ MEP; GD30 paga cable → ÷ CCL) y la TIR
    se calcula con la ficha nativa (AL30D / GD30C)."""
    bond_universe.ensure_loaded()
    # Store propio: otros tests asumen los símbolos AL30/GD30 pesos vacíos.
    store = mds_.MarketDataStore()
    monkeypatch.setattr(mds_, "_store", store)
    fx = fx_svc.FxSnapshot(ccl=1480.0, usb=1465.0)
    monkeypatch.setattr(fx_svc, "get_fx", lambda plazo="24hs": fx)

    store.update_from_md(syms_.md_symbol("AL30", "24hs"), {"LA": {"price": 84000.0}})
    row = curves_route._row_for_code("AL30", "24hs", leg="native", fx=None)
    assert row is not None
    assert row["last"] == 84000.0                                # se muestra el precio pesos
    assert row["px_calc"] == pytest.approx(84000.0 / 1465.0)     # ÷ MEP (paga MEP)
    assert row["tirea"] is not None and np.isfinite(row["tirea"])
    assert row["tirea"] > -0.5                                   # nunca más el -100%

    store.update_from_md(syms_.md_symbol("GD30", "24hs"), {"LA": {"price": 85000.0}})
    row_gd = curves_route._row_for_code("GD30", "24hs", leg="native", fx=None)
    assert row_gd["px_calc"] == pytest.approx(85000.0 / 1480.0)  # ÷ CCL (paga cable)

    # Sin FX vivo → None honesto (el template pinta "—"), jamás una TIR mentirosa.
    monkeypatch.setattr(fx_svc, "get_fx", lambda plazo="24hs": fx_svc.FxSnapshot())
    row_nofx = curves_route._row_for_code("AL30", "24hs", leg="native", fx=None)
    assert row_nofx["px_calc"] is None
    assert row_nofx["tirea"] is None or not np.isfinite(row_nofx["tirea"])


@pytest.mark.asyncio
async def test_mercado_book_especie_pesos_sin_menos_cien(monkeypatch) -> None:
    """El libro de la especie en pesos (AL30) computa TIRs por nivel con el
    precio normalizado — la página no vuelve a mostrar -100,00%."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    fx = fx_svc.FxSnapshot(ccl=1480.0, usb=1465.0)
    monkeypatch.setattr(fx_svc, "get_fx", lambda plazo="24hs": fx)
    store = mds_.MarketDataStore()                     # aislado (ver test de arriba)
    monkeypatch.setattr(mds_, "_store", store)
    store.update_from_md(syms_.md_symbol("AL30", "24hs"), {
        "LA": {"price": 84000.0}, "CL": {"price": 83500.0},
        "BI": [{"price": 83900.0, "size": 1000}],
        "OF": [{"price": 84100.0, "size": 500}],
    })
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/mercado/book/AL30", params={"plazo": "24hs", "leg": "native"})
    assert r.status_code == 200
    assert "book-stats" in r.text
    assert "-100,00" not in r.text


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
