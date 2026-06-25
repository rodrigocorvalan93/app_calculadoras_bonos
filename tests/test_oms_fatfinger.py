"""OMS fat-finger / es-AR price-parse hardening (audit C1).

Cubre: el parser es-AR único (`parse_ar_num`, fin del sub-precio 1000×) y la
cascada de referencia en `oms.validate` — mercado → valor técnico (teórico) →
confirmación manual cuando no hay ninguna.
"""
from __future__ import annotations

from backend.locale_ar import parse_ar_num
from backend.services import oms


def test_parse_ar_num_price_thousands():
    assert parse_ar_num("204.600") == 204600.0       # EL bug: antes float()=204,6
    assert parse_ar_num("204.600,00") == 204600.0
    assert parse_ar_num("1.234,56") == 1234.56
    assert parse_ar_num("98,50") == 98.5
    assert parse_ar_num("11.75") == 11.75            # %: 1-2 dígitos → decimal
    assert parse_ar_num("1.000") == 1000.0           # 3 dígitos → miles
    assert parse_ar_num("inf") is None and parse_ar_num("nan") is None
    assert parse_ar_num("-5", allow_negative=False) is None
    assert parse_ar_num("") is None and parse_ar_num("xyz") is None


def test_validate_market_band():
    # Con cotización de mercado: en banda pasa; sub-precio 1000× rebota.
    assert oms.validate("AL30", "buy", 1000, 100.0, "acct", 100.0, "USD", "limit") is None
    m = oms.validate("AL30", "sell", 1000, 0.1, "acct", 100.0, "USD", "limit")
    assert m and "banda" in m.lower() and "mercado" in m.lower()


def test_validate_theo_fallback_no_market():
    # Sin mercado pero con valor técnico: precio sano pasa, 1000× abajo rebota.
    assert oms.validate("PSSXO", "sell", 1000, 100.0, "acct", None, "ARS", "limit",
                        theo_ref=100.0) is None
    m = oms.validate("PSSXO", "sell", 1000, 0.1, "acct", None, "ARS", "limit",
                     theo_ref=100.0)
    assert m and "técnico" in m.lower()              # el agujero del ON ilíquido, cerrado


def test_validate_no_ref_requires_manual_confirm():
    # Sin mercado NI teórico: bloquea salvo confirmación manual explícita.
    m = oms.validate("RARE", "sell", 1000, 0.1, "acct", None, "ARS", "limit", theo_ref=None)
    assert m and "confirm" in m.lower()
    assert oms.validate("RARE", "sell", 1000, 0.1, "acct", None, "ARS", "limit",
                        theo_ref=None, confirmed=True) is None


def test_validate_market_order_uses_theo_for_notional():
    # Market sin last_ref usa el teórico para estimar notional vs el tope.
    from backend.config import settings
    huge = settings.oms_max_notional_usd * 100 / 1.0      # qty que excede el tope USD
    m = oms.validate("GD30", "buy", huge, None, "acct", None, "USD", "market", theo_ref=100.0)
    assert m and "notional" in m.lower()
