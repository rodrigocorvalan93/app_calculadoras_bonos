"""Phase 1 smoke tests for the YAS calc.

Goal: 3 representative bonds (LECAP, dual TAMAR, hard-dollar) run end to
end through `backend.services.pricing.compute_metrics` and return sane
numbers. We also exercise the `/yas/recompute` endpoint via httpx
AsyncClient.

The dual-TAMAR sanity check focuses on the spec from the task:
"TXMJ9v a precio 87.30 dé TNA≈31% y Margen TNA≈8%". We assert that
TNA and Margen TNA are finite and within a wide window (the legacy app
gives the reference numbers; this lets us track regressions while
allowing minor BCRA-data-driven drift).
"""
from __future__ import annotations

import math
import os
from typing import Any, Dict

import pytest

# These imports trigger backend/services/bond_universe → especies → indices.
# That can take several seconds on a cold container as indices reads the
# BCRA backup JSON.

from backend.services import bond_universe, pricing
from backend.routes.yas import _parse_ar_number


def _isfin(x: Any) -> bool:
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


@pytest.fixture(scope="session", autouse=True)
def _load_universe() -> None:
    bond_universe.ensure_loaded()


# ── Pure helper tests ────────────────────────────────────────────────────

def test_parse_ar_number_accepts_coma_and_period() -> None:
    assert _parse_ar_number("87,30") == 87.30
    assert _parse_ar_number("87.30") == 87.30
    assert _parse_ar_number("1.234.567,89") == 1_234_567.89
    assert _parse_ar_number("") is None
    assert _parse_ar_number("abc") is None


# ── Pricing smoke tests ──────────────────────────────────────────────────

def _expect_calc(metrics: Dict[str, Any]) -> None:
    assert metrics.get("error") is None, metrics.get("error")
    assert _isfin(metrics["tirea"])
    assert _isfin(metrics["tna"])
    assert _isfin(metrics["duration"])
    assert _isfin(metrics["paridad"])


def test_dual_tamar_txmj9v_price_87_30() -> None:
    """TXMJ9v @ 87,30 → TNA cap32 ≈ 31%, Margen TNA ≈ 8%.

    Reproduce el target del prompt de Fase 1. La TNA usa la convención
    cap 32/365 (no la `obj.tna` cruda que daba ~51%). El margen relativo
    al TAMAR aplicable (avg 5d, ~22,8 a esta fecha) ronda 8 p.p.
    """
    if "TXMJ9v" not in bond_universe.all_codes():
        pytest.skip("TXMJ9v not present in especies.py")

    m = pricing.compute_metrics(code="TXMJ9v", mode="precio", value=87.30)
    _expect_calc(m)

    assert m["tipo_tasa_interes"] == "VARIABLE_CAP"
    assert m["index"] == "TAMAR"

    assert _isfin(m["margen_tna"]), "Margen TNA debería computarse para VARIABLE_CAP"
    assert _isfin(m["benchmark_pct"]), "Benchmark TAMAR debería estar disponible"

    # Target del prompt: TNA ≈ 31% y Margen TNA ≈ 8%. Las ventanas
    # son anchas (±3 p.p.) para tolerar drift en TAMAR avg-5d entre
    # corridas; el valor del benchmark cambia conforme BCRA publica.
    assert 0.27 <= m["tna"] <= 0.34, f"TNA fuera de target ~31%: {m['tna']!r}"
    assert 0.05 <= m["margen_tna"] <= 0.11, f"Margen TNA fuera de target ~8%: {m['margen_tna']!r}"

    # La TNA cruda de rentafija (cnv 'plazo remanente') seguía dando
    # ~51% — la dejamos expuesta como `tna_raw` para diagnóstico.
    assert _isfin(m["tna_raw"])
    assert m["tna_raw"] > 0.40, "tna_raw debería seguir reflejando el bug histórico (~51%)"


def test_txmj9v_modes_are_symmetric() -> None:
    """Los 4 modos (precio/tir/tna/margen) deben converger al mismo TIREA."""
    if "TXMJ9v" not in bond_universe.all_codes():
        pytest.skip("TXMJ9v not present in especies.py")

    base = pricing.compute_metrics(code="TXMJ9v", mode="precio", value=87.30)
    _expect_calc(base)

    tirea = base["tirea"]
    via_tir = pricing.compute_metrics(code="TXMJ9v", mode="tir", value=tirea)
    via_tna = pricing.compute_metrics(code="TXMJ9v", mode="tna", value=base["tna"])
    via_marg = pricing.compute_metrics(code="TXMJ9v", mode="margen", value=base["margen_tna"])
    for label, m in (("tir", via_tir), ("tna", via_tna), ("margen", via_marg)):
        _expect_calc(m)
        assert abs(m["tirea"] - tirea) < 1e-3, f"mode={label} TIREA drift: {m['tirea']!r} vs {tirea!r}"


def test_lecap_runs() -> None:
    # Pick the first LECAP-ish code present (S, T, etc.). LECAPs are the
    # most common bullet ARS bonds in the universe.
    candidates = [c for c in bond_universe.all_codes() if c.startswith(("S", "T"))]
    if not candidates:
        pytest.skip("No LECAP-style bonds in especies.py")

    chosen = None
    for c in candidates:
        meta = pricing.bond_meta(c)
        if meta.get("tipo_tasa_interes") != "FIJA" or meta.get("moneda") != "ARS":
            continue
        # Saltear letras al borde del vencimiento: con settlement t+1 ≥ vto el
        # motor legacy no puede calcular (el día que vence una S*, este test se
        # rompía solo — bomba de tiempo). Exigimos ≥5 días de vida.
        venc = getattr(bond_universe.get(c), "vencimiento", None)
        from datetime import date, timedelta
        if venc is None or venc < date.today() + timedelta(days=5):
            continue
        chosen = c
        break
    if chosen is None:
        pytest.skip("No fixed-rate ARS bullet found")

    m = pricing.compute_metrics(code=chosen, mode="precio", value=80.0)
    _expect_calc(m)


def test_hard_dollar_runs() -> None:
    # Find any USD bullet (GD30 / AL30-style sovereigns are the typical sample).
    chosen = None
    for c in bond_universe.all_codes():
        meta = pricing.bond_meta(c)
        if meta.get("moneda") == "USD" and meta.get("tipo_tasa_interes") == "FIJA":
            chosen = c
            break
    if chosen is None:
        pytest.skip("No USD fixed-rate bond in especies.py")

    m = pricing.compute_metrics(code=chosen, mode="precio", value=70.0)
    _expect_calc(m)
    assert m["tna_convention_label"] == "180/360", m["tna_convention_label"]


# ── TNA convention table ─────────────────────────────────────────────────


def test_tna_convention_label_per_type() -> None:
    """Exercises the per-tipo convention table from `tna_convention`."""
    if "TXMJ9v" in bond_universe.all_codes():
        m = pricing.compute_metrics("TXMJ9v", "precio", 87.30)
        assert m["tna_convention_label"] == "32/365 cap"


def test_tna_convention_override() -> None:
    """When freq/base are passed, they win over auto-detection."""
    if "TXMJ9v" not in bond_universe.all_codes():
        pytest.skip("TXMJ9v not present")
    m = pricing.compute_metrics("TXMJ9v", "precio", 87.30, freq_override=180, base_override=365)
    assert "180/365 custom" in m["tna_convention_label"]


def test_cer_bond_shows_cer_aplicable() -> None:
    """CER / CER PROYECTADO bonds must report the latest CER value."""
    cer_code = None
    for c in bond_universe.all_codes():
        meta = pricing.bond_meta(c)
        if "CER" in (meta.get("ajuste_sobre_capital") or "").upper():
            cer_code = c
            break
    if cer_code is None:
        pytest.skip("No CER bond in especies.py")
    m = pricing.compute_metrics(cer_code, "precio", 95.0)
    idx = m["index_applied"]
    assert idx["kind"] == "CER"
    assert _isfin(idx["value"]), f"CER value should be loaded from rentafija.inputs: {idx}"
    assert m["tna_convention_label"] == "180/365"


def test_variable_uses_90_over_365() -> None:
    """Per the latest spec: tasa variable pura = 90/365 (no longer days/365)."""
    target = None
    for c in bond_universe.all_codes():
        meta = pricing.bond_meta(c)
        if meta.get("tipo_tasa_interes") == "VARIABLE":
            target = c
            break
    if target is None:
        pytest.skip("No VARIABLE-rate bond in especies.py")
    m = pricing.compute_metrics(target, "precio", 95.0)
    assert m["tna_convention_label"] == "90/365", m["tna_convention_label"]


# ── HTTP layer smoke tests ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_yas_page_renders() -> None:
    from httpx import ASGITransport, AsyncClient
    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/yas")
    assert r.status_code == 200
    assert "Análisis de Yields" in r.text


@pytest.mark.asyncio
async def test_curves_page_renders() -> None:
    from httpx import ASGITransport, AsyncClient
    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/curves")
    assert r.status_code == 200
    assert "Curvas" in r.text


@pytest.mark.asyncio
async def test_curve_table_partial() -> None:
    from httpx import ASGITransport, AsyncClient
    from backend.main import app
    from backend.services import curves

    target_key = None
    for c in curves.list_curves():
        if curves.build_curve_codes().get(c.key):
            target_key = c.key
            break
    if target_key is None:
        pytest.skip("No non-empty curve available")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get(f"/curves/table?curve={target_key}")
    assert r.status_code == 200
    # Should link back to YAS for each row.
    assert "/yas?code=" in r.text


def test_curves_partition_is_nonempty() -> None:
    from backend.services import curves

    table = curves.build_curve_codes()
    # At least LECAP and globales should populate from the live universe.
    assert any(table.get(k) for k in ("lecap", "cer", "globales"))


@pytest.mark.asyncio
async def test_yas_recompute_partial() -> None:
    from httpx import ASGITransport, AsyncClient
    from backend.main import app

    if "TXMJ9v" not in bond_universe.all_codes():
        pytest.skip("TXMJ9v not present in especies.py")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post(
            "/yas/recompute",
            data={
                "code": "TXMJ9v",
                "mode": "precio",
                "value": "87,30",
                "nominales": "1000000",
                "plazo": "24hs",
            },
        )
    assert r.status_code == 200
    # The metrics partial includes a TIREA cell.
    assert "TIREA" in r.text
    assert "Margen TNA" in r.text  # VARIABLE_CAP path must render the margen block
