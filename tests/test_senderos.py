"""Senderos mensuales del Escenario: nivel mes a mes para inflación (CER/UVA),
deva A3500 (DLK), deva CCL (globales) y deva MEP (bonares). Cubre compound_path,
el parser del sendero, la equivalencia con el input plano viejo (compat), que el
sendero MUEVE el TR, y los endpoints (grid + tabla con params de sendero)."""
from __future__ import annotations

import pytest

from backend.routes import escenario as esc_route
from backend.services import total_return as tr


# ── compound_path ────────────────────────────────────────────────────────────
def test_compound_path():
    assert tr.compound_path(None, 4) is None
    assert tr.compound_path([], 4) is None
    # un elemento = plano → idéntico al viejo (1+m)^months − 1
    assert tr.compound_path([0.02], 4) == pytest.approx((1.02) ** 4 - 1)
    assert tr.compound_path([0.02], 2.5) == pytest.approx((1.02) ** 2.5 - 1)
    # multi-mes = producto
    assert tr.compound_path([0.02, 0.03], 2) == pytest.approx(1.02 * 1.03 - 1)
    # extiende el último para meses más allá del sendero
    assert tr.compound_path([0.02, 0.03], 4) == pytest.approx(1.02 * 1.03 * 1.03 * 1.03 - 1)
    # mes fraccional sobre el último tramo
    assert tr.compound_path([0.02, 0.04], 2.5) == pytest.approx(1.02 * 1.04 * (1.04 ** 0.5) - 1)


# ── parser de sendero (route) ────────────────────────────────────────────────
def test_parse_path():
    pp = esc_route._parse_path
    assert pp("") is None and pp(None) is None
    assert pp("2,1;2,0;1,9") == pytest.approx((0.021, 0.020, 0.019))
    assert pp("5;5;5", scale=1.0) == (5.0, 5.0, 5.0)        # nivel TNA tal cual
    # carry-forward de huecos internos; backfill del hueco inicial; trim del final
    assert pp("2;;3") == pytest.approx((0.02, 0.02, 0.03))
    assert pp(";3") == pytest.approx((0.03, 0.03))
    assert pp("2;;") == pytest.approx((0.02,))


# ── el sendero mueve el TR; equivalencia con el plano viejo ───────────────────
def _dates():
    terminal = "30/10/2026"
    settle = tr.settle_str("24hs")
    sd, td = tr._parse_d(settle), tr._parse_d(terminal)
    return terminal, settle, sd, td


def test_infl_path_equivale_al_plano_y_mueve():
    terminal, settle, sd, td = _dates()
    base = tr._bond_tr("TX26", 0.05, 0.05, terminal, settle, sd, td, 0.5, want_duration=False)
    plano = tr._bond_tr("TX26", 0.05, 0.05, terminal, settle, sd, td, 0.5,
                        want_duration=False, infl_monthly=0.04)
    sendero1 = tr._bond_tr("TX26", 0.05, 0.05, terminal, settle, sd, td, 0.5,
                           want_duration=False, infl_path=(0.04,))
    # plano == sendero de un elemento (compat exacta)
    assert sendero1["tr_total"] == pytest.approx(plano["tr_total"])
    # un sendero ascendente alto sube el ajuste de un bono CER vs el base proyectado
    alto = tr._bond_tr("TX26", 0.05, 0.05, terminal, settle, sd, td, 0.5,
                       want_duration=False, infl_path=(0.06, 0.06, 0.06, 0.06))
    assert alto["ajuste"] > base["ajuste"]


def test_a3500_path_mueve_un_dlk():
    from backend.services import bond_universe, curves
    bond_universe.ensure_loaded()
    terminal, settle, sd, td = _dates()
    dlk = curves.build_curve_codes().get("dolarlinked", [])
    code = next((c for c in dlk if "A3500" in (getattr(bond_universe.get(c), "ajuste_sobre_capital", "") or "")), None)
    if code is None:
        pytest.skip("sin DLK A3500 en la curva")
    base = tr._bond_tr(code, 0.05, 0.05, terminal, settle, sd, td, 0.5, want_duration=False)
    alto = tr._bond_tr(code, 0.05, 0.05, terminal, settle, sd, td, 0.5,
                       want_duration=False, a3500_path=(0.05, 0.05, 0.05, 0.05))
    assert base is not None and alto is not None
    assert alto["ajuste"] != base["ajuste"]        # la deva override cambia el drift A3500


# ── endpoints ────────────────────────────────────────────────────────────────
def _seed():
    from backend.services import bond_universe, curves, marketdata_store as mds, symbols as syms
    bond_universe.ensure_loaded()
    tbl = curves.build_curve_codes(); store = mds.get_store()
    for key in ("cer", "dolarlinked", "globales", "bonares", "lecap"):
        for i, c in enumerate(tbl.get(key) or []):
            store.update_from_md(syms.md_symbol(c, "24hs"),
                                 {"LA": {"price": 98.0 + (i % 30) * 0.5},
                                  "CL": {"price": 97.9 + (i % 30) * 0.5}, "EV": 2e7, "NV": 2e5})


@pytest.mark.asyncio
async def test_escenario_grid_y_senderos_http():
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    _seed()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        page = await ac.get("/escenario")
        base = await ac.get("/escenario/table")
        ccl = await ac.get("/escenario/table?ccl_path=2;2;2;2")
    assert page.status_code == 200
    assert "escSenderos(" in page.text and "sendero-tbl" in page.text
    assert 'name="ccl_path"' in page.text and 'name="infl_path"' in page.text
    assert base.status_code == 200 and ccl.status_code == 200
    import re
    g = lambda h: re.search(r"deva CCL ([0-9.,]+%)", h).group(1)
    assert g(base.text) != g(ccl.text)             # el sendero CCL cambió la deva proyectada
