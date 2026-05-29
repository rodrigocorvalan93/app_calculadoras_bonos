"""Tests for the Phase 2 warmup daemon.

Covers the two cold-path mitigations:
  - `prime_calc_engine` forces the lazy calc-engine load and leaves the
    engine usable (exercises the real TIR math).
  - `warm_curves_once` pre-fills the metrics cache for codes that have a
    live price, and is a safe no-op for codes with no quote.
  - `/healthz` exposes the daemon stats (HTTP endpoint smoke).
"""
from __future__ import annotations

import numpy as np
import pytest

from backend.services import bond_universe, curves
from backend.services import marketdata_store as mds_
from backend.services import pricing
from backend.services import symbols as syms_
from backend.services import warmup


def _first_curve_code() -> tuple[str, str]:
    """First code of the first non-empty curve — same pick the curve-table
    test uses, so we know it prices cleanly at 87.30."""
    bond_universe.ensure_loaded()
    table = curves.build_curve_codes()
    for c in curves.list_curves():
        codes = table.get(c.key) or []
        if codes:
            return c.key, codes[0]
    raise AssertionError("no non-empty curve found")


def test_prime_calc_engine_runs_and_engine_usable() -> None:
    elapsed = warmup.prime_calc_engine()
    assert isinstance(elapsed, float)
    assert elapsed >= 0.0
    # Engine is now resident: a fresh calc returns a finite TIREA.
    _, code = _first_curve_code()
    m = pricing.compute_metrics(code, mode="precio", value=87.30, include_cashflows=False)
    assert m is not None
    assert np.isfinite(m.get("tirea"))


def test_warm_code_no_price_returns_false() -> None:
    """A code with no snapshot in the store warms nothing (no exception)."""
    assert warmup._warm_code("NONEXISTENT_CODE_XYZ", "24hs") is False


@pytest.mark.asyncio
async def test_warm_curves_once_fills_metrics_cache() -> None:
    curve_key, code = _first_curve_code()
    price = 87.30
    symbol = syms_.md_symbol(code, "24hs")
    mds_.get_store().update_from_md(symbol, {"LA": {"price": price, "size": 1000}})

    res = await warmup.warm_curves_once("24hs")
    assert res["warmed"] >= 1
    assert res["codes"] >= 1

    # The exact key the curves route would look up is now cached: a
    # get_or_compute with a sentinel factory must NOT call the factory.
    sentinel = object()
    key = (code, round(price, 2), "")
    cached = pricing._curve_metrics_cache.get_or_compute(key, lambda: sentinel)
    assert cached is not sentinel


@pytest.mark.asyncio
async def test_healthz_exposes_warmup() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert "warmup" in body
    assert "primed" in body["warmup"]
