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


def _pure_tamar_floater():
    from backend.services import bond_universe, curves
    bond_universe.ensure_loaded()
    for c in curves.build_curve_codes().get("corp_tamar", []):
        o = bond_universe.get(c)
        if o is not None and getattr(o, "index", None) == "TAMAR" \
                and getattr(o, "tipo_tasa_interes", None) == "VARIABLE":
            return c
    return None


def test_tamar_sendero_mueve_carry_con_signo_correcto():
    from backend.services import bond_universe, pricing
    code = _pure_tamar_floater()
    if code is None:
        pytest.skip("sin floater TAMAR puro")
    terminal = "30/04/2027"; settle = tr.settle_str("24hs")
    sd, td = tr._parse_d(settle), tr._parse_d(terminal)
    px100 = float(bond_universe.get(code) and pricing._bond_obj_copy(code).calcula_precio(0.30)) * 100.0
    n = 20
    base = tr._bond_tr(code, 0.30, 0.30, terminal, settle, sd, td, 1.0, want_duration=False, price=px100)
    hi = tr._bond_tr(code, 0.30, 0.30, terminal, settle, sd, td, 1.0, want_duration=False,
                     tamar_path=(45.0,) * n, price=px100)
    lo = tr._bond_tr(code, 0.30, 0.30, terminal, settle, sd, td, 1.0, want_duration=False,
                     tamar_path=(8.0,) * n, price=px100)
    assert base and hi and lo
    # más TAMAR ⇒ más cupón ⇒ y0 re-derivada más alta ⇒ más carry (signo correcto)
    assert hi["carry"] > base["carry"] > lo["carry"]
    assert hi["y0"] > lo["y0"]


def test_tamar_sendero_NO_toca_singleton_ni_yas():
    """Aislamiento (lo que el usuario pidió): correr el escenario con sendero TAMAR
    NO puede cambiar el pricing del mismo bono por YAS/Curvas ni el singleton."""
    from backend.services import bond_universe, pricing
    import numpy as np
    code = _pure_tamar_floater()
    if code is None:
        pytest.skip("sin floater TAMAR puro")
    terminal = "30/04/2027"; settle = tr.settle_str("24hs")
    sd, td = tr._parse_d(settle), tr._parse_d(terminal)
    px100 = float(pricing._bond_obj_copy(code).calcula_precio(0.30)) * 100.0
    # baseline por el camino YAS/Curvas + cupón del singleton ANTES
    yas_before = pricing.metrics_for_market_price(code, px100)["tirea"]
    intereses_before = float(np.array(bond_universe.get(code).intereses, dtype=float)[0])
    # corro el TR con sendero TAMAR (aplica override sobre la copia)
    tr._bond_tr(code, 0.30, 0.30, terminal, settle, sd, td, 1.0, want_duration=False,
                tamar_path=(45.0,) * 20, price=px100)
    # DESPUÉS: YAS/Curvas y el singleton, idénticos
    assert pricing.metrics_for_market_price(code, px100)["tirea"] == yas_before
    assert float(np.array(bond_universe.get(code).intereses, dtype=float)[0]) == intereses_before


def test_tamar_baseline_sin_sendero_identico():
    """Sin sendero TAMAR, el TR es byte-idéntico al de hoy (no regresión)."""
    code = _pure_tamar_floater() or "TX26"
    terminal = "30/04/2027"; settle = tr.settle_str("24hs")
    sd, td = tr._parse_d(settle), tr._parse_d(terminal)
    a = tr._bond_tr(code, 0.30, 0.32, terminal, settle, sd, td, 1.0, want_duration=False)
    b = tr._bond_tr(code, 0.30, 0.32, terminal, settle, sd, td, 1.0, want_duration=False, tamar_path=None)
    assert a and b and a["carry"] == b["carry"] and a["tr_total"] == b["tr_total"]


@pytest.mark.asyncio
async def test_escenario_tamar_http_y_aislamiento_categorias():
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    _seed()
    # extra: seed the TAMAR curve too
    from backend.services import curves, marketdata_store as mds, symbols as syms
    for i, c in enumerate(curves.build_curve_codes().get("tamar", [])):
        mds.get_store().update_from_md(syms.md_symbol(c, "24hs"),
                                       {"LA": {"price": 98.0 + i * 0.5}, "CL": {"price": 97.9 + i * 0.5},
                                        "EV": 2e7, "NV": 2e5})
    import re
    def carry(html, lbl):
        m = re.search(r">" + lbl + r" <i class=\"muted\">\(\d+\)</i></td>\s*<td></td><td></td>\s*<td>[^<]+</td>\s*<td>[^<]+</td>\s*<td class=\"grp\">([^<]+)</td>", html, re.S)
        return m.group(1) if m else None
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        base = await ac.get("/escenario/table")
        hi = await ac.get("/escenario/table?tamar_path=45;45;45;45;45;45")
    assert base.status_code == 200 and hi.status_code == 200
    if carry(base.text, "TAMAR") and carry(hi.text, "TAMAR"):
        assert carry(base.text, "TAMAR") != carry(hi.text, "TAMAR")     # TAMAR se movió
    if carry(base.text, "CER corto") and carry(hi.text, "CER corto"):
        assert carry(base.text, "CER corto") == carry(hi.text, "CER corto")  # CER intacto


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
