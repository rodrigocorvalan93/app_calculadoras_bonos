"""Break-even Fisher — matemática + endpoint."""
from __future__ import annotations

import pytest

from backend.services.breakeven import compute_fisher


def _row(code, dur, tirea):
    return {"code": code, "duration": dur, "tirea": tirea}


def test_fisher_math() -> None:
    # nominal plana 40% — real 8% → BE = 1.40/1.08 − 1 ≈ 29.63%
    lecap = [_row("S1", 0.5, 0.40), _row("S2", 2.0, 0.40)]
    cer = [_row("TX1", 1.0, 0.08)]
    out = compute_fisher(cer, lecap)
    r = out["rows"][0]
    assert abs(r["be_anual"] - (1.40 / 1.08 - 1.0)) < 1e-12
    assert abs(r["be_tem"] - ((1.0 + r["be_anual"]) ** (30 / 360) - 1.0)) < 1e-12
    assert not r["extrapolado"]
    assert out["resumen"]["n"] == 1


def test_fisher_interpola_y_extrapola() -> None:
    lecap = [_row("S1", 1.0, 0.30), _row("S2", 3.0, 0.50)]   # pendiente +10%/año
    cer = [_row("C1", 2.0, 0.05),    # interpola → nominal 40%
           _row("C2", 6.0, 0.05)]    # fuera de rango → clamp 50% + extrapolado
    out = compute_fisher(cer, lecap)
    by = {r["code"]: r for r in out["rows"]}
    assert abs(by["C1"]["tirea_nom"] - 0.40) < 1e-12 and not by["C1"]["extrapolado"]
    assert abs(by["C2"]["tirea_nom"] - 0.50) < 1e-12 and by["C2"]["extrapolado"]


def test_fisher_filtra_basura() -> None:
    lecap = [_row("S1", 1.0, 0.40)]
    cer = [_row("C1", 1.0, 0.08), _row("C2", None, 0.08), _row("C3", 1.0, None),
           _row("C4", -1.0, 0.08), _row("C5", 1.0, 9.0)]   # NaN/None/dur<=0/absurda
    out = compute_fisher(cer, lecap)
    assert out["n_cer"] == 1 and len(out["rows"]) == 1


@pytest.mark.asyncio
async def test_breakeven_endpoints() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        p = await ac.get("/breakeven")
        t = await ac.get("/breakeven/table")
    assert p.status_code == 200 and "Break-even" in p.text
    assert "md-update from:body" in p.text          # panel live
    assert t.status_code == 200
