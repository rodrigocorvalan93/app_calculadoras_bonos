"""MAE Market Data (cauciones / repo / renta fija cross-venue).

  - normalización de cauciones/repo desde un snapshot inyectado.
  - `match` por ticker + leg (best-effort moneda).
  - degradación sin MAE_API_KEY (todo vacío, nada explota).
  - HTTP smoke de /tasas, /tasas/table y el cross-venue en /mercado.
"""
from __future__ import annotations

import time

import pytest

from backend.services import mae


def _inject(rentafija=None, cauciones=None, repo=None) -> None:
    rf = rentafija or []
    by_ticker: dict = {}
    for r in rf:
        by_ticker.setdefault(str(r.get("ticker")).upper(), []).append(r)
    with mae._lock:
        mae._snap.update({"rentafija": rf, "cauciones": cauciones or [],
                          "repo": repo or [], "by_ticker": by_ticker, "ts": time.time()})


def _clear() -> None:
    with mae._lock:
        mae._snap.update({"rentafija": [], "cauciones": [], "repo": [], "by_ticker": {}, "ts": 0.0})


def test_cauciones_and_repo_normalize() -> None:
    _inject(
        cauciones=[{"plazo": "007", "moneda": "$", "ultimatasa": 31.2, "variacion": -0.3, "volumenAcumulado": 4.0e10},
                   {"plazo": "001", "moneda": "$", "ultimatasa": 29.5, "volumenAcumulado": 1.2e11}],
        repo=[{"rueda": "REPO", "plazo": "001", "moneda": "$", "tasaPP": 33.1, "ultimaTasa": 33.0,
               "tasaMinimo": 32.0, "tasaMaximo": 34.0, "volumen": 8.5e8, "cantOperaciones": 3}],
    )
    try:
        ca = mae.cauciones_rows()
        assert [c["plazo"] for c in ca] == ["001", "007"]   # ordenado por plazo
        assert ca[0]["tasa"] == pytest.approx(29.5)
        rp = mae.repo_rows()
        assert rp[0]["tasa_pp"] == pytest.approx(33.1) and rp[0]["tasa_max"] == pytest.approx(34.0)
    finally:
        _clear()


def test_match_by_ticker_and_leg() -> None:
    _inject(rentafija=[
        {"ticker": "AL30", "segmento": "Bilateral PPT", "moneda": "$", "plazo": "002",
         "precioUltimo": 74250.0, "variacion": 0.2, "volumenAcumulado": 3.2e6, "montoAcumulado": 2.4e11},
        {"ticker": "AL30", "segmento": "Garantizado", "moneda": "X", "plazo": "002",
         "precioUltimo": 52.1, "variacion": -0.1, "volumenAcumulado": 9.9e6},
    ])
    try:
        # leg=USD prefiere moneda X (cable) aunque tenga otro volumen
        mx = mae.match("AL30", "USD")
        assert mx and mx["moneda"] == "X" and mx["last"] == pytest.approx(52.1)
        # …C/…D se normalizan al base
        assert mae.match("AL30C", "USD")["ticker"] == "AL30"
        # leg native → sin preferencia de moneda, gana la de mayor volumen (X)
        assert mae.match("AL30", "native")["moneda"] == "X"
        assert mae.volume_for("AL30", "USD") == pytest.approx(9.9e6)
        assert mae.match("NOEXISTE") is None
    finally:
        _clear()


def test_degrades_without_key(monkeypatch) -> None:
    monkeypatch.delenv("MAE_API_KEY", raising=False)
    _clear()
    assert mae.enabled() is False
    assert mae.cauciones_rows() == [] and mae.repo_rows() == []
    assert mae.match("AL30") is None
    st = mae.status()
    assert st["enabled"] is False and st["n_rentafija"] == 0


@pytest.mark.asyncio
async def test_tasas_endpoints() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    _inject(cauciones=[{"plazo": "001", "moneda": "$", "ultimatasa": 29.5, "volumenAcumulado": 1e11}])
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            for url in ("/tasas", "/tasas/table"):
                r = await ac.get(url)
                assert r.status_code == 200, url
                assert r.text
    finally:
        _clear()
