"""=OMS.PRECIO tiene que ser el INVERSO EXACTO de =OMS.TIREA.

Caso real (03/09): TIREA("TX26";735,4) → 3,75% OK, pero PRECIO devolvía
3.653,6 — era `precio_clean_pct` (clean por 100 de RESIDUAL) y TX26 cotiza
DIRTY por 100 nominal y amortizó al 20% de residual: el clean-por-residual da
~5× el precio de pantalla. El campo nuevo `precio_mercado_pct` devuelve la
convención que `calcula_tirea` acepta (clean para CLEAN-quoted como GD/AL,
dirty para CER/lecaps/DLK) y cierra el round-trip para todos los tipos."""
from __future__ import annotations

import pytest

from backend.services import curves, pricing


def _round_trip(code: str, px: float, settle: str | None = None) -> None:
    m1 = pricing.compute_metrics(code, "precio", px, settle=settle)
    assert m1["tirea"] == m1["tirea"], f"{code}: tirea NaN"
    # en modo precio, el campo mercado ES el input (misma convención)
    assert m1["precio_mercado_pct"] == pytest.approx(px, abs=1e-6)
    m2 = pricing.compute_metrics(code, "tir", m1["tirea"], settle=settle)
    assert m2["precio_mercado_pct"] == pytest.approx(px, abs=1e-4), \
        f"{code}: PRECIO(TIREA({px})) devolvió {m2['precio_mercado_pct']}"


def test_round_trip_lecap_dirty() -> None:
    code = None
    for c in curves.build_curve_codes().get("lecap") or []:
        t = pricing.compute_metrics(c, "precio", 100.0)["tirea"]
        if t == t:                                   # primera con TIR calculable
            code = c
            break
    assert code, "sin lecap calculable en las curvas"
    _round_trip(code, 100.0)


def test_round_trip_gd30_clean() -> None:
    _round_trip("GD30", 78.5)


def test_round_trip_tx26_dirty_amortizado_cer() -> None:
    """El caso del reporte: DIRTY + AMORTIZABLE (VR 20%) + CER. Settle fijo
    dentro del backup de CER para correr sin red."""
    m1 = pricing.compute_metrics("TX26", "precio", 735.4, settle="19/08/2026")
    assert m1["valor_residual"] == pytest.approx(20.0)
    assert m1["precio_clean_pct"] > 3000             # clean-por-residual: NO es inverso
    _round_trip("TX26", 735.4, settle="19/08/2026")


def test_excel_calc_expone_precio_mercado() -> None:
    """La plomería del add-in (=OMS.PRECIO lee precio_mercado_pct del batch)."""
    from backend.routes.excel import _calc_one
    out = _calc_one("GD30", "tir", 0.145, "24hs", None)
    assert out.get("precio_mercado_pct") == pytest.approx(out.get("precio_clean_pct"))
