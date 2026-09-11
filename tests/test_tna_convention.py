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


def test_dlk_corporativo_90_360() -> None:
    # El mercado cotiza los DLK corporativos en 90/360 (los soberanos no).
    assert _conv(moneda="ARS", ajuste_sobre_capital="Dolar A3500",
                 clasificacion="Corporativo Dolar Linked") == ("90/360", 90, 360, "linear")


def test_dlk_soberano_90_365() -> None:
    assert _conv(moneda="ARS", ajuste_sobre_capital="Dolar A3500",
                 clasificacion="Soberano") == ("90/365", 90, 365, "linear")


def test_more_specific_branches_win_over_hard_dollar() -> None:
    # Ordering: a VARIABLE bond tagged USB is still 90/365 (the rate
    # convention runs before the hard-dollar check).
    assert _conv(moneda="USB", tipo_tasa_interes="VARIABLE") == ("90/365", 90, 365, "linear")
    # CER adjustment wins too (y desde 08/09 la TNA CER se reexpresa 180/360).
    assert _conv(moneda="USD", ajuste_sobre_capital="CER") == ("180/360", 180, 360, "linear")


def test_cer_y_uva_reexpresan_tna_180_360() -> None:
    # Pedido del desk (08/09): CER y UVA reexpresan TIR→TNA en base 360
    # (el devengamiento del cashflow no cambia — sólo el label TNA).
    assert _conv(moneda="ARS", ajuste_sobre_capital="CER") == ("180/360", 180, 360, "linear")
    assert _conv(moneda="ARS", ajuste_sobre_capital="CER PROYECTADO") == ("180/360", 180, 360, "linear")
    assert _conv(moneda="ARS", ajuste_sobre_capital="UVA") == ("180/360", 180, 360, "linear")
    assert _conv(moneda="ARS", ajuste_sobre_capital="UVA PROYECTADO") == ("180/360", 180, 360, "linear")


# ── Referencia 1816: reexpresión TNA bajo SU convención (no cambia el cálculo) ──

def test_tna_bajo_conv_1816_reexpresa_por_convencion() -> None:
    tirea = 0.15
    # lineal freq/base
    assert pricing.tna_bajo_conv_1816(_Stub(), tirea, "180-360") == \
        ((1 + tirea) ** (180 / 360) - 1) * (360 / 180)
    assert pricing.tna_bajo_conv_1816(_Stub(), tirea, "90-360") == \
        ((1 + tirea) ** (90 / 360) - 1) * (360 / 90)
    # 32-365 capitaliza cada 32 días (TAMAR/duales), no lineal
    assert pricing.tna_bajo_conv_1816(_Stub(), tirea, "32-365") == \
        ((1 + tirea) ** (32 / 365) - 1) * (365 / 32)
    # plazo-rem usa días remanentes del bono
    assert pricing.tna_bajo_conv_1816(_Stub(dias_remanentes=200), tirea, "plazo-rem") == \
        ((1 + tirea) ** (200 / 365) - 1) * (365 / 200)


def test_tna_bajo_conv_1816_bordes_nan() -> None:
    import math
    assert math.isnan(pricing.tna_bajo_conv_1816(_Stub(), 0.15, None))
    assert math.isnan(pricing.tna_bajo_conv_1816(_Stub(), float("nan"), "180-360"))
    assert math.isnan(pricing.tna_bajo_conv_1816(_Stub(), 0.15, "raro-999"))
    # plazo-rem sin días remanentes → NaN (no inventa)
    assert math.isnan(pricing.tna_bajo_conv_1816(_Stub(dias_remanentes=0), 0.15, "plazo-rem"))


def test_conv_1816_por_curva() -> None:
    from backend.services import bond_universe, curves
    bond_universe.ensure_loaded()
    # Diferencias reales vs nuestra tabla (donde 1816 diverge): TAMAR sob 32-365,
    # DLK sob 180-360, corp inflación 90-360; y coincidencias: CER sob 180-360.
    assert curves.CONV_1816["tamar"] == "32-365"
    assert curves.CONV_1816["dolarlinked"] == "180-360"
    assert curves.CONV_1816["corp_uva"] == "90-360"
    assert curves.CONV_1816["cer"] == "180-360"
    # Un ticker que no cae en ninguna curva → None (sin referencia inventada)
    assert curves.conv_1816_for("NOEXISTE_XYZ") is None
