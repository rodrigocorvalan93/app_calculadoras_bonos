"""Total Return — descomposición exacta (carry+compresión+ajuste=TR total),
ajuste=0 sin índice, y endpoints. Núcleo = rentafija.calcula_total_return."""
from __future__ import annotations

import pytest

from backend.services import bond_universe, curves, pricing, total_return as tr


def _setup_dates():
    bond_universe.ensure_loaded()
    pricing.compute_metrics("TX26", mode="precio", value=1000.0, include_cashflows=False)
    settle = pricing.settlement_date_str("CI")
    terminal = "31/10/2026"
    return settle, terminal, tr._parse_d(settle), tr._parse_d(terminal)


def test_decomposicion_aditiva_cer() -> None:
    settle, terminal, sd, td = _setup_dates()
    r = tr._bond_tr("TX26", 0.008, 0.03, terminal, settle, sd, td, 0.4)
    assert r is not None
    # carry + compresión + ajuste == TR total (telescoping exacto)
    assert abs((r["carry"] + r["compresion"] + r["ajuste"]) - r["tr_total"]) < 1e-9
    # TR real = TR total − ajuste = carry + compresión
    assert abs(r["tr_real"] - (r["carry"] + r["compresion"])) < 1e-9
    # un CER tiene acreción de inflación > 0 en ~4 meses
    assert r["ajuste"] > 0.0


def test_ajuste_cero_sin_indice() -> None:
    """LECAP / tasa fija no ajusta capital → ajuste = 0 y TR real == TR total."""
    settle, terminal, sd, td = _setup_dates()
    code = None
    for c in curves.build_curve_codes().get("lecap", []):
        o = bond_universe.get(c)
        if o is not None and str(getattr(o, "vencimiento", "")) > "2026-11-01":
            code = c
            break
    if code is None:
        pytest.skip("no hay LECAP con vto > terminal")
    r = tr._bond_tr(code, 0.40, 0.42, terminal, settle, sd, td, 0.4)
    assert r is not None
    assert abs(r["ajuste"]) < 1e-9 and abs(r["tr_total"] - r["tr_real"]) < 1e-9


@pytest.mark.asyncio
async def test_total_return_endpoints() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.services import marketdata_store as mds, symbols as syms
    bond_universe.ensure_loaded()
    for c in curves.build_curve_codes()["cer"]:
        mds.get_store().update_from_md(syms.md_symbol(c, "24hs"), {"LA": {"price": 1000.0}, "CL": {"price": 990.0}})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        pg = await ac.get("/total-return?curve=cer")
        assert pg.status_code == 200 and ">Total Return<" in pg.text and 'name="level"' in pg.text
        tb = await ac.get("/total-return/table?curve=cer&plazo=24hs&terminal=31/10/2026"
                          "&mode=params&level=2&slope=200&convex=0&anchor=1")
        assert tb.status_code == 200
        assert "Carry" in tb.text and "Ajuste" in tb.text and "TR total" in tb.text
        assert 'name="y1__TX26"' in tb.text          # TIR final editable por fila
        # Gráfico de columnas apiladas (SVG server-side, sin JS).
        assert 'class="tr-chart"' in tb.text and "<svg" in tb.text
        assert "Ganancia de capital" in tb.text and "Retorno Total" in tb.text


def test_curve_chart_two_series() -> None:
    import math
    rows = [
        {"code": "A", "dur0": 0.5, "y0": 0.40, "y1": 0.30},
        {"code": "B", "dur0": 2.0, "y0": 0.35, "y1": 0.28},
        {"code": "C", "dur0": 4.0, "y0": 0.33, "y1": float("nan")},  # y1 NaN → sólo 'actual'
    ]
    ch = tr.curve_chart(rows)
    assert ch is not None
    assert len(ch["actual"]["nodes"]) == 3 and len(ch["esper"]["nodes"]) == 2
    for s in ("actual", "esper"):
        for n in ch[s]["nodes"]:
            assert math.isfinite(n["cx"]) and math.isfinite(n["cy"])
    assert ch["actual"]["poly"] and ch["yticks"] and ch["xticks"]


def test_curve_chart_empty() -> None:
    assert tr.curve_chart([]) is None
    assert tr.curve_chart([{"code": "X", "dur0": None, "y0": 0.4, "y1": 0.3}]) is None


def test_bar_chart_geometry() -> None:
    """Apilado estilo Excel: positivos arriba, negativos abajo, punto = total,
    y todo dentro del lienzo."""
    items = [
        {"label": "A", "carry": 0.08, "capital": 0.02, "total": 0.10},   # ambos +
        {"label": "B", "carry": 0.08, "capital": -0.015, "total": 0.065},  # capital −
        {"label": "C", "carry": 0.0, "capital": 0.0, "total": 0.0},       # plano
    ]
    ch = tr.bar_chart(items, width=860, height=308)
    assert ch is not None and len(ch["bars"]) == 3
    H = ch["h"]
    for b in ch["bars"]:
        for s in b["segs"]:
            assert s["h"] >= 0 and 0 <= s["y"] <= H and 0 <= s["y"] + s["h"] <= H + 0.5
        if b["dot_y"] is not None:
            assert 0 <= b["dot_y"] <= H
    # carry positivo arranca en la base (toca el 0); capital negativo cuelga del 0.
    bz = ch["zero_y"]
    a_carry = ch["bars"][0]["segs"][0]
    assert abs((a_carry["y"] + a_carry["h"]) - bz) < 0.6        # base del carry = 0
    b_cap = ch["bars"][1]["segs"][1]
    assert abs(b_cap["y"] - bz) < 0.6                            # capital − arranca en 0
    assert b_cap["y"] + b_cap["h"] > bz                          # y baja


@pytest.mark.asyncio
async def test_graficos_nss_params() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.services import marketdata_store as mds, symbols as syms
    import random
    bond_universe.ensure_loaded()
    for c in curves.build_curve_codes()["cer"]:
        mds.get_store().update_from_md(syms.md_symbol(c, "24hs"), {"LA": {"price": round(random.uniform(100, 2000), 2)}})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/graficos/nss?curve=cer&plazo=24hs")
    assert r.status_code == 200 and "β0" in r.text and "τ1" in r.text
