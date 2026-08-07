"""Histórico de forwards par-a-par — fórmula, serie, stats/percentil y endpoint."""
from __future__ import annotations

import pytest

from backend.services import forwards_hist as fh


def test_fwd_rate_formula() -> None:
    # forward 0,5→1,0 años con 30% y 35%: f = (d1/d2)^(1/0,5) − 1
    y1, t1, y2, t2 = 0.30, 0.5, 0.35, 1.0
    d1, d2 = (1 + y1) ** -t1, (1 + y2) ** -t2
    esperado = (d1 / d2) ** (1.0 / (t2 - t1)) - 1.0
    assert fh.fwd_rate(y1, t1, y2, t2) == pytest.approx(esperado)
    assert fh.fwd_rate(y1, 1.0, y2, 0.5) is None       # t2 ≤ t1
    assert fh.fwd_rate(None, t1, y2, t2) is None
    assert fh.fwd_rate(-1.5, t1, y2, t2) is None       # (1+y) ≤ 0


def _base_sintetica(monkeypatch, n=100, ver="v-test"):
    """historico_byma falso: A (corto) y B (largo) con TIR/Duration por rueda."""
    from backend.services import historico_byma as hb

    dates = [f"2026-{4 + i // 30:02d}-{(i % 30) + 1:02d}" for i in range(n)]
    a = {"dates": dates, "vals": {"TIREA": [0.30 + 0.0005 * i for i in range(n)],
                                  "Duration": [0.5] * n}}
    b = {"dates": dates, "vals": {"TIREA": [0.35 + 0.0005 * i for i in range(n)],
                                  "Duration": [1.0] * n}}
    fake = {"loaded": True, "by_code": {"AAA": a, "BBB": b}, "last_update": ver}
    monkeypatch.setattr(hb, "ensure_loaded", lambda: fake)
    monkeypatch.setattr(hb, "meta", lambda: {"last_update": ver})
    monkeypatch.setattr(hb, "available", lambda: True)
    return dates


def test_serie_y_stats_con_ventana(monkeypatch) -> None:
    _base_sintetica(monkeypatch, n=100, ver="v1")
    s = fh.serie("AAA", "BBB")
    assert len(s["dates"]) == 100 and len(s["fwds"]) == 100
    # la serie es creciente (TIRs suben en paralelo) → percentil alto para el último
    st = fh.stats("AAA", "BBB", ventana=60, fwd_hoy=s["fwds"][-1])
    assert st["n"] == 60                                # ventana recorta
    assert st["media"] == pytest.approx(sum(s["fwds"][-60:]) / 60)
    assert st["desvio"] is not None and st["desvio"] > 0
    assert st["percentil"] is not None and st["percentil"] > 0.95
    assert st["z"] == pytest.approx((s["fwds"][-1] - st["media"]) / st["desvio"])
    assert st["aviso_n"] is False
    # toda la historia
    st_all = fh.stats("AAA", "BBB", ventana=0, fwd_hoy=None)
    assert st_all["n"] == 100 and st_all["percentil"] is None
    # un fwd_hoy en la mediana → percentil ~50
    mid = sorted(s["fwds"][-60:])[30]
    st_mid = fh.stats("AAA", "BBB", ventana=60, fwd_hoy=mid)
    assert 0.35 < st_mid["percentil"] < 0.65


def test_stats_muestra_chica_avisa(monkeypatch) -> None:
    _base_sintetica(monkeypatch, n=8, ver="v2")
    st = fh.stats("AAA", "BBB", ventana=60, fwd_hoy=0.4)
    assert st["n"] == 8 and st["aviso_n"] is True


def test_par_sin_datos(monkeypatch) -> None:
    _base_sintetica(monkeypatch, n=10, ver="v3")
    assert fh.serie("AAA", "NOEXISTE")["fwds"] == []
    st = fh.stats("AAA", "NOEXISTE", ventana=60)
    assert st["n"] == 0 and st["media"] is None


def test_chart_geometria(monkeypatch) -> None:
    _base_sintetica(monkeypatch, n=50, ver="v4")
    s = fh.serie("AAA", "BBB")
    st = fh.stats("AAA", "BBB", ventana=0, fwd_hoy=s["fwds"][-1])
    ch = fh.chart(st)
    assert ch is not None
    assert len(ch["poly"].split()) == 50                # un punto por rueda
    assert ch["media_y"] is not None and ch["banda"] is not None
    assert ch["hoy"] is not None and len(ch["xlabels"]) == 5
    assert all(ch["y0"] <= t["y"] <= ch["y1"] for t in ch["yticks"])


@pytest.mark.asyncio
async def test_forwards_hist_endpoint(monkeypatch) -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    _base_sintetica(monkeypatch, n=40, ver="v5")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        # par sintético: sin fwd de hoy (no está en la curva viva) pero con serie
        r = await ac.get("/forwards/hist", params={
            "curve": "cer", "fw-corto": "AAA", "fw-largo": "BBB", "fw-ventana": "30"})
        vacio = await ac.get("/forwards/hist", params={"curve": "cer"})
        page = await ac.get("/forwards", params={"only_quoting": "false"})
    assert r.status_code == 200
    assert "Media (30 ruedas)" in r.text and "Percentil hoy" in r.text
    assert "fc-band" in r.text and "fc-avg" in r.text     # banda ±1σ + media
    assert "Ojo con el percentil" in r.text               # la advertencia SIEMPRE visible
    assert vacio.status_code == 200                       # sin par → estado vacío, no 500
    assert page.status_code == 200
    if "Histórico del forward" in page.text:              # con ≥2 candidatos
        assert 'name="fw-corto"' in page.text and 'name="fw-ventana"' in page.text


def test_serie_saltea_gaps_infimos(monkeypatch) -> None:
    """t2−t1 → 0 anualiza a miles de %: esas ruedas quedan FUERA de la serie
    para no envenenar media/desvío/percentil con un solo outlier."""
    from backend.services import historico_byma as hb

    dates = [f"2026-05-{i+1:02d}" for i in range(10)]
    a = {"dates": dates, "vals": {"TIREA": [0.30] * 10, "Duration": [0.50] * 10}}
    # el largo cruza al corto en las últimas 5 ruedas (gap < _MIN_GAP)
    b = {"dates": dates, "vals": {"TIREA": [0.35] * 10,
                                  "Duration": [1.0] * 5 + [0.51] * 5}}
    fake = {"loaded": True, "by_code": {"C": a, "L": b}, "last_update": "v-gap"}
    monkeypatch.setattr(hb, "ensure_loaded", lambda: fake)
    monkeypatch.setattr(hb, "meta", lambda: {"last_update": "v-gap"})
    s = fh.serie("C", "L")
    assert len(s["fwds"]) == 5                      # sólo las ruedas con gap sano


@pytest.mark.asyncio
async def test_matriz_celdas_clickeables_para_hist() -> None:
    """Las celdas con forward llevan data-fwc/data-fwl (fila=corto, col=largo):
    app.js las usa para cargar ese par en el panel de histórico."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.services import bond_universe, curves, marketdata_store as mds
    from backend.services import symbols as syms

    bond_universe.ensure_loaded()
    for i, c in enumerate((curves.build_curve_codes().get("cer") or [])[:5]):
        mds.get_store().update_from_md(syms.md_symbol(c, "24hs"),
                                       {"LA": {"price": 1150.0 + i * 40}})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/forwards/table", params={"curve": "cer"})
    assert r.status_code == 200
    if 'data-fwc="' in r.text:                      # con ≥2 bonos válidos
        assert 'data-fwl="' in r.text
