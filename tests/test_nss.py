"""Nelson-Siegel-Svensson — ajuste, estimación TIR/TEM/TNAs y endpoints de Gráficos."""
from __future__ import annotations

import pytest

from backend.services import nss


def test_nss_fit_and_estimate() -> None:
    xs = [0.3, 0.6, 1.0, 1.5, 2.0, 2.8, 3.5, 4.2]
    ys = [40, 38, 36, 34, 33, 32, 31.5, 31]              # TIREA en %
    e = nss.estimate(1.5, xs, ys)
    assert e is not None
    assert 0.30 < e["tirea"] < 0.40                      # ~34%
    assert e["tnas"]["365"] == pytest.approx(e["tirea"])  # TNA cap. anual = TIREA
    assert e["tem"] == pytest.approx((1 + e["tirea"]) ** (30 / 360) - 1)
    assert e["tna_plazo"] is not None
    assert nss.sample(xs, ys)                             # curva muestreada
    assert nss.fit([1.0, 2.0], [10.0, 11.0]) is None      # <4 pts → None


def test_nss_estimate_clamps_out_of_range() -> None:
    xs = [0.5, 1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [40, 38, 35, 33, 32, 31]
    e = nss.estimate(20.0, xs, ys)                        # fuera del rango del fit
    assert e is not None and e["clamped"]
    assert e["duration_used"] == pytest.approx(5.0)


@pytest.mark.asyncio
async def test_graficos_estimate_endpoint() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.services import bond_universe, curves, marketdata_store as mds, symbols as syms

    bond_universe.ensure_loaded()
    codes = curves.build_curve_codes().get("cer", [])
    if len(codes) < 4:
        pytest.skip("curva CER insuficiente")
    store = mds.get_store()
    for i, c in enumerate(codes):
        store.update_from_md(syms.md_symbol(c, "24hs"),
                             {"LA": {"price": 95.0 + i * 0.7}, "CL": {"price": 94.9 + i * 0.7},
                              "EV": 2e7, "NV": 2e5})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        svg = await ac.get("/graficos/svg?curve=cer&only_quoting=false")
        est = await ac.get("/graficos/estimate?curve=cer&only_quoting=false&duration=1,5")
    assert svg.status_code == 200
    assert est.status_code == 200
    assert "TIR (TIREA)" in est.text and "TNA del plazo" in est.text
