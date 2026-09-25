"""bench_override — TAMAR / BADLAR aplicable a mano en YAS.

- `rentafija.Bono.aplica_nivel_variable`: la serie proyectada (plana en el
  promedio 5 ruedas desde la última observación, indices.py) se reemplaza por
  el nivel del usuario SOBRE LA COPIA; con el nivel = ese promedio el cupón (y
  el precio) queda idéntico al de siempre.
- `pricing.compute_metrics(bench_override=…)`: cupón + benchmark del margen
  (modo margen, Margen TNA, card "aplicable (custom)"); no muta el singleton;
  no hace nada en un bono que no es floater. `tr_puntual` lo respeta.
- `/yas/recompute` y `/yas/tr` con el campo `bench_override`.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from backend.services import bond_universe, curves, pricing


def _floater(index: str, tipo: str) -> str | None:
    """Primer código de las curvas con ese índice y tipo de tasa que pricea."""
    bond_universe.ensure_loaded()
    for codes in curves.build_curve_codes().values():
        for c in codes or []:
            m = pricing.bond_meta(c) or {}
            if (m.get("index") or "").upper() != index or (m.get("tipo_tasa_interes") or "").upper() != tipo:
                continue
            r = pricing.compute_metrics(c, "tir", 0.30, include_cashflows=False)
            if not r.get("error") and np.isfinite(r.get("precio", float("nan"))) and np.isfinite(r.get("benchmark_pct", float("nan"))):
                return c
    return None


def _fijo() -> str | None:
    bond_universe.ensure_loaded()
    for c in curves.build_curve_codes().get("lecap") or []:
        r = pricing.compute_metrics(c, "tir", 0.30, include_cashflows=False)
        if not r.get("error") and np.isfinite(r.get("precio", float("nan"))):
            return c
    return None


def _check_floater(code: str) -> None:
    obj = bond_universe.get(code)
    intereses_antes = np.array(obj.intereses, dtype=float).copy()
    base = pricing.compute_metrics(code, "tir", 0.30, include_cashflows=False)
    bench = base["benchmark_pct"]
    assert base["bench_custom"] is False and "avg 5d" in base["index_applied"]["label"]

    # 1) con el nivel = promedio 5 ruedas (lo que ya proyecta indices.py) el
    #    cupón y el precio son EXACTAMENTE los de siempre
    mismo = pricing.compute_metrics(code, "tir", 0.30, include_cashflows=False, bench_override=bench)
    assert mismo["bench_custom"] is True
    assert mismo["precio"] == pytest.approx(base["precio"], rel=1e-12)
    assert mismo["tna"] == pytest.approx(base["tna"], rel=1e-12)

    # 2) +10 pp de tasa aplicable → cupones más altos → a la misma TIR el precio sube;
    #    el benchmark del margen es el nivel custom (card + Margen TNA)
    wif = pricing.compute_metrics(code, "tir", 0.30, include_cashflows=False, bench_override=bench + 10.0)
    assert wif.get("error") is None and wif["bench_custom"] is True
    assert wif["precio"] > base["precio"]
    assert wif["benchmark_pct"] == pytest.approx(bench + 10.0)
    assert wif["index_applied"]["label"].endswith("(custom)") and wif["index_applied"]["value"] == pytest.approx(bench + 10.0)
    tipo = (pricing.bond_meta(code) or {}).get("tipo_tasa_interes", "").upper()
    if tipo == "VARIABLE":
        assert wif["margen_tna"] == pytest.approx(wif["tna"] - (bench + 10.0) / 100.0, abs=1e-12)
    else:                                                     # VARIABLE_CAP: TNA 32/365 equivalente
        tna_eq = ((1.0 + wif["tirea"]) ** (32.0 / 365.0) - 1.0) * (365.0 / 32.0)
        assert wif["margen_tna"] == pytest.approx(tna_eq - (bench + 10.0) / 100.0, abs=1e-12)

    # 3) modo MARGEN: el objetivo es bench_custom + margen (round-trip por la
    #    misma convención) — sólo en VARIABLE puro, donde TNA = bench + margen
    if tipo == "VARIABLE":
        mg = pricing.compute_metrics(code, "margen", 0.05, include_cashflows=False, bench_override=30.0)
        assert mg.get("error") is None
        assert mg["tna"] == pytest.approx(0.35, abs=1e-9) and mg["margen_tna"] == pytest.approx(0.05, abs=1e-9)

    # 4) el singleton no se tocó: cupones intactos y un cálculo sin override
    #    reproduce el base
    assert np.allclose(np.array(bond_universe.get(code).intereses, dtype=float), intereses_antes)
    again = pricing.compute_metrics(code, "tir", 0.30, include_cashflows=False)
    assert again["precio"] == pytest.approx(base["precio"], rel=1e-12) and again["bench_custom"] is False


def test_tamar_variable() -> None:
    code = _floater("TAMAR", "VARIABLE")
    if not code:
        pytest.skip("sin floater TAMAR VARIABLE calculable en las curvas")
    _check_floater(code)


def test_badlar_variable() -> None:
    code = _floater("BADLAR", "VARIABLE")
    if not code:
        pytest.skip("sin floater BADLAR VARIABLE calculable en las curvas")
    _check_floater(code)


def test_dual_tamar_cap() -> None:
    code = _floater("TAMAR", "VARIABLE_CAP")
    if not code:
        pytest.skip("sin dual TAMAR (VARIABLE_CAP) calculable en las curvas")
    _check_floater(code)


def test_bono_fijo_ignora_el_override() -> None:
    code = _fijo()
    if not code:
        pytest.skip("sin lecap calculable")
    base = pricing.compute_metrics(code, "tir", 0.30, include_cashflows=False)
    wif = pricing.compute_metrics(code, "tir", 0.30, include_cashflows=False, bench_override=99.0)
    assert wif["bench_custom"] is False and wif["precio"] == pytest.approx(base["precio"], rel=1e-12)
    assert math.isnan(wif["benchmark_pct"])


def test_cupon_desde_serie_bit_a_bit_con_la_mascara_legacy() -> None:
    """Los cortes por searchsorted dan EXACTAMENTE los cupones de la máscara
    `(s.index >= inicio) & (s.index < fin)` de __init__, para todos los
    floaters del universo (y con un índice desordenado cae a la máscara)."""
    import rentafija

    bond_universe.ensure_loaded()
    n = 0
    for code in bond_universe.all_codes():
        obj = bond_universe.get(code)
        if getattr(obj, "step_up", False) or getattr(obj, "tipo_tasa_interes", None) not in ("VARIABLE", "VARIABLE_CAP"):
            continue
        copia = pricing._bond_obj_copy(code)
        serie, col = copia._serie_variable()
        s = rentafija.inputs[serie]
        fechas = copia.fechas_devengo_intereses_habil
        legacy = [s[(s.index >= fechas[i]) & (s.index < fechas[i + 1])][col].mean() for i in range(len(fechas) - 1)]
        copia._cupon_desde_serie(s, col)
        nuevo = copia.intereses
        # reconstruyo los intereses legacy con las mismas fórmulas (VARIABLE)
        if copia.tipo_tasa_interes == "VARIABLE":
            esperado = copia.dias_entre_cupones_anual * np.array([m + copia.cupon_spread for m in legacy]) / 100 * copia.valores_residuales
            assert np.array_equal(np.asarray(nuevo, dtype=float), np.asarray(esperado, dtype=float), equal_nan=True), code
        n += 1
    assert n > 0
    # índice desordenado → camino de la máscara: mismo cupón (la suma en otro
    # orden puede mover el último bit, por eso allclose y no igualdad exacta)
    code = _floater("TAMAR", "VARIABLE")
    if code:
        copia = pricing._bond_obj_copy(code)
        serie, col = copia._serie_variable()
        s = rentafija.inputs[serie]
        copia._cupon_desde_serie(s, col)
        ref = np.array(copia.intereses, dtype=float)
        copia._cupon_desde_serie(s.iloc[::-1], col)
        assert np.allclose(np.array(copia.intereses, dtype=float), ref, rtol=1e-12, atol=0, equal_nan=True)


def test_aplica_nivel_variable_no_muta_inputs() -> None:
    import rentafija
    code = _floater("TAMAR", "VARIABLE") or _floater("TAMAR", "VARIABLE_CAP")
    if not code:
        pytest.skip("sin floater TAMAR")
    s = rentafija.inputs["tamar_proyectado"]
    huella = (len(s.index), float(s["TAMAR"].sum()))
    obj = pricing._bond_obj_copy(code)
    assert obj.aplica_nivel_variable(55.0) is True
    assert (len(s.index), float(s["TAMAR"].sum())) == huella          # la serie global sigue igual
    # un bono fijo devuelve False y no toca nada
    fijo = _fijo()
    if fijo:
        assert pricing._bond_obj_copy(fijo).aplica_nivel_variable(55.0) is False


def test_tr_puntual_respeta_el_override() -> None:
    code = _floater("TAMAR", "VARIABLE") or _floater("BADLAR", "VARIABLE")
    if not code:
        pytest.skip("sin floater VARIABLE")
    base = pricing.tr_puntual(code=code, mode="tir", value=0.30, settle=pricing.settlement_date_str("24hs"))
    wif = pricing.tr_puntual(code=code, mode="tir", value=0.30, settle=pricing.settlement_date_str("24hs"),
                             bench_override=60.0)
    assert base.get("error") is None and wif.get("error") is None
    assert wif["px_ini_pct"] != pytest.approx(base["px_ini_pct"], rel=1e-9)   # la entrada priceó con otros cupones


@pytest.mark.asyncio
async def test_http_yas_con_bench_override() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    code = _floater("TAMAR", "VARIABLE") or _floater("TAMAR", "VARIABLE_CAP")
    if not code:
        pytest.skip("sin floater TAMAR")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.post("/yas/recompute", data={"code": code, "mode": "tir", "value": "0,30",
                                                  "nominales": "1000000", "plazo": "24hs",
                                                  "bench_override": "40,5"})
        assert r.status_code == 200
        assert "aplicable (custom)" in r.text and "40,5000" in r.text
        r = await ac.post("/yas/recompute", data={"code": code, "mode": "tir", "value": "0,30",
                                                  "nominales": "1000000", "plazo": "24hs"})
        assert r.status_code == 200 and "aplicable (avg 5d)" in r.text
        r = await ac.post("/yas/tr", data={"code": code, "mode": "tir", "value": "0,30",
                                           "nominales": "1000000", "plazo": "24hs",
                                           "bench_override": "40,5"})
        assert r.status_code == 200
        page = await ac.get(f"/yas?code={code}")
        assert 'name="bench_override"' in page.text and "TAMAR/BADLAR custom" in page.text
