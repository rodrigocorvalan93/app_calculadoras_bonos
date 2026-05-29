"""TNA convention hard-dollar detection (backend/services/pricing.py).

Regression guard for the FX-leg refactor: `Moneda` now encodes the quote
leg (USD = cable, USB = MEP), so the hard-dollar 180/360 convention must
be detected from the leg currency OR the classification — never from
`moneda == "USD"` alone, which would drop USB (MEP) and pesos-quoted
hard-dollar bonds to the días/365 default.
"""
from __future__ import annotations

from backend.services import pricing


class _Stub:
    """Minimal stand-in: tna_convention only does getattr on the bond."""

    def __init__(self, **kw: object) -> None:
        for k, v in kw.items():
            setattr(self, k, v)


def _conv(**kw: object):
    return pricing.tna_convention(_Stub(**kw))


def test_usd_cable_is_hard_dollar() -> None:
    assert _conv(moneda="USD") == ("180/360", 180, 360, "linear")


def test_usb_mep_is_hard_dollar() -> None:
    # The fix: USB (MEP) is USD-cashflow too → 180/360, not días/365.
    assert _conv(moneda="USB") == ("180/360", 180, 360, "linear")


def test_pesos_quoted_hard_dollar_via_classification() -> None:
    # A hard-dollar bond quoted in pesos (Moneda=ARS) is still 180/360,
    # detected from the classification.
    assert _conv(moneda="ARS", clasificacion="Corporativo Hard Dolar",
                 dias_remanentes=300) == ("180/360", 180, 360, "linear")


def test_ars_rate_bond_not_hard_dollar() -> None:
    # No false positive: an ARS fixed-rate bond keeps días/365.
    assert _conv(moneda="ARS", clasificacion="Soberano ARS Tasa Fija",
                 dias_remanentes=120) == ("120/365", 120, 365, "linear")


def test_more_specific_branches_win_over_hard_dollar() -> None:
    # Ordering: a VARIABLE bond tagged USB is still 90/365 (the rate
    # convention runs before the hard-dollar check).
    assert _conv(moneda="USB", tipo_tasa_interes="VARIABLE") == ("90/365", 90, 365, "linear")
    # CER adjustment wins too.
    assert _conv(moneda="USD", ajuste_sobre_capital="CER") == ("180/365", 180, 365, "linear")
