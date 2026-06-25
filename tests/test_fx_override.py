"""fx_override aislamiento (audit C2).

Un what-if de FX (`/yas/recompute` con fx_override) NO debe corromper la serie
A3500 global del proceso. Antes escribía `rentafija.inputs['a3500']` sin restaurar
(y con clave string) → todo cálculo DLK/A3500 posterior quedaba podrido.
"""
from __future__ import annotations

import pytest

from backend.services import bond_universe, curves, pricing


def _a3500_state():
    import rentafija
    s = rentafija.inputs["a3500"]
    return (len(s.index), float(s.iloc[-1]["tca3500"]))


def _dlk_code():
    bond_universe.ensure_loaded()
    return next(iter(curves.build_curve_codes().get("dolarlinked", [])), None)


def test_fx_override_no_contamina_a3500_global():
    code = _dlk_code()
    if not code:
        pytest.skip("sin bonos dolar-linked en el universo")
    before = _a3500_state()
    base = pricing.compute_metrics(code, "precio", 100.0)
    tir0 = base.get("tirea")

    # what-if con un FX absurdo
    wif = pricing.compute_metrics(code, "precio", 100.0, fx_override=9999.0)
    assert wif.get("error") is None

    # 1) la serie A3500 global quedó intacta (largo + último valor restaurados)
    assert _a3500_state() == before, "fx_override dejó la serie A3500 contaminada"
    # 2) un cálculo posterior SIN override reproduce exactamente el base
    again = pricing.compute_metrics(code, "precio", 100.0)
    t_again, t0 = again.get("tirea"), tir0
    assert (t_again != t_again and t0 != t0) or t_again == t0  # iguales (o ambos NaN)


def test_fx_override_si_afecta_el_calc_objetivo():
    """El override debe FLUIR al cálculo del bono objetivo (antes, por la clave
    string, ni eso hacía bien)."""
    code = _dlk_code()
    if not code:
        pytest.skip("sin bonos dolar-linked")
    base = pricing.compute_metrics(code, "precio", 100.0).get("tirea")
    wif = pricing.compute_metrics(code, "precio", 100.0, fx_override=9999.0).get("tirea")
    if base is None or base != base:
        pytest.skip("bono base no calculable")
    assert wif is not None and wif == wif and abs(wif - base) > 1e-9
