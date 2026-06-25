"""Escenario multi-activo — TR EN PESOS por categoría: additividad
(carry+capital=total), overlay FX hard-dollar (TR_pesos=(1+TR_usd)(1+ccl)−1),
y columnas multiplicativas neto-fondeo / neto-FX. Núcleo = total_return._bond_tr.
"""
from __future__ import annotations

import math

import pytest

from backend.services import bond_universe, curves, escenario as esc, total_return as tr


def _dates():
    bond_universe.ensure_loaded()
    settle = tr.settle_str("24hs")
    terminal = "31/10/2026"
    return settle, terminal, tr._parse_d(settle), tr._parse_d(terminal)


def test_helpers_buckets_fx_exit():
    c = esc.CAT_BY_KEY["cer_medio"]
    assert esc.in_bucket(c, 1.0) and not esc.in_bucket(c, 0.4) and not esc.in_bucket(c, 1.6)
    assert esc.fx_of(esc.CAT_BY_KEY["globales"], 0.085, 0.07) == 0.085   # CCL
    assert esc.fx_of(esc.CAT_BY_KEY["bonares"], 0.085, 0.07) == 0.07     # MEP
    assert esc.fx_of(esc.CAT_BY_KEY["cer_largo"], 0.085, 0.07) == 0.0    # ARS puro
    assert esc.fx_of(esc.CAT_BY_KEY["dlk"], 0.085, 0.07) == 0.0          # deva ∈ ajuste
    assert abs(esc.exit_ytm(0.25, 0, 5.0) - 0.25) < 1e-12               # plano
    assert abs(esc.exit_ytm(0.25, 200, 2.0, anchor=1.0) - 0.27) < 1e-12  # +200bps·(2−1)


def test_ars_fx_cero_y_columnas_neto():
    """ARS puro: fx=0 ⇒ TR_pesos = TR nativo; neto-fondeo y neto-FX
    multiplicativos (réplica de la aritmética del Excel)."""
    settle, terminal, sd, td = _dates()
    cat = esc.CAT_BY_KEY["cer_corto"]
    rows = [{"code": "TX26", "tirea": 0.01, "duration": 0.38, "px_calc": 700.0}]
    cauc, ccl = 0.081, 0.085
    res = esc.compute_category(cat, rows, {"TX26": 0.03}, fx_proy=0.0, ccl_proy=ccl,
                               cauc=cauc, terminal=terminal, settle=settle)
    assert res["n"] == 1
    r = res["rows"][0]
    assert abs((r["carry"] + r["capital"]) - r["total"]) < 1e-12          # additivo
    native = tr._bond_tr("TX26", 0.01, 0.03, terminal, settle, sd, td, 0.38)
    assert abs(r["total"] - native["tr_total"]) < 1e-9                    # fx=0
    assert abs(r["neto_fondeo"] - ((1 + r["total"]) / (1 + cauc) - 1)) < 1e-12
    assert abs(r["neto_fx"] - ((1 + r["total"]) / (1 + ccl) - 1)) < 1e-12
    # resumen = promedio (1 bono ⇒ igual a la fila)
    assert abs(res["summary"]["total"] - r["total"]) < 1e-12


def test_hard_dollar_overlay_ccl():
    """Global: TR_pesos = (1+TR_usd)·(1+ccl)−1 ; neto-FX vuelve a USD."""
    settle, terminal, sd, td = _dates()
    cat = esc.CAT_BY_KEY["globales"]
    code = next((c for c in curves.build_curve_codes()["globales"]
                 if tr._bond_tr(c, 0.10, 0.09, terminal, settle, sd, td, 2.0)), None)
    if code is None:
        pytest.skip("sin global calculable en el universo")
    ccl = 0.085
    res = esc.compute_category(cat, [{"code": code, "tirea": 0.10, "duration": 2.0}],
                               {code: 0.09}, fx_proy=ccl, ccl_proy=ccl, cauc=0.081,
                               terminal=terminal, settle=settle)
    r = res["rows"][0]
    native = tr._bond_tr(code, 0.10, 0.09, terminal, settle, sd, td, 2.0)
    assert abs(native["ajuste"]) < 1e-9                                   # hard-dollar: sin ajuste
    assert abs(r["total"] - ((1 + native["tr_total"]) * (1 + ccl) - 1)) < 1e-9
    assert abs(r["carry"] - ((1 + native["carry"]) * (1 + ccl) - 1)) < 1e-9
    assert abs((r["carry"] + r["capital"]) - r["total"]) < 1e-12
    assert abs(r["neto_fx"] - native["tr_total"]) < 1e-9                  # (1+peso)/(1+ccl)-1 = TR_usd


def test_num_rejects_non_finite():
    from backend.routes.escenario import _num
    assert _num("inf") is None and _num("-inf") is None
    assert _num("nan") is None and _num("1e999") is None     # 1e999 → inf
    assert _num("11,75") == 11.75 and _num("1.234,5") == 1234.5 and _num("20") == 20.0


def test_exit_ytm_clamped_to_band():
    # pendiente extrema no manda la TIR de salida bajo −100 % ni sobre 500 %
    assert esc.exit_ytm(0.05, -5000, 5.0, 1.0) == -0.99
    assert esc.exit_ytm(1.0, 9000, 6.0, 1.0) == 5.0
    assert abs(esc.exit_ytm(0.10, 0, 3.0) - 0.10) < 1e-12


def test_bar_chart_survives_non_finite():
    # inf/nan en segmentos o total no deben romper la geometría (antes: SVG height="nan")
    items = [
        {"label": "ok", "carry": 0.05, "capital": 0.01, "total": 0.06},
        {"label": "inf", "carry": float("inf"), "capital": 0.0, "total": float("inf")},
        {"label": "nan", "carry": float("nan"), "capital": 0.02, "total": float("nan")},
    ]
    ch = tr.bar_chart(items)
    assert ch is not None
    for b in ch["bars"]:
        assert b["dot_y"] is None or math.isfinite(b["dot_y"])
        for s in b["segs"]:
            assert math.isfinite(s["y"]) and math.isfinite(s["h"])
    for t in ch["yticks"]:
        assert math.isfinite(t["y"]) and math.isfinite(t["v"])
    assert math.isfinite(ch["zero_y"])


@pytest.mark.asyncio
async def test_escenario_table_adversarial_inputs():
    """Entradas degeneradas (-100 % de deva/caución, no-finitos, pendiente brutal)
    no deben 500-ear: deben renderizar 200 con celdas '—' donde corresponda."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.services import marketdata_store as mds, symbols as syms
    bond_universe.ensure_loaded()
    for c in curves.build_curve_codes()["cer"]:
        mds.get_store().update_from_md(syms.md_symbol(c, "24hs"),
                                       {"LA": {"price": 1000.0}, "CL": {"price": 990.0}})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        for qs in ("ccl_deva=-100&mep_deva=-100",            # neto_fx → None (1+ccl == 0)
                   "cauc_plazo=-100",                         # neto_fondeo → None (1+cauc == 0)
                   "ccl_deva=inf&cauc_tna=nan",               # no-finitos → caen al default
                   "ytm_cer_corto=5&slope_cer_corto=-99999"):  # exit YTM extremo → clamp
            r = await ac.get(f"/escenario/table?plazo=24hs&terminal=31/12/2026&{qs}")
            assert r.status_code == 200, f"{qs} -> {r.status_code}"
            assert "Traceback" not in r.text and 'height="nan"' not in r.text


@pytest.mark.asyncio
async def test_escenario_endpoints():
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.services import marketdata_store as mds, symbols as syms
    bond_universe.ensure_loaded()
    for curve, px in (("cer", 1000.0), ("lecap", 120.0)):
        for c in curves.build_curve_codes()[curve]:
            mds.get_store().update_from_md(syms.md_symbol(c, "24hs"),
                                           {"LA": {"price": px}, "CL": {"price": px * 0.99}})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        pg = await ac.get("/escenario")
        assert pg.status_code == 200 and "retorno esperado en pesos" in pg.text
        assert 'name="ccl_deva"' in pg.text and 'name="ytm_cer_corto"' in pg.text
        tb = await ac.get("/escenario/table?plazo=24hs&terminal=31/12/2026"
                          "&cauc_tna=20&ccl_deva=11,75&mep_deva=11,75&ytm_cer_corto=5&slope_cer_corto=0")
        assert tb.status_code == 200
        assert 'class="tr-chart"' in tb.text                       # gráfico por categoría
        assert "Total Return" in tb.text and "Neto de FX" in tb.text
        assert "CER corto" in tb.text and 'name="y1__' in tb.text  # banda + Exit YTM editable


def test_bond_tr_want_duration_skips_durf_same_math():
    """El comparador llama `_bond_tr(..., want_duration=False)`: ahorra el 3er
    cálculo (dur_f, que no usa) sin cambiar la matemática de TR."""
    settle, terminal, sd, td = _dates()
    full = tr._bond_tr("TX26", 0.01, 0.03, terminal, settle, sd, td, 0.4, want_duration=True)
    fast = tr._bond_tr("TX26", 0.01, 0.03, terminal, settle, sd, td, 0.4, want_duration=False)
    assert full and fast
    assert fast["dur_f"] is None                              # saltea el calc de duration final
    assert abs(full["tr_total"] - fast["tr_total"]) < 1e-12   # TR idéntico
    assert abs(full["carry"] - fast["carry"]) < 1e-12


def test_infl_override_cer_solo_mueve_ajuste():
    """El override de inflación mueve el AJUSTE de CER/UVA = (1+infl)^meses − 1,
    pero NO la parte cara (carry/tr_real) — esa es real, libre de inflación."""
    settle, terminal, sd, td = _dates()
    base = tr._bond_tr("TX26", 0.05, 0.05, terminal, settle, sd, td, 0.5, want_duration=False)
    inf2 = tr._bond_tr("TX26", 0.05, 0.05, terminal, settle, sd, td, 0.5,
                       want_duration=False, infl_monthly=0.02)
    inf5 = tr._bond_tr("TX26", 0.05, 0.05, terminal, settle, sd, td, 0.5,
                       want_duration=False, infl_monthly=0.05)
    assert base and inf2 and inf5
    assert abs(inf2["carry"] - base["carry"]) < 1e-12        # carry no cambia
    assert abs(inf5["tr_real"] - base["tr_real"]) < 1e-12    # tr_real no cambia
    assert inf5["ajuste"] > inf2["ajuste"]                   # más inflación → más ajuste
    months = (td - sd).days / 30.4375
    drift2 = (1 + inf2["tr_total"]) / (1 + inf2["tr_real"]) - 1
    assert abs(drift2 - ((1.02) ** months - 1.0)) < 1e-9     # = (1+infl)^meses − 1


def test_infl_override_no_toca_dlk():
    """La inflación NO toca el ajuste de los dollar-linked (A3500 = deva, no CPI)."""
    settle, terminal, sd, td = _dates()
    code = next(iter(curves.build_curve_codes().get("dolarlinked", [])), None)
    if not code:
        pytest.skip("sin dollar-linked")
    base = tr._bond_tr(code, 0.05, 0.05, terminal, settle, sd, td, 1.0, want_duration=False)
    inf = tr._bond_tr(code, 0.05, 0.05, terminal, settle, sd, td, 1.0,
                      want_duration=False, infl_monthly=0.10)
    if not base or not inf:
        pytest.skip("dlk no calculable")
    assert abs(inf["ajuste"] - base["ajuste"]) < 1e-9        # mismo ajuste (A3500), no inflación


def test_chart_from_categories():
    cats = [
        {"label": "A", "summary": {"carry": 0.08, "capital": 0.01, "total": 0.09}},
        {"label": "B", "summary": {"carry": 0.10, "capital": -0.02, "total": 0.08}},
        {"label": "C", "summary": None, "n": 0},   # sin bonos → se omite
    ]
    ch = esc.chart_from_categories(cats)
    assert ch is not None and len(ch["bars"]) == 2
    assert ch["bars"][0]["label"] == "A"
