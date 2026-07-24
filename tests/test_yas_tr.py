"""Total return puntual de la ficha YAS (pricing.tr_puntual + POST /yas/tr)."""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pytest

from backend.services import bond_universe, pricing


def _un_bono_priceable():
    """Primer bono del universo que produce TIR finita a algún precio."""
    bond_universe.ensure_loaded()
    for code in bond_universe.all_codes():
        for px in (100.0, 87.30, 1000.0, 5000.0):
            m = pricing.compute_metrics(code, mode="precio", value=px, include_cashflows=False)
            if not m.get("error") and np.isfinite(m.get("tirea", float("nan"))):
                return code, px, m
    pytest.skip("ningún bono pricea en este entorno")


def test_tr_puntual_flat_y_desglose() -> None:
    """Salida flat (misma TIR) a +90 días: TR finito y el desglose cierra —
    interés + capital cobrados = total cobrado; montos $ escalan con el VN."""
    code, px, _ = _un_bono_priceable()
    tr = pricing.tr_puntual(code, mode="precio", value=px, nominales=1_000_000.0)
    assert tr["error"] is None, tr["error"]
    assert tr["salida_flat"] is True
    assert tr["tir_salida"] == pytest.approx(tr["tir_entrada"])
    assert np.isfinite(tr["tr"])
    assert tr["dias"] > 0
    # desglose: interés + capital = total cobrado (con ajuste aplicado)
    assert tr["interes_pct"] + tr["capital_pct"] == pytest.approx(tr["cobrado_pct"], abs=1e-9)
    assert len(tr["flujos"]) == tr["n_flujos"]
    # TR = (P&L capital + cobrado) / px inicial
    esperado = (tr["pnl_capital_pct"] + tr["cobrado_pct"]) / tr["px_ini_pct"]
    assert tr["tr"] == pytest.approx(esperado, rel=1e-9)
    # montos $ = pct/100 × nominales
    assert tr["pnl_total_m"] == pytest.approx(
        (tr["pnl_capital_pct"] + tr["cobrado_pct"]) / 100.0 * 1_000_000.0, rel=1e-9)
    # doble de nominales → doble de $
    tr2 = pricing.tr_puntual(code, mode="precio", value=px, nominales=2_000_000.0)
    assert tr2["pnl_total_m"] == pytest.approx(tr["pnl_total_m"] * 2, rel=1e-9)


def test_tr_puntual_salida_explicita_mueve_el_px_final() -> None:
    """Una TIR de salida más alta que la de entrada baja el px final vs flat
    (mientras la salida no sea a vencimiento, donde el px final no juega)."""
    code, px, m = _un_bono_priceable()
    flat = pricing.tr_puntual(code, mode="precio", value=px)
    if flat["error"] or flat["a_vencimiento"]:
        pytest.skip("bono vence antes de +90 días en este entorno")
    subida = pricing.tr_puntual(code, mode="precio", value=px,
                                tir_salida=flat["tir_entrada"] + 0.10)
    assert subida["error"] is None
    assert subida["px_fin_pct"] < flat["px_fin_pct"]
    assert subida["tr"] < flat["tr"]


def test_tr_puntual_fechas_invalidas() -> None:
    code, px, m = _un_bono_priceable()
    # fecha no parseable → error claro
    r = pricing.tr_puntual(code, mode="precio", value=px, fecha_salida="32/13/2026")
    assert r["error"] and "inválida" in r["error"]
    # fecha ≤ settle → error claro
    ayer = (m["fecha_settlement"] - timedelta(days=1)).strftime("%d/%m/%Y")
    r = pricing.tr_puntual(code, mode="precio", value=px, fecha_salida=ayer)
    assert r["error"] and "posterior" in r["error"]


def test_tr_puntual_a_vencimiento() -> None:
    """Salida ≥ vencimiento: se cobran todos los flujos, px final ≈ 0 y la
    tasa de salida no cambia el resultado."""
    code, px, _ = _un_bono_priceable()
    lejos = (datetime.now() + timedelta(days=365 * 80)).strftime("%d/%m/%Y")
    a = pricing.tr_puntual(code, mode="precio", value=px, fecha_salida=lejos)
    b = pricing.tr_puntual(code, mode="precio", value=px, fecha_salida=lejos,
                           tir_salida=1.23)
    assert a["error"] is None and b["error"] is None
    assert a["a_vencimiento"] is True
    assert a["px_fin_pct"] == pytest.approx(0.0, abs=1e-9)
    assert a["tr"] == pytest.approx(b["tr"], rel=1e-12)


@pytest.mark.asyncio
async def test_yas_tr_http() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    code, px, _ = _un_bono_priceable()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # defaults (tasa/fecha vacías → flat + 90 días)
        r = await ac.post("/yas/tr", data={"code": code, "mode": "precio",
                                           "value": str(px).replace(".", ","),
                                           "nominales": "1.000.000", "plazo": "24hs"})
        assert r.status_code == 200
        assert "TR período" in r.text and "Interés cobrado" in r.text
        # valor no numérico → error legible, sin 500
        r = await ac.post("/yas/tr", data={"code": code, "mode": "precio", "value": "abc"})
        assert r.status_code == 200
        assert "Ingresá un valor" in r.text
        # la página YAS incluye el cuadro
        r = await ac.get("/yas")
        assert r.status_code == 200
        assert "Total return puntual" in r.text and "/yas/tr" in r.text
