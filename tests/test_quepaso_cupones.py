"""Qué pasó: aclaración de cortes de cupón junto al Δ Precio.

Se opera DIRTY → el corte de cupón tira el precio un escalón y el Δ Precio
solo se lee peor de lo que fue. El segmento y cada bono muestran el cobro
promedio de la ventana (% del precio inicial): Δ Precio + cupones ≈ TR.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest
from httpx import ASGITransport, AsyncClient

from backend.services import bond_universe, curves, historico_byma, tr_realizado

_HOY = date.today() - timedelta(days=1)
# La ventana semanal es end−7: la observación previa tiene que caer ANTES del
# inicio de la ventana para que _value_at(start) la encuentre.
_PREV = date.today() - timedelta(days=10)


@pytest.fixture()
def base_lecaps(tmp_path, monkeypatch):
    bond_universe.ensure_loaded()
    lecaps = [c for c in curves.build_curve_codes().get("lecap") or []][:2]
    if len(lecaps) < 2:
        pytest.skip("sin lecaps")
    monkeypatch.setenv("DELTA_HISTORICO_DIR", str(tmp_path))
    monkeypatch.delenv("DELTA_HISTORICO_PATH", raising=False)
    monkeypatch.delenv("DELTA_BASES_DIR", raising=False)
    c1, c2 = lecaps
    pd.DataFrame({
        "fecha_hoy": [_PREV, _PREV, _HOY, _HOY],
        "Código":    [c1, c2, c1, c2],
        "TIREA":     [0.34, 0.35, 0.30, 0.31],
        "TNA":       [0.29, 0.30, 0.26, 0.27],
        "TEM":       [0.0245, 0.0252, 0.0221, 0.0228],
        "Paridad":   [0.95, 0.94, 0.97, 0.96],
        "Last Price": [100.0, 90.0, 99.8, 94.5],
        "Duration":  [0.55, 0.90, 0.47, 0.82],
    }).to_parquet(tmp_path / "Delta - historico_byma_px_tasas.parquet", index=False)
    historico_byma.refresh()
    yield {"c1": c1, "c2": c2}
    historico_byma._cache = None


def test_segmento_expone_cupones_promedio(base_lecaps, monkeypatch) -> None:
    # Cupón sintético: c1 cobró 1,5 por 100 VN en la ventana; c2 nada.
    c1 = base_lecaps["c1"]
    monkeypatch.setattr(tr_realizado, "cupones_entre_cached",
                        lambda code, d1, d2: 1.5 if code == c1 else 0.0)
    w = historico_byma.weekly_segments(days=7)
    assert w["loaded"]
    seg = next(s for s in w["segments"] if s["key"] in ("tasa_fija", "tasa_fija_l")
               and any(r["code"] == c1 for r in s["rows"]))
    r1 = next(r for r in seg["rows"] if r["code"] == c1)
    assert r1["cup_pct"] == pytest.approx(1.5 / 100.0)     # % del precio inicial
    # el promedio del segmento usa el MISMO set que Δ Precio (cero para c2)
    esperado = sum(x for x in ((1.5 / 100.0) if r["code"] == c1 else 0.0
                               for r in seg["rows"] if r["dprice"] is not None)) / \
        sum(1 for r in seg["rows"] if r["dprice"] is not None)
    assert seg["cup_pct"] == pytest.approx(esperado)


def test_lecap_sin_cupon_no_ensucia(base_lecaps) -> None:
    # Ficha real: una lecap viva no corta cupón en la ventana → 0 exacto y
    # el chip no aparece (cup_pct bajo el umbral del template).
    w = historico_byma.weekly_segments(days=7)
    seg = next(s for s in w["segments"]
               if any(r["code"] == base_lecaps["c1"] for r in s["rows"]))
    r1 = next(r for r in seg["rows"] if r["code"] == base_lecaps["c1"])
    assert r1["cup_pct"] == pytest.approx(0.0, abs=1e-12)
    assert (seg["cup_pct"] or 0.0) == pytest.approx(0.0, abs=1e-12)


@pytest.mark.asyncio
async def test_http_semanal_muestra_chip_de_cupones(base_lecaps, monkeypatch) -> None:
    from backend.main import app
    monkeypatch.setattr(tr_realizado, "cupones_entre_cached",
                        lambda code, d1, d2: 1.5)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/historicos/semanal", params={"dias": 7})
    assert r.status_code == 200
    assert "✂ cupones +" in r.text                          # chip del segmento
    assert "✂ +" in r.text                                  # chip por bono