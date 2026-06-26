"""Regresiones de la revisión de código: parsers es-AR unificados (miles) y la
variación SIOPEL del dólar oficial (venía 100× por usar ar_pct sobre puntos)."""
from __future__ import annotations

import pytest


# ── parsers es-AR: el caso "sólo miles" (antes daba None o 1000× chico) ───────
def test_route_parsers_manejan_miles():
    from backend.routes import escenario as esc_r, futuros as fut_r, total_return as tr_r, yas as yas_r
    # yas: VN con separador de miles → ya no cae al default silencioso
    assert yas_r._parse_ar_number("2.000.000") == 2_000_000.0
    assert yas_r._parse_ar_number("500.000") == 500_000.0
    assert yas_r._parse_ar_number("87,30") == 87.30
    # futuros: spot override → 1435, no 1,435 (positivo)
    assert fut_r._parse_num("1.435") == 1435.0
    assert fut_r._parse_num("1.435,50") == 1435.50
    assert fut_r._parse_num("0") is None and fut_r._parse_num("-5") is None    # sigue exigiendo > 0
    # total_return / escenario: mismo parser canónico
    assert tr_r._num("1.000") == 1000.0 and esc_r._num("11,75") == 11.75
    assert esc_r._num("inf") is None and tr_r._num("nan") is None              # rechaza no-finitos


def test_curves_price_override_acepta_miles():
    # un what-if de precio en decenas de miles (DICP/PARP) ya no se descarta
    from types import SimpleNamespace

    from backend.routes import curves as cr

    class _QP:
        def multi_items(self):
            return [("price_DICP", "50.000,00"), ("price_TX26", "98,5"), ("price_X", "-3")]
    req = SimpleNamespace(query_params=_QP())
    ov = cr._price_overrides(req)
    assert ov["DICP"] == 50_000.0 and ov["TX26"] == 98.5 and "X" not in ov     # negativo fuera


# ── SIOPEL: la variación de MAE viene en pp; debe renderizar como fracción ────
def test_dolares_oficial_variacion_no_100x():
    from backend.main import app
    env = app.state.templates.env
    row = {"ticker": "USD/ARS", "segmento": "MAE", "plazo": "SPOT", "moneda": "ARS",
           "precioUltimo": 1478.04, "precioCierreAnterior": 1473.9, "variacion": 0.28,
           "precioMinimo": 1470.0, "precioMaximo": 1480.0, "volumenOperado": 1e9,
           "horaUltima": "17:00"}
    html = env.get_template("partials/dolares_oficial.html").render(
        siopel=[row], oficial={"last": 1478.04, "var_pct": 0.0028})
    assert "0,28%" in html            # 0,28 pp → 0,28% (no "28,00%")
    assert "28,00%" not in html
