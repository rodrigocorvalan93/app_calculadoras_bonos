"""Históricos: curva en múltiples fechas (scatter Duration vs métrica),
métrica Precio en tasas por curva, y TR realizado entre dos fechas
(ΔP dirty + cupones de la ficha — lecap es cupón cero ⇒ TR == ΔP exacto)."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest
from httpx import ASGITransport, AsyncClient

from backend.services import bond_universe, curves, historico_byma, tr_realizado

_HOY = date.today() - timedelta(days=1)
_PREV = date.today() - timedelta(days=31)


def _lecaps() -> list:
    bond_universe.ensure_loaded()
    td = date.today() + timedelta(days=90)
    out = []
    for c in curves.build_curve_codes().get("lecap") or []:
        o = bond_universe.get(c)
        v = getattr(o, "vencimiento", None)
        vd = v.date() if hasattr(v, "date") else v
        if vd and vd > td:
            out.append(c)
        if len(out) == 2:
            break
    if len(out) < 2:
        pytest.skip("sin 2 lecaps vivas para la fixture")
    return out


@pytest.fixture()
def base_sintetica(tmp_path, monkeypatch):
    """Base histórica de 2 lecaps reales × 2 fechas, servida vía parquet."""
    monkeypatch.setenv("DELTA_HISTORICO_DIR", str(tmp_path))
    monkeypatch.delenv("DELTA_HISTORICO_PATH", raising=False)
    monkeypatch.delenv("DELTA_BASES_DIR", raising=False)
    c1, c2 = _lecaps()
    df = pd.DataFrame({
        "fecha_hoy": [_PREV, _PREV, _HOY, _HOY],
        "Código":    [c1, c2, c1, c2],
        "TIREA":     [0.34, 0.35, 0.30, 0.31],
        "TNA":       [0.29, 0.30, 0.26, 0.27],
        "TEM":       [0.0245, 0.0252, 0.0221, 0.0228],
        "Paridad":   [0.95, 0.94, 0.97, 0.96],
        "Last Price": [95.0, 90.0, 100.0, 94.5],
        "Duration":  [0.55, 0.90, 0.47, 0.82],
    })
    df.to_parquet(tmp_path / "Delta - historico_byma_px_tasas.parquet", index=False)
    historico_byma.refresh()
    tr_realizado._cache.clear() if hasattr(tr_realizado._cache, "clear") else None
    yield {"c1": c1, "c2": c2}
    historico_byma._cache = None            # el próximo test recarga su propio estado


def test_scatter_dos_fechas(base_sintetica) -> None:
    sc = historico_byma.scatter_by_dates(
        "lecap", [_HOY.isoformat(), _PREV.isoformat()], "TEM")
    assert sc["loaded"] and len(sc["series"]) == 2
    hoy = next(s for s in sc["series"] if s["fecha"] == _HOY.isoformat())
    assert {p["code"] for p in hoy["points"]} == {base_sintetica["c1"], base_sintetica["c2"]}
    p1 = next(p for p in hoy["points"] if p["code"] == base_sintetica["c1"])
    assert p1["dur"] == pytest.approx(0.47) and p1["v"] == pytest.approx(0.0221)
    # fecha sin datos cerca (tolerancia 7 días) → la serie ni aparece
    lejos = (_PREV - timedelta(days=20)).isoformat()
    sc2 = historico_byma.scatter_by_dates("lecap", [lejos], "TEM")
    assert sc2["series"] == []


def test_metrica_precio_en_curve_series(base_sintetica) -> None:
    cs = historico_byma.curve_series("lecap", "Last Price")
    assert cs["loaded"] and cs["metric"] == "Last Price"
    assert cs["scale"] == 1.0                              # el precio no se multiplica ×100
    ln = next(l for l in cs["lines"] if l["code"] == base_sintetica["c1"])
    assert ln["last"] == pytest.approx(100.0)
    assert ln["delta"] == pytest.approx((100.0 / 95.0 - 1) * 100)   # Δ en %
    assert ln["delta_unit"] == "%"


def test_tr_realizado_lecap_es_delta_precio_exacto(base_sintetica) -> None:
    t = tr_realizado.tabla("lecap", _PREV.isoformat(), _HOY.isoformat())
    assert t["loaded"] and len(t["rows"]) == 2
    r1 = next(r for r in t["rows"] if r["code"] == base_sintetica["c1"])
    # lecap viva = cupón cero: sin cobros en la ventana ⇒ TR == P2/P1 − 1 EXACTO
    assert r1["cupones"] == pytest.approx(0.0, abs=1e-12)
    assert r1["tr"] == pytest.approx(100.0 / 95.0 - 1.0, abs=1e-12)
    assert r1["px_var"] == pytest.approx(r1["tr"], abs=1e-12)
    assert r1["dy_bps"] == pytest.approx(-400.0, abs=1e-6)          # 34% → 30%
    assert t["summary"]["n"] == 2


@pytest.mark.asyncio
async def test_http_tab_curva_fechas_y_metrica_precio(base_sintetica) -> None:
    from backend.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/historicos/curva-fechas", params={
            "curve": "lecap", "metric": "TEM",
            "f1": _HOY.isoformat(), "f2": _PREV.isoformat(),
            "trd1": _PREV.isoformat(), "trd2": _HOY.isoformat(),
        })
        assert r.status_code == 200
        assert "TR realizado" in r.text and base_sintetica["c1"] in r.text
        assert "<svg" in r.text                                     # scatter renderizado
        r2 = await ac.get("/historicos/curva", params={"curve": "lecap", "metric": "Last Price"})
        assert r2.status_code == 200 and "Precio" in r2.text
        # la página muestra el tab nuevo
        page = await ac.get("/historicos")
        assert "Curva por fecha + TR" in page.text


@pytest.mark.asyncio
async def test_csv_export_que_paso(base_sintetica) -> None:
    """Export CSV es-AR del resumen: ';' separador, coma decimal, BOM y
    attachment — sale del mismo cache de weekly_segments que la tabla."""
    from backend.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/historicos/semanal.csv", params={"dias": 30})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers.get("content-disposition", "")
    assert r.text.startswith("﻿")                             # BOM para Excel
    assert "Segmento;Bono;Duration;Δ Precio %" in r.text
    # la lecap de la fixture está, con Δ precio es-AR (100/95−1 = 5,26%)
    assert base_sintetica["c1"] in r.text and "5,26" in r.text
    # el botón de descarga está en el partial del resumen
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        h = await ac.get("/historicos/semanal", params={"dias": 30})
    assert "semanal.csv" in h.text

def test_scatter_chart_linea_es_curva_nss_no_serrucho() -> None:
    """La línea del scatter es la NSS ajustada a la nube (suave, ~70 muestras,
    robusta a los cortos dispersos), NO la polilínea punto a punto (serrucho).
    Con <4 puntos no hay fit → cae a la polilínea punteada (fit=False)."""
    from backend.routes.historico import _scatter_chart

    # Nube estilo CER real: decreciente con ruido fuerte en los cortos.
    puntos = [{"code": f"B{i}", "dur": d, "v": v} for i, (d, v) in enumerate([
        (0.10, 0.29), (0.15, 0.02), (0.20, 0.31), (0.30, 0.05),
        (0.45, 0.27), (0.60, 0.24), (0.90, 0.20), (1.30, 0.16),
        (1.80, 0.13), (2.50, 0.11), (4.00, 0.10), (7.00, 0.095),
    ])]
    sc = {"loaded": True, "metric": "TIREA", "curve_label": "CER",
          "series": [{"fecha": "2026-08-13", "points": puntos}]}
    ch = _scatter_chart(sc)
    s = ch["series"][0]
    assert s["fit"] is True
    assert len(s["points"]) == len(puntos)              # los puntos no se tocan
    assert s["path"].count(" L ") + 1 >= 60             # muestreo suave (n=70)
    # la curva ajustada no se sale del área del gráfico (clamp al rango Y)
    ys = [float(seg.split(",")[1]) for seg in s["path"][2:].split(" L ")]
    assert min(ys) >= ch["y0"] - 0.6 and max(ys) <= ch["y1"] + 0.6

    # <4 puntos: sin fit → polilínea de los puntos tal cual, punteada
    sc2 = {"loaded": True, "metric": "TIREA", "curve_label": "CER",
           "series": [{"fecha": "2026-08-13", "points": puntos[:3]}]}
    s2 = _scatter_chart(sc2)["series"][0]
    assert s2["fit"] is False and s2["path"].count(" L ") == 2
