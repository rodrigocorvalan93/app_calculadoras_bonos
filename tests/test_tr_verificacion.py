"""Verificación numérica del Total Return del Escenario contra el núcleo
`rentafija.calcula_total_return` (precio inicial a la TIR de entrada vs precio
final al terminal con la EXIT yield, + cupones cobrados).

Cadena auditada: calcula_total_return → total_return._bond_tr (cache + drift
de índice) → escenario.compute_category (descomposición carry/capital + fx).
Foco en lo agregado: patas duales (TAMAR sin doble conteo de inflación; CER
con inflación) y el ruteo del sendero TAMAR sólo a las patas tamar_leg.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.services import bond_universe, curves, escenario as esc
from backend.services import pricing, total_return as tr_svc


def _terminal(days: int = 120) -> str:
    return (date.today() + timedelta(days=days)).strftime("%d/%m/%Y")


def _settle() -> str:
    return tr_svc.settle_str("24hs")


def _pickable(curve: str) -> str:
    """Primer código de la curva calculable y que no venza antes del terminal."""
    bond_universe.ensure_loaded()
    td = tr_svc._parse_d(_terminal())
    for code in curves.build_curve_codes().get(curve) or []:
        o = bond_universe.get(code)
        v = getattr(o, "vencimiento", None)
        try:
            vd = v.date() if hasattr(v, "date") else v
        except Exception:  # noqa: BLE001
            vd = None
        if vd is None or vd <= td:
            continue
        if pricing.metrics_for_market_price(code, 100.0) is not None:
            return code
    pytest.skip(f"sin bono calculable en la curva {curve}")


def test_lecap_tr_igual_al_calculo_directo() -> None:
    """Tasa fija sin índice: el TR del servicio == calcula_total_return crudo,
    total == real (drift 0) y carry + compresión == real (aditivo exacto)."""
    code = _pickable("lecap")
    terminal, settle = _terminal(), _settle()
    sd, td = tr_svc._parse_d(settle), tr_svc._parse_d(terminal)
    y0, y1 = 0.32, 0.28

    obj = pricing._bond_obj_copy(code)
    manual = tr_svc._pct(obj.calcula_total_return(y0, y1, terminal, settle)
                         .loc["Total Return", "Total Return Valores"])
    carry_manual = tr_svc._pct(obj.calcula_total_return(y0, y0, terminal, settle)
                               .loc["Total Return", "Total Return Valores"])

    res = tr_svc._bond_tr(code, y0, y1, terminal, settle, sd, td, 0.5, want_duration=False)
    assert res is not None
    assert res["tr_real"] == pytest.approx(manual, abs=1e-12)
    assert res["carry"] == pytest.approx(carry_manual, abs=1e-12)
    assert res["carry"] + res["compresion"] == pytest.approx(res["tr_real"], abs=1e-12)
    assert res["tr_total"] == pytest.approx(res["tr_real"], abs=1e-12)   # sin índice: drift 0
    assert res["ajuste"] == pytest.approx(0.0, abs=1e-12)
    # exit yield más baja que la de entrada ⇒ ganancia de capital positiva
    assert res["compresion"] > 0


def test_dual_pata_cer_lleva_inflacion_y_la_tamar_no() -> None:
    """Dual CER/TAMAR (pata base, ajuste CER): la inflación entra como drift
    multiplicativo. Dual TAMAR/CER (pata 'v', ajuste None): la inflación NO la
    toca — tr_total == tr_real exacto (sin doble conteo)."""
    terminal, settle = _terminal(), _settle()
    sd, td = tr_svc._parse_d(settle), tr_svc._parse_d(terminal)
    infl = (0.02,)                                    # 2 %/mes plano

    cer_code = _pickable("dualcer")
    base = tr_svc._bond_tr(cer_code, 0.10, 0.10, terminal, settle, sd, td, 1.0,
                           want_duration=False)                       # sin sendero → serie real
    con_infl = tr_svc._bond_tr(cer_code, 0.10, 0.10, terminal, settle, sd, td, 1.0,
                               want_duration=False, infl_path=infl)
    assert base is not None and con_infl is not None
    assert con_infl["tr_real"] == pytest.approx(base["tr_real"], abs=1e-12)  # base cacheada intacta
    # drift multiplicativo con la MISMA base: total = (1+real)·(1+drift) − 1
    drift = (1.0 + con_infl["tr_total"]) / (1.0 + con_infl["tr_real"]) - 1.0
    months = (td - sd).days / 30.4375
    assert drift > 0
    assert drift == pytest.approx(1.02 ** months - 1.0, rel=0.5)      # orden de magnitud (lag −10d)

    v_code = _pickable("dualtamar_cer")
    v = tr_svc._bond_tr(v_code, 0.30, 0.30, terminal, settle, sd, td, 1.0,
                        want_duration=False, infl_path=infl)
    assert v is not None
    assert v["tr_total"] == pytest.approx(v["tr_real"], abs=1e-12)    # ajuste None → inflación NO pega
    assert v["ajuste"] == pytest.approx(0.0, abs=1e-12)


def test_sendero_tamar_mas_alto_mas_carry_en_pata_v() -> None:
    """Pata TAMAR dual: con el mismo precio de mercado, un sendero TAMAR más
    alto ⇒ más cupón ⇒ TIR de entrada re-derivada más alta y más carry."""
    terminal, settle = _terminal(), _settle()
    sd, td = tr_svc._parse_d(settle), tr_svc._parse_d(terminal)
    code = _pickable("dualtamar_cer")
    px = 100.0
    m = pricing.compute_metrics(code, mode="precio", value=px, include_cashflows=False)
    assert m and not m.get("error")
    y0 = float(m["tirea"])

    lo = tr_svc._bond_tr(code, y0, y0, terminal, settle, sd, td, 1.0,
                         want_duration=False, tamar_path=(20.0,), price=px)
    hi = tr_svc._bond_tr(code, y0, y0, terminal, settle, sd, td, 1.0,
                         want_duration=False, tamar_path=(35.0,), price=px)
    assert lo is not None and hi is not None
    assert hi["y0"] > lo["y0"]                       # más TAMAR ⇒ TIR de entrada más alta
    assert hi["carry"] > lo["carry"]                 # ⇒ más carry


def test_compute_category_rutea_tamar_path_solo_a_patas_tamar(monkeypatch) -> None:
    """El sendero TAMAR llega a _bond_tr SÓLO en categorías tamar_leg (TAMAR
    puro y Dual TAMAR/CER); en la pata CER dual viaja None — así su base
    cacheada no se invalida ni se recomputa el cupón de un no-floater."""
    visto = {}

    def _spy(code, y0, y1, terminal, settle, sd, td, dur, **kw):
        visto[code] = kw.get("tamar_path")
        return None                                   # no importa el resultado

    monkeypatch.setattr(esc.tr, "_bond_tr", _spy)
    row = [{"code": "X1", "tirea": 0.3, "duration": 1.0, "px_calc": 100.0}]
    sendero = (30.0, 32.0)
    esc.compute_category(esc.CAT_BY_KEY["dual_tamar_cer"], row, {"X1": 0.3}, 0.0, 0.0,
                         0.0, _terminal(), _settle(), tamar_path=sendero)
    assert visto["X1"] == sendero
    esc.compute_category(esc.CAT_BY_KEY["dual_cer"], row, {"X1": 0.3}, 0.0, 0.0,
                         0.0, _terminal(), _settle(), tamar_path=sendero)
    assert visto["X1"] is None
    esc.compute_category(esc.CAT_BY_KEY["tamar"], row, {"X1": 0.3}, 0.0, 0.0,
                         0.0, _terminal(), _settle(), tamar_path=sendero)
    assert visto["X1"] == sendero


def test_categoria_total_es_precio_a_precio_con_fx() -> None:
    """Fila del Escenario vs cálculo directo: total en pesos ==
    (1 + TR_nativo(calcula_total_return + drift)) · (1 + fx) − 1, y la
    descomposición carry + capital reconstruye el total exacto."""
    code = _pickable("lecap")
    terminal, settle = _terminal(), _settle()
    sd, td = tr_svc._parse_d(settle), tr_svc._parse_d(terminal)
    y0, y1 = 0.31, 0.27
    fx = 0.05                                         # 5 % de deva overlay (sintético)

    nativo = tr_svc._bond_tr(code, y0, y1, terminal, settle, sd, td, 0.5, want_duration=False)
    cat = esc.Cat("test", "Test", "lecap", 0.0, 1e9, "ccl")
    res = esc.compute_category(cat, [{"code": code, "tirea": y0, "duration": 0.5,
                                      "px_calc": 100.0}],
                               {code: y1}, fx, fx, 0.02, terminal, settle)
    assert res["n"] == 1
    r = res["rows"][0]
    assert r["total"] == pytest.approx((1 + nativo["tr_total"]) * (1 + fx) - 1, abs=1e-12)
    assert r["carry"] + r["capital"] == pytest.approx(r["total"], abs=1e-12)
