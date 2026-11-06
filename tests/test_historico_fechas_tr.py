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
    assert p1["px"] == pytest.approx(100.0)                      # precio a esa fecha (Δ precio del hover)
    # memo por (curva, fechas, métrica, tipo, versión de la base): misma foto de memoria
    assert historico_byma.scatter_by_dates("lecap", [_HOY.isoformat(), _PREV.isoformat()], "TEM") is sc
    historico_byma.refresh()
    assert historico_byma.scatter_by_dates("lecap", [_HOY.isoformat(), _PREV.isoformat()], "TEM") is not sc
    # fecha sin datos cerca (tolerancia 7 días) → la serie ni aparece
    lejos = (_PREV - timedelta(days=20)).isoformat()
    sc2 = historico_byma.scatter_by_dates("lecap", [lejos], "TEM")
    assert sc2["series"] == []


def test_scatter_chart_excluir_y_tramo() -> None:
    """Excluir bonos (outliers) y acotar el tramo de duration sacan puntos ANTES
    del fit, como en Gráficos; la leyenda (`codes`) queda ordenada por duration
    y `excluded` lista sólo los que estaban en la foto."""
    from backend.routes.historico import _parse_exclude, _scatter_chart

    assert _parse_exclude(" tx26, T30J6;tzxm7  tx26 ") == ["TX26", "T30J6", "TZXM7"]
    puntos = [{"code": c, "dur": d, "v": v, "px": 100.0 + i}
              for i, (c, d, v) in enumerate([("A1", 0.2, 0.30), ("B2", 0.5, 0.27), ("C3", 0.9, 0.24),
                                             ("D4", 1.6, 0.20), ("E5", 2.4, 0.17), ("F6", 3.5, 0.15),
                                             ("G7", 5.0, 0.13)])]
    sc = {"loaded": True, "metric": "TIREA", "curve_label": "CER",
          "series": [{"fecha": "2026-08-13", "points": puntos},
                     {"fecha": "2026-09-13", "points": [dict(p, v=p["v"] - 0.01) for p in puntos[:-1]]}]}
    ch = _scatter_chart(sc)
    assert [c["code"] for c in ch["codes"]] == ["A1", "B2", "C3", "D4", "E5", "F6", "G7"]
    assert ch["ultima"] == "2026-09-13" and [s["ultima"] for s in ch["series"]] == [False, True]
    assert ch["series"][0]["grupos"][0]["points"][0]["px"] == 100.0
    ch2 = _scatter_chart(sc, dmin=0.4, dmax=3.0, exclude=["c3", "ZZ9"])
    vis = {p["code"] for s in ch2["series"] for g in s["grupos"] for p in g["points"]}
    assert vis == {"B2", "D4", "E5"}                           # 0,4 ≤ dur ≤ 3, sin C3
    assert ch2["excluded"] == ["c3"] and ch2["dmin"] == 0.4 and ch2["dmax"] == 3.0
    assert [c["code"] for c in ch2["codes"]] == ["B2", "D4", "E5"]
    # todo afuera → sin puntos pero con el motivo (excluidos / tramo) para el template
    ch3 = _scatter_chart(sc, dmin=10.0)
    assert ch3["n"] == 0 and ch3["dmin"] == 10.0 and ch3["codes"] == []


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
        # interacción client-side: puntos con data-* (hover Δ tasa / Δ precio),
        # etiquetas de la última fecha, leyenda con chips y capa de hover
        c1 = base_sintetica["c1"]
        assert f'class="hc-pt" data-code="{c1}" data-fecha="{_HOY.isoformat()}"' in r.text
        assert 'data-px="100.0"' in r.text and 'class="hc-hover"' in r.text
        assert f'class="hc-lbl" data-code="{c1}"' in r.text and r.text.count("hc-lbl") == 2
        assert f'class="cmp-chip hc-chip" data-code="{c1}"' in r.text and "hc-labels-toggle" in r.text
        # excluir un bono del fit + tramo de duration (es-AR): el punto no viaja
        r3 = await ac.get("/historicos/curva-fechas", params={
            "curve": "lecap", "metric": "TEM", "f1": _HOY.isoformat(), "f2": _PREV.isoformat(),
            "exclude": c1.lower(), "dmin": "0,6", "dmax": "3"})
        assert r3.status_code == 200
        assert f'data-code="{c1}"' not in r3.text.split("hc-excluded")[0]
        assert f'class="hc-restore lnk" data-code="{c1}"' in r3.text   # ↺ para volver a incluirlo
        assert f'name="exclude" value="{c1}"' in r3.text and 'name="dmin" value="0,6"' in r3.text
        assert 'name="dmax" value="3"' in r3.text                       # el tramo vuelve al form (no la fecha máx. de la base)
        assert 'data-dur="0.82"' in r3.text and 'data-dur="0.47"' not in r3.text
        r2 = await ac.get("/historicos/curva", params={"curve": "lecap", "metric": "Last Price"})
        assert r2.status_code == 200 and "Precio" in r2.text
        # la página muestra el tab nuevo
        page = await ac.get("/historicos")
        assert "Curva por fecha + TR" in page.text


@pytest.mark.asyncio
async def test_presets_de_ventana_curva_fechas(base_sintetica) -> None:
    """Chips 1 sem / 1 mes / … / 1 año: Fecha 1 = última rueda, Fecha 2 =
    última rueda ≤ N atrás (rueda REAL, no un feriado), 3/4 vacías y TR en la
    misma ventana; los que la base no alcanza salen deshabilitados; el activo
    se infiere de las fechas (sin estado oculto). Sin JS: botones submit."""
    from backend.main import app
    from backend.routes.historico import _fecha_atras

    # meses calendario con el día recortado al fin de mes; "1 sem" = 7 días
    assert _fecha_atras("2026-03-31", meses=1) == "2026-02-28"
    assert _fecha_atras("2026-05-31", meses=3) == "2026-02-28"
    assert _fecha_atras("2028-02-29", meses=12) == "2027-02-28"
    assert _fecha_atras("2026-01-15", meses=2) == "2025-11-15"
    assert _fecha_atras("2026-09-16", dias=7) == "2026-09-09"
    # rueda real ≤ objetivo (bisect sobre las ruedas de la base)
    assert historico_byma.rueda_hasta(_HOY.isoformat()) == _HOY.isoformat()
    assert historico_byma.rueda_hasta((_HOY - timedelta(days=7)).isoformat()) == _PREV.isoformat()
    assert historico_byma.rueda_hasta((_PREV - timedelta(days=1)).isoformat()) is None
    assert historico_byma.rueda_hasta(None) is None
    hoy, prev = _HOY.isoformat(), _PREV.isoformat()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/historicos/curva-fechas", params={"curve": "lecap", "preset": "1s",
                                                            "f3": hoy, "trd1": hoy, "trd2": hoy})
        assert r.status_code == 200
        assert f'name="f1" value="{hoy}"' in r.text and f'name="f2" value="{prev}"' in r.text
        assert 'name="f3" value=""' in r.text and 'name="f4" value=""' in r.text   # el preset deja 2 curvas
        assert f'name="trd1" value="{prev}"' in r.text and f'name="trd2" value="{hoy}"' in r.text
        assert 'value="1s" class="hc-preset active"' in r.text                    # activo por coincidencia de fechas
        assert 'value="1a" class="hc-preset" disabled' in r.text                  # la base (1 mes) no llega a 1 año
        assert "TR realizado" in r.text and "<svg" in r.text
        # las mismas fechas a mano (sin preset) siguen marcando el chip; un
        # preset que la base no alcanza se ignora y quedan las fechas del form
        r2 = await ac.get("/historicos/curva-fechas", params={"curve": "lecap", "f1": hoy, "f2": prev})
        assert 'value="1s" class="hc-preset active"' in r2.text
        r3 = await ac.get("/historicos/curva-fechas", params={"curve": "lecap", "preset": "1a", "f1": hoy, "f2": hoy})
        assert r3.status_code == 200 and "hc-preset active" not in r3.text
        assert f'name="f2" value="{hoy}"' in r3.text
        # default sin fechas: última rueda vs 1 mes atrás (o la primera rueda si
        # la base es más corta) — acá la base tiene 1 mes justo → la primera rueda
        r4 = await ac.get("/historicos/curva-fechas", params={"curve": "lecap"})
        assert f'name="f1" value="{hoy}"' in r4.text and f'name="f2" value="{prev}"' in r4.text


@pytest.mark.asyncio
async def test_tramo_que_deja_todo_afuera_dice_por_que(base_sintetica) -> None:
    """Globales con un tramo 0,05–1 heredado de CER: la base TIENE historia pero
    el tramo saca a todos → el alert dice el motivo (n bonos, rango de duration)
    y ofrece quitar el tramo; con un tramo parcial, la leyenda lista los de
    afuera. Sin datos de verdad, el mensaje sigue siendo "no hay datos"."""
    from backend.main import app
    from backend.routes.historico import _scatter_chart, _tramo_txt

    assert _tramo_txt(0.05, 1.0) == "0,05 a 1" and _tramo_txt(None, 3.0) == "hasta 3"
    assert _tramo_txt(0.5, None) == "desde 0,5" and _tramo_txt(None, None) == ""
    hoy, prev = _HOY.isoformat(), _PREV.isoformat()
    sc = historico_byma.scatter_by_dates("lecap", [prev, hoy], "TEM", "todos")
    ch = _scatter_chart(sc, dmin=5.0, dmax=8.0)                  # lecaps: dur 0,47–0,82
    assert ch["n"] == 0 and ch["vacio"] == {"n": 2, "dur_min": 0.47, "dur_max": 0.82, "tramo": True, "exclusiones": False}
    ch2 = _scatter_chart(sc, dmax=0.6)                           # queda c1 (0,47); c2 (0,82) afuera
    assert ch2["n"] == 2 and ch2["fuera_tramo"] == [base_sintetica["c2"]] and ch2["tramo_txt"] == "hasta 0,6"
    ch3 = _scatter_chart(sc, exclude=[base_sintetica["c1"], base_sintetica["c2"]])
    assert ch3["n"] == 0 and ch3["vacio"]["exclusiones"] and not ch3["vacio"]["tramo"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/historicos/curva-fechas", params={
            "curve": "lecap", "f1": hoy, "f2": prev, "dmin": "5", "dmax": "8"})
        assert r.status_code == 200
        assert "Sin puntos por el filtro, no por falta de datos" in r.text and "2 bonos" in r.text
        assert "tramo de duration 5 a 8" in r.text and "Quitar el tramo" in r.text
        assert "hcQuitar(this, ['dmin','dmax'])" in r.text and "Quitar exclusiones" not in r.text
        r2 = await ac.get("/historicos/curva-fechas", params={"curve": "lecap", "f1": hoy, "f2": prev, "dmax": "0,6"})
        cola = r2.text.split("fuera del tramo hasta 0,6", 1)
        assert len(cola) == 2 and base_sintetica["c2"] in cola[1][:200] and "quitar tramo" in cola[1][:400]
        r3 = await ac.get("/historicos/curva-fechas", params={"curve": "lecap", "f1": "2001-01-05", "f2": "2001-01-12"})
        assert "la base no tiene datos de" in r3.text and "Quitar el tramo" not in r3.text
        js = await ac.get("/static/js/charts.js")
        assert "window.hcQuitar = function" in js.text


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
    assert ch["mixto"] is False                          # sin 'j' → un solo grupo
    g = ch["series"][0]["grupos"][0]
    assert g["proy"] is False and g["fit"] is True
    assert len(g["points"]) == len(puntos)              # los puntos no se tocan
    assert g["path"].count(" L ") + 1 >= 60             # muestreo suave (n=70)
    # la curva ajustada no se sale del área del gráfico (clamp al rango Y)
    ys = [float(seg.split(",")[1]) for seg in g["path"][2:].split(" L ")]
    assert min(ys) >= ch["y0"] - 0.6 and max(ys) <= ch["y1"] + 0.6

    # <4 puntos: sin fit → polilínea de los puntos tal cual, punteada
    sc2 = {"loaded": True, "metric": "TIREA", "curve_label": "CER",
           "series": [{"fecha": "2026-08-13", "points": puntos[:3]}]}
    g2 = _scatter_chart(sc2)["series"][0]["grupos"][0]
    assert g2["fit"] is False and g2["path"].count(" L ") == 2


def test_scatter_delta_bps_por_bono_es_el_mismo_del_hover() -> None:
    """Panel Δ bps (estilo Graph Curves de Bloomberg) debajo del scatter: una
    barra por bono con (última − primera fecha del bono) × 100 en bps — el
    MISMO Δ del hover —, ordenadas por duration, proy 'j' marcadas, amplió > 0
    / comprimió < 0, línea de cero y promedio. Con una sola fecha o sin bono
    presente en dos, no hay panel."""
    from backend.routes.historico import _bps_txt, _nice_step, _scatter_chart

    # códigos en orden NO alfabético y con la duration de la última fecha
    # distinta de la primera: el orden tiene que salir de la dur a la última fecha
    puntos = [{"code": c, "dur": d, "v": v} for c, d, v in
              [("ZA", 0.2, 0.30), ("MB", 0.5, 0.27), ("C3j", 0.9, 0.24), ("AD", 1.6, 0.20), ("E5", 2.4, 0.17)]]
    hoy = [dict(p, v=p["v"] + dv, dur=nd) for p, dv, nd in
           zip(puntos[:-1], (0.0023, -0.0085, 0.0, 0.0001), (0.8, 0.3, 1.2, 1.5))]   # MB pasa a ser la más corta
    sc = {"loaded": True, "metric": "TIREA", "curve_label": "CER",
          "series": [{"fecha": "2026-11-05", "points": hoy},          # desordenadas a propósito
                     {"fecha": "2026-10-29", "points": puntos}]}
    d = _scatter_chart(sc)["delta"]
    assert [b["code"] for b in d["bars"]] == ["MB", "ZA", "C3j", "AD"]      # E5 sólo en una fecha: sin barra
    bps = {b["code"]: b["bps"] for b in d["bars"]}
    assert bps["ZA"] == pytest.approx(23.0) and bps["MB"] == pytest.approx(-85.0)
    assert bps["C3j"] == pytest.approx(0.0) and bps["AD"] == pytest.approx(1.0)
    assert [b["txt"] for b in d["bars"]] == ["−85", "+23", "0", "+1"]
    assert d["f1"] == "2026-10-29" and d["f2"] == "2026-11-05" and d["n"] == 4
    assert d["prom"] == pytest.approx((23 - 85 + 0 + 1) / 4) and d["mixto"] is True
    assert _scatter_chart(sc)["n_curvas"] == 4                       # 2 fechas × (base + proy)
    # una fecha sin proy: 3 curvas, no "2 × fechas"
    sin_j = {**sc, "series": [sc["series"][0], {"fecha": "2026-10-29", "points": [p for p in puntos if not p["code"].endswith("j")]}]}
    assert _scatter_chart(sin_j)["n_curvas"] == 3
    assert next(b for b in d["bars"] if b["code"] == "C3j")["proy"] is True
    # geometría: amplió arriba de la línea de cero, comprimió abajo, alto = |Δ|
    mb, za = d["bars"][0], d["bars"][1]
    assert za["y"] < d["y_zero"] and za["y"] + za["h"] == pytest.approx(d["y_zero"], abs=0.2)
    assert mb["y"] == pytest.approx(d["y_zero"], abs=0.2) and mb["h"] > za["h"]
    assert d["x0"] == 62                                             # mismo margen izquierdo que el scatter
    assert any(t["v"] == "0" for t in d["ticks"])
    assert all(b["val_lbl"] and b["code_lbl"] for b in d["bars"])    # 4 barras: todos los rótulos entran
    # una sola fecha, o dos fechas sin ningún bono en común → nada que comparar
    assert _scatter_chart({**sc, "series": sc["series"][:1]})["delta"] is None
    disjuntas = {**sc, "series": [{"fecha": "2026-11-05", "points": puntos[:2]},
                                  {"fecha": "2026-10-29", "points": puntos[2:]}]}
    assert _scatter_chart(disjuntas)["delta"] is None
    # medio bps redondea lejos de cero, como el toFixed(0) del hover (12,5 → 13, no 12)
    assert _bps_txt(-0.4) == "0" and _bps_txt(1234) == "+1234" and _bps_txt(-85) == "−85"
    assert _bps_txt(12.5) == "+13" and _bps_txt(-12.5) == "−13" and _bps_txt(0.5) == "+1" and _bps_txt(2.5) == "+3"
    assert _nice_step(300) == 100 and _nice_step(47) == 20 and _nice_step(1500) == 500
    # semana quieta (Δ de ±0,4 bps): el eje no colapsa a cuatro "0" — rango mínimo ±5, paso ≥ 1
    quieta = {**sc, "series": [{"fecha": "2026-10-29", "points": puntos[:2]},
                               {"fecha": "2026-11-05", "points": [dict(puntos[0], v=0.30003), dict(puntos[1], v=0.26996)]}]}
    dq = _scatter_chart(quieta)["delta"]
    assert len({t["v"] for t in dq["ticks"]}) == len(dq["ticks"]) and {"−5", "0", "5"} <= {t["v"] for t in dq["ticks"]}
    # muchas barras (corp_hdmep tiene 170+): sin rótulo de valor y un código cada k barras
    muchos = [{"code": f"B{i:03d}", "dur": 0.1 + i * 0.05, "v": 0.10} for i in range(174)]
    dm = _scatter_chart({**sc, "series": [{"fecha": "2026-10-29", "points": muchos},
                                          {"fecha": "2026-11-05", "points": [dict(p, v=0.101) for p in muchos]}]})["delta"]
    assert dm["n"] == 174 and not any(b["val_lbl"] for b in dm["bars"])
    assert 1 < sum(b["code_lbl"] for b in dm["bars"]) < 174 and dm["bars"][0]["code_lbl"]


@pytest.mark.asyncio
async def test_http_curva_fechas_trae_el_panel_delta(base_sintetica) -> None:
    from backend.main import app
    c1 = base_sintetica["c1"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/historicos/curva-fechas", params={
            "curve": "lecap", "metric": "TIREA", "f1": _HOY.isoformat(), "f2": _PREV.isoformat()})
        assert r.status_code == 200
        assert 'class="hc-delta"' in r.text and "Δ TIREA por bono" in r.text
        assert f'class="hc-dgrp" data-code="{c1}"' in r.text                  # barra por bono
        assert "−400" in r.text and "hc-dbar hc-dn" in r.text                 # 34% → 30%: comprimió 400 bps
        assert f"{_PREV.strftime('%d/%m/%Y')} → {_HOY.strftime('%d/%m/%Y')}" in r.text
        # checkbox "proy (j)" del título: prendido con Tipo = Todos, apagado con Base
        assert 'class="hc-proy-toggle" checked' in r.text
        rb = await ac.get("/historicos/curva-fechas", params={
            "curve": "lecap", "metric": "TIREA", "f1": _HOY.isoformat(), "f2": _PREV.isoformat(), "proy": "base"})
        assert rb.status_code == 200 and 'class="hc-proy-toggle">' in rb.text and 'hc-proy-toggle" checked' not in rb.text
        # una sola fecha con datos (la 2ª cae lejos de toda rueda y no entra a la
        # foto; vacía el server la completa con el preset "1 mes"): scatter sí, panel Δ no
        r1 = await ac.get("/historicos/curva-fechas", params={
            "curve": "lecap", "metric": "TIREA", "f1": _HOY.isoformat(),
            "f2": (_PREV - timedelta(days=20)).isoformat()})
        assert r1.status_code == 200 and 'class="hc-pt"' in r1.text and 'class="hc-delta"' not in r1.text


def test_scatter_fit_por_grupo_real_y_proy() -> None:
    """El caso de la captura del usuario: con Tipo=Todos, los reales (TEM
    ~0,3-0,8%) y los proyectados 'j' (~2,1-2,5%) son DOS nubes — una sola NSS
    por el medio no describía a ninguna. Ahora: un fit POR GRUPO por fecha,
    proy con flag para marcador hueco/punteado, y el eje X nunca negativo."""
    from backend.routes.historico import _scatter_chart

    reales = [{"code": f"R{i}", "dur": 0.3 + i * 0.5, "v": 0.005 + 0.0004 * i}
              for i in range(6)]
    proys = [{"code": f"P{i}j", "dur": 0.3 + i * 0.5, "v": 0.021 + 0.0003 * i}
             for i in range(6)]
    sc = {"loaded": True, "metric": "TEM", "curve_label": "CER",
          "series": [{"fecha": "2026-09-04", "points": reales + proys}]}
    ch = _scatter_chart(sc)
    s = ch["series"][0]
    assert ch["mixto"] is True and len(s["grupos"]) == 2
    g_real = next(g for g in s["grupos"] if not g["proy"])
    g_proy = next(g for g in s["grupos"] if g["proy"])
    assert len(g_real["points"]) == 6 and len(g_proy["points"]) == 6
    assert g_real["path"] != g_proy["path"]              # dos curvas, no una promedio
    assert all(str(p["code"]).endswith("j") for p in g_proy["points"])
    assert ch["xticks"][0]["v"] >= 0                     # sin duration negativa
