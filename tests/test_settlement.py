"""Settlement / plazo — la TIR se descuenta desde la fecha de liquidación correcta.

Regresión de la auditoría:
- Curvas valuaba el plazo CI a t+1 (no pasaba `settle`): hasta ~200 bps de sesgo
  en letras cortas. `metrics_for_market_price` ya aceptaba `settle`; ahora todo
  el pipeline de curvas lo pasa, y la key del cache lo separa (CI ≠ 24hs).
- `settle_str("24hs")` devolvía HOY en día hábil (t+0/CI) en vez de t+1.
- Una fecha de liquidación explícita pero inválida se descartaba en silencio y
  se valuaba a la fecha default; ahora avisa.
"""
from __future__ import annotations

from datetime import date

import pytest

from backend.services import bond_universe, curves, pricing
from backend.services import total_return as tr


def _any_code() -> str:
    bond_universe.ensure_loaded()
    for codes in curves.build_curve_codes().values():
        for c in codes or []:
            return c
    raise AssertionError("universo de bonos vacío en el entorno de test")


def test_settle_str_24hs_es_t1_no_ci() -> None:
    from backend.locale_ar import hoy_ba

    ci = pricing.settlement_date_str("CI")            # hoy hábil (t+0)
    s24 = tr.settle_str("24hs")                        # debe ser t+1 hábil
    assert s24 != ci                                   # 24hs NO liquida a CI
    # "hoy" en fecha BA: con date.today() naive (UTC) el test fallaba en la
    # ventana 00:00–03:00 UTC, cuando el server ya cruzó la medianoche y BA no.
    assert s24 != hoy_ba().strftime("%d/%m/%Y")        # ni a hoy


def test_compute_metrics_settle_invalido_avisa() -> None:
    code = _any_code()
    m = pricing.compute_metrics(code, "precio", 100.0, settle="32/13/2026")
    assert m.get("error") and "inválida" in m["error"].lower()
    # None sigue siendo el default legítimo (no dispara el error de settle)
    m2 = pricing.compute_metrics(code, "precio", 100.0, settle=None)
    assert "liquidación inválida" not in (m2.get("error") or "").lower()


def test_settle_ci_vs_t1_difiere_la_tir() -> None:
    """CI (t+0) y 24hs (t+1) descuentan desde fechas distintas → TIRs distintas
    en una letra corta. Antes Curvas ignoraba el settle y ambas daban lo mismo."""
    bond_universe.ensure_loaded()
    ci = pricing.settlement_date_str("CI")
    for code in (curves.build_curve_codes().get("lecap") or []):
        m_ci = pricing.metrics_for_market_price(code, 95.0, ci)
        m_t1 = pricing.metrics_for_market_price(code, 95.0, None)   # None → t+1
        if (m_ci and m_t1 and m_ci.get("tirea") == m_ci.get("tirea")
                and m_t1.get("tirea") == m_t1.get("tirea")):
            assert abs(m_ci["tirea"] - m_t1["tirea"]) > 1e-9
            return
    pytest.skip("sin LECAP computable en el universo de test")
