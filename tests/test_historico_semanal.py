"""Resumen semanal por segmento en Históricos: Δ Precio % + Δ TIR (pp) por
categoría (mismas que Escenario), sobre la serie histórica por bono."""
from __future__ import annotations

import pytest

from backend.services import bond_universe, curves
from backend.services import historico_byma as hb


def test_weekly_segments_calcula_deltas():
    bond_universe.ensure_loaded()
    cer = curves.build_curve_codes().get("cer", [])
    if not cer:
        pytest.skip("sin curva cer")
    code = cer[0]
    # by_code sintético: precio +1%, TIR −0,5pp, TEM −0,1pp, duration 0,3 (→ CER corto)
    prev = hb._cache
    hb._cache = {
        "loaded": True, "error": None, "bounds": ("2026-06-18", "2026-06-25"),
        "by_code": {code: {"dates": ["2026-06-18", "2026-06-25"],
                           "vals": {"Last Price": [100.0, 101.0],
                                    "TIREA": [0.50, 0.495], "TEM": [0.030, 0.029],
                                    "Duration": [0.3, 0.3]}}},
    }
    try:
        res = hb.weekly_segments(7)
    finally:
        hb._cache = prev
    assert res["loaded"] and res["start"] == "2026-06-18" and res["end"] == "2026-06-25"
    seg = next((s for s in res["segments"] if code in s["members"]), None)
    assert seg is not None and seg["key"] == "cer_corto"
    assert abs(seg["dprice"] - 0.01) < 1e-9        # +1 %
    assert abs(seg["dtir"] - (-0.005)) < 1e-9       # −0,5 pp (compresión)
    assert {"cer", "a3500", "tamar_ini", "tamar_fin", "tamar_delta"} <= set(res["indices"])
    # detalle por bono: Δprecio / ΔTIR / ΔTEM
    row = next((r for r in seg["rows"] if r["code"] == code), None)
    assert row is not None
    assert abs(row["dprice"] - 0.01) < 1e-9
    assert abs(row["dtir"] - (-0.005)) < 1e-9
    assert abs(row["dtem"] - (-0.001)) < 1e-9        # 0,029 − 0,030
    # CER no es tasa variable → sin margen TNA
    assert row["margen"] is None and row["dmargen"] is None
    assert seg["has_margen"] is False


def test_margen_tna_formula():
    """Margen = TNA30(TIR) − bench/100; None si falta benchmark o TIR.
    TNA_30 = ((1+TIREA)^(30/365) − 1) × (365/30)."""
    entry = {"dates": ["2026-06-25"], "vals": {"TIREA": [0.50]}}
    tna30 = ((1.0 + 0.50) ** (30.0 / 365.0) - 1.0) * (365.0 / 30.0)
    assert abs(hb._margen_tna(entry, 30.0, "2026-06-25") - (tna30 - 0.30)) < 1e-9
    assert hb._margen_tna(entry, None, "2026-06-25") is None
    assert hb._margen_tna({"dates": ["2026-06-25"], "vals": {}}, 30.0, "2026-06-25") is None


def test_weekly_segments_margen_solo_variable(monkeypatch):
    """El margen TNA SÍ aparece en un bono de tasa variable (TAMAR). Se fija el
    benchmark TAMAR a 30 % para no depender de la serie BCRA del entorno."""
    bond_universe.ensure_loaded()
    tamar = curves.build_curve_codes().get("tamar", [])
    if not tamar:
        pytest.skip("sin curva tamar")
    code = tamar[0]
    monkeypatch.setattr(hb, "_index_at", lambda key, col, target: 30.0 if key == "tamar" else None)
    prev = hb._cache
    hb._cache = {
        "loaded": True, "error": None, "bounds": ("2026-06-18", "2026-06-25"),
        "by_code": {code: {"dates": ["2026-06-18", "2026-06-25"],
                           "vals": {"Last Price": [100.0, 101.0], "TIREA": [0.50, 0.495],
                                    "TNA": [0.45, 0.46], "TEM": [0.030, 0.029],
                                    "Duration": [0.3, 0.3]}}},
    }
    try:
        res = hb.weekly_segments(7)
    finally:
        hb._cache = prev
    seg = next((s for s in res["segments"] if code in s["members"]), None)
    assert seg is not None and seg["has_margen"] is True
    row = next((r for r in seg["rows"] if r["code"] == code), None)
    assert row is not None and row["margen"] is not None and row["dmargen"] is not None


def test_weekly_segments_duales_separados(monkeypatch):
    """Los duales aparecen como segmentos separados: la pata TAMAR ('…v', que en el
    Excel cae bajo el ticker base) trae margen; la base fija/CER no."""
    bond_universe.ensure_loaded()
    codes = curves.build_curve_codes()
    fija, tamar_fija = codes.get("dualfija", []), codes.get("dualtamar_fija", [])
    if not fija or not tamar_fija:
        pytest.skip("sin duales fija/tamar en el universo")
    base = sorted(fija)[0]            # p.ej. TTD26 (ficha FIJA = ticker traded del Excel)
    monkeypatch.setattr(hb, "_index_at", lambda key, col, target: 30.0 if key == "tamar" else None)
    prev = hb._cache
    hb._cache = {
        "loaded": True, "error": None, "bounds": ("2026-06-18", "2026-06-25"),
        "by_code": {base: {"dates": ["2026-06-18", "2026-06-25"],
                           "vals": {"Last Price": [100.0, 101.0], "TIREA": [0.50, 0.495],
                                    "TEM": [0.030, 0.029], "Duration": [0.3, 0.3]}}},
    }
    try:
        res = hb.weekly_segments(7)
    finally:
        hb._cache = prev
    segs = {s["key"]: s for s in res["segments"]}
    # base Fija/TAMAR: aparece, SIN margen (no es floater)
    assert "dual_fija" in segs and segs["dual_fija"]["has_margen"] is False
    # pata TAMAR/Fija: aparece (vía fallback '…v' → ticker base) y CON margen
    assert "dual_tamar_fija" in segs and segs["dual_tamar_fija"]["has_margen"] is True
    assert segs["dual_tamar_fija"]["rows"][0]["margen"] is not None


_VER = iter(range(10_000, 20_000))


def _cache_sintetico(code: str) -> dict:
    return {
        "loaded": True, "error": None, "bounds": ("2026-06-18", "2026-06-25"), "ver": next(_VER),
        "by_code": {code: {"dates": ["2026-06-18", "2026-06-25"],
                           "vals": {"Last Price": [100.0, 101.0], "TIREA": [0.50, 0.495],
                                    "TEM": [0.030, 0.029], "Duration": [0.3, 0.3]}}},
    }


def test_weekly_segments_sin_segmentos_repetidos(monkeypatch):
    """Los tres duales que también son categoría de Escenario (Dual TAMAR/CER,
    Dual CER/TAMAR, Dual TAMAR/DLK) salían DOS veces en Qué pasó (CATEGORIES +
    DUAL_CATEGORIES a secas). Cada key una vez y los seis duales juntos al
    final, después de Globales / Bonares."""
    from backend.services import escenario as esc

    bond_universe.ensure_loaded()
    codes = curves.build_curve_codes()
    monkeypatch.setattr(hb, "_index_at", lambda key, col, target: 30.0 if key == "tamar" else None)
    prev = hb._cache
    # un bono con dato en CADA curva de las categorías → todos los segmentos presentes
    by_code = {}
    for cat in esc.CATEGORIES + esc.DUAL_CATEGORIES:
        for c in codes.get(cat.curve, [])[:1]:
            by_code[c] = _cache_sintetico(c)["by_code"][c]
    hb._cache = {"loaded": True, "error": None, "bounds": ("2026-06-18", "2026-06-25"), "by_code": by_code}
    try:
        res = hb.weekly_segments(7)
    finally:
        hb._cache = prev
    keys = [s["key"] for s in res["segments"]]
    assert len(keys) == len(set(keys)), keys
    duales = [k for k in keys if k.startswith("dual_")]
    if duales:
        assert keys[-len(duales):] == duales                       # todos los duales al final, juntos
        assert "globales" not in keys[-len(duales):] and "bonares" not in keys[-len(duales):]
    assert keys.count("dual_tamar_cer") <= 1 and keys.count("dual_cer") <= 1 and keys.count("dual_tamar_dlk") <= 1


@pytest.mark.asyncio
async def test_partial_semanal_lleva_los_datos_por_bono_para_el_tilde():
    """El detalle por bono lleva sus valores en data-* y un checkbox por fila;
    el encabezado del segmento tiene las celdas `.sem-c-*` que app.js rehace
    sin los destildados (tests/quepaso_harness.cjs prueba el cálculo)."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    bond_universe.ensure_loaded()
    cer = curves.build_curve_codes().get("cer", [])
    if not cer:
        pytest.skip("sin curva cer")
    code = cer[0]
    prev = hb._cache
    hb._cache = _cache_sintetico(code)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            r = await ac.get("/historicos/semanal?dias=7")
    finally:
        hb._cache = prev
    assert r.status_code == 200
    h = r.text
    assert 'data-seg="cer_corto"' in h
    assert f'data-code="{code}"' in h and 'data-dprice="0.01' in h and 'data-tir1="0.495"' in h
    assert 'data-dur="0.3"' in h and 'class="sem-chk"' in h
    for cls in ("sem-c-n", "sem-c-dprice", "sem-c-dtir", "sem-c-dtem", "sem-c-tir", "sem-c-tem", "sem-c-dur", "sem-c-cup"):
        assert cls in h, cls
    assert f'class="sem-m" data-m="{code}"' in h and 'class="lnk sem-all"' in h
    # precio inicial → final por bono (y las fechas reales sólo si difieren de la ventana)
    assert "Precio ini → fin" in h and "100,00 → 101,00" in h and "sem-fechas" not in h
    assert "2 ruedas" in h and "⚠" not in h


def test_quepaso_harness_js():
    """Las funciones puras de app.js (promedios sin los destildados + formatos
    es-AR del encabezado) corren en Node contra filas de muestra."""
    import json
    import shutil
    import subprocess
    from pathlib import Path

    node = shutil.which("node")
    if not node:
        pytest.skip("node no disponible")
    harness = Path(__file__).resolve().parent / "quepaso_harness.cjs"
    out = subprocess.run([node, str(harness)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stdout + out.stderr
    res = json.loads(out.stdout.strip().splitlines()[-1])
    assert res["ok"] is True, res["fallos"]


def test_weekly_segments_ventana_efectiva_y_hueco():
    """El inicio de la ventana es la última RUEDA de la base ≤ inicio pedido (no
    la fecha calendario), se informan las ruedas que abarca y, si la base tiene
    un hueco grande justo ahí, un aviso con la ventana efectiva; cada fila
    lleva precio y fechas reales del Δ (`desfasado` cuando no son las de la
    ventana). Antes '1 mes' podía medir mes y medio sin decirlo."""
    bond_universe.ensure_loaded()
    cer = curves.build_curve_codes().get("cer", [])
    if len(cer) < 3:
        pytest.skip("sin curva cer")
    a, b, c = cer[0], cer[1], cer[2]
    prev = hb._cache
    # base con ruedas 05-20, 06-01 y 06-19…06-25 (hueco de 18 días): '7 días' pide
    # el 06-18 → la rueda efectiva es el 06-01 → aviso. b sólo cotiza desde el
    # 06-22 (sin dato inicial → sin Δ, no se inventa uno); c no tiene dato el
    # 06-01 y su inicial es del 05-20 → Δ desfasado, con las fechas reales.
    hb._cache = {
        "loaded": True, "error": None, "bounds": ("2026-05-20", "2026-06-25"), "ver": next(_VER),
        "by_code": {
            a: {"dates": ["2026-06-01", "2026-06-19", "2026-06-25"],
                "vals": {"Last Price": [100.0, 103.0, 104.0], "TIREA": [0.50, 0.49, 0.48],
                         "TEM": [0.030, 0.0295, 0.029], "Duration": [0.3, 0.3, 0.3]}},
            b: {"dates": ["2026-06-22", "2026-06-25"],
                "vals": {"Last Price": [200.0, 202.0], "TIREA": [0.40, 0.39],
                         "TEM": [0.028, 0.0275], "Duration": [0.3, 0.3]}},
            c: {"dates": ["2026-05-20", "2026-06-25"],
                "vals": {"Last Price": [300.0, 309.0], "TIREA": [0.45, 0.44],
                         "TEM": [0.029, 0.0285], "Duration": [0.3, 0.3]}},
        },
    }
    try:
        res = hb.weekly_segments(7)
    finally:
        hb._cache = prev
    assert res["start_req"] == "2026-06-18" and res["start"] == "2026-06-01"
    assert res["hueco_dias"] == 17 and res["dias_efectivos"] == 24 and res["n_ruedas"] == 4
    assert res["aviso"] and "01/06/2026" in res["aviso"] and "19/06/2026" in res["aviso"] and "24 días" in res["aviso"]
    seg = next(s for s in res["segments"] if a in s["members"])
    ra = next(r for r in seg["rows"] if r["code"] == a)
    assert ra["p0"] == 100.0 and ra["p1"] == 104.0 and ra["f0"] == "2026-06-01" and ra["f1"] == "2026-06-25"
    assert abs(ra["dprice"] - 0.04) < 1e-9 and ra["desfasado"] is False
    rb = next(r for r in seg["rows"] if r["code"] == b)
    assert rb["p0"] is None and rb["dprice"] is None and rb["desfasado"] is False
    rc = next(r for r in seg["rows"] if r["code"] == c)
    assert rc["f0"] == "2026-05-20" and rc["desfasado"] is True and rc["f0_ar"] == "20/05/2026"
    assert abs(rc["dprice"] - 0.03) < 1e-9 and rc["p0"] == 300.0
    assert abs(seg["dprice"] - (0.04 + 0.03) / 2) < 1e-9                  # b (sin Δ) no entra al promedio
    # sin hueco: sin aviso, inicio = rueda pedida
    hb._cache = _cache_sintetico(a)
    try:
        res2 = hb.weekly_segments(7)
    finally:
        hb._cache = prev
    assert res2["start"] == "2026-06-18" and res2["aviso"] is None and res2["n_ruedas"] == 2
    # CSV: precios y fechas por bono + aviso
    from backend.services import quepaso_report
    hb._cache = {
        "loaded": True, "error": None, "bounds": ("2026-06-01", "2026-06-25"), "ver": next(_VER),
        "by_code": {a: {"dates": ["2026-06-01", "2026-06-25"],
                        "vals": {"Last Price": [100.0, 104.0], "TIREA": [0.50, 0.48],
                                 "TEM": [0.030, 0.029], "Duration": [0.3, 0.3]}}},
    }
    try:
        csv = quepaso_report.csv_es_ar(7)
    finally:
        hb._cache = prev
    assert "AVISO;" in csv and "Precio ini;Precio fin;Fecha ini;Fecha fin" in csv
    fila = next(l for l in csv.splitlines() if l.startswith(f"CER corto;{a};"))
    assert fila.startswith(f"CER corto;{a};0,30;4,00;")                      # cupones: depende del bono
    assert fila.endswith(";-2,00;-0,10;50,00;48,00;100,00;104,00;01/06/2026;25/06/2026")


def test_weekly_segments_sin_data():
    prev = hb._cache
    hb._cache = {"loaded": False, "error": "x", "bounds": (None, None), "by_code": {}}
    try:
        res = hb.weekly_segments(7)
    finally:
        hb._cache = prev
    assert res["loaded"] is False and res["segments"] == []


def test_index_at_robusto_a_indice_mixto():
    """Regresión A3500: el poller de FX inyectaba hoy con índice STRING → índice
    mixto (date + str) que rompía la comparación y dejaba la deva A3500 en None.
    `_index_at` ahora salta etiquetas no parseables y sigue dando el valor."""
    import rentafija
    from datetime import date, timedelta
    a3500 = rentafija.inputs.get("a3500")
    if a3500 is None or "tca3500" not in getattr(a3500, "columns", []):
        pytest.skip("sin serie a3500")
    # contaminar el índice con una etiqueta string (reproduce el bug viejo)
    rentafija.inputs["a3500"].loc["2026-06-26", "tca3500"] = 1480.0
    start = (date(2026, 6, 26) - timedelta(days=7)).isoformat()
    idx = hb._window_indices(start, "2026-06-25")
    assert idx["a3500"] is not None        # antes daba None por el TypeError str<=date
    assert hb._index_at("a3500", "tca3500", start) is not None


def test_segment_curve_geometria():
    """El SVG de 'curva antes/ahora' necesita ≥2 bonos con dur + TIR en ambos
    extremos; con menos devuelve None. Ejes: X=duration, Y=TIR (×100)."""
    from backend.routes.historico import _segment_curve
    rows = [
        {"code": "A", "dur": 0.5, "tir0": 0.30, "tir1": 0.28},
        {"code": "B", "dur": 1.5, "tir0": 0.32, "tir1": 0.29},
        {"code": "C", "dur": 2.5, "tir0": None, "tir1": 0.31},   # descartada (tir0 None)
    ]
    c = _segment_curve(rows)
    assert c is not None
    assert len(c["before"]) == 2 and len(c["after"]) == 2       # C descartada
    assert c["path_before"].startswith("M ") and c["path_after"].startswith("M ")
    assert len(c["yticks"]) == 5 and len(c["xticks"]) == 5
    # ordenado por duration → primer nodo es el de dur menor
    assert c["after"][0]["dur"] == 0.5
    assert _segment_curve(rows[:1]) is None                     # 1 punto → sin curva
    assert _segment_curve([]) is None


@pytest.mark.asyncio
async def test_historicos_semanal_curva_render():
    """Con ≥2 bonos CER en el mismo bucket, el partial dibuja el SVG de curva
    antes/ahora (leyenda + paths) dentro del acordeón del segmento."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    bond_universe.ensure_loaded()
    cer = curves.build_curve_codes().get("cer", [])
    if len(cer) < 2:
        pytest.skip("se necesitan ≥2 CER")
    c0, c1 = cer[0], cer[1]
    prev = hb._cache
    hb._cache = {
        "loaded": True, "error": None, "bounds": ("2026-06-18", "2026-06-25"),
        "by_code": {
            c0: {"dates": ["2026-06-18", "2026-06-25"],
                 "vals": {"Last Price": [100.0, 101.0], "TIREA": [0.50, 0.48],
                          "TEM": [0.030, 0.029], "Duration": [0.3, 0.3]}},
            c1: {"dates": ["2026-06-18", "2026-06-25"],
                 "vals": {"Last Price": [100.0, 100.5], "TIREA": [0.52, 0.49],
                          "TEM": [0.031, 0.030], "Duration": [0.45, 0.45]}},
        },
    }
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            r = await ac.get("/historicos/semanal?dias=7")
    finally:
        hb._cache = prev
    assert r.status_code == 200 and "Traceback" not in r.text
    assert "Cómo se movió la curva" in r.text and "sem-curve" in r.text
    assert "sem-lg-before" in r.text and "sem-lg-after" in r.text


@pytest.mark.asyncio
async def test_historicos_semanal_endpoint_no_crash():
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        for d in (7, 14, 30):
            r = await ac.get(f"/historicos/semanal?dias={d}")
            assert r.status_code == 200 and "Traceback" not in r.text
        # "Qué pasó" ahora es su propia pestaña (/que-paso), no un sub-tab de Históricos
        pg = await ac.get("/que-paso")
        assert pg.status_code == 200 and 'id="hist-semanal"' in pg.text and "Qué pasó" in pg.text


@pytest.mark.asyncio
async def test_historicos_semanal_detalle_render(monkeypatch):
    """Con cache inyectada (bono TAMAR = floater) y benchmark fijo, el partial
    renderiza el detalle por bono CON la columna Margen (Δ TEM, sub-tabla, código)."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    bond_universe.ensure_loaded()
    tamar = curves.build_curve_codes().get("tamar", [])
    if not tamar:
        pytest.skip("sin curva tamar")
    code = tamar[0]
    monkeypatch.setattr(hb, "_index_at", lambda key, col, target: 30.0 if key == "tamar" else None)
    prev = hb._cache
    hb._cache = {
        "loaded": True, "error": None, "bounds": ("2026-06-18", "2026-06-25"),
        "by_code": {code: {"dates": ["2026-06-18", "2026-06-25"],
                           "vals": {"Last Price": [100.0, 101.0], "TIREA": [0.50, 0.495],
                                    "TNA": [0.45, 0.46], "TEM": [0.030, 0.029],
                                    "Duration": [0.3, 0.3]}}},
    }
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            r = await ac.get("/historicos/semanal?dias=7")
    finally:
        hb._cache = prev
    assert r.status_code == 200 and "Traceback" not in r.text
    assert "Δ TEM" in r.text and "Margen" in r.text       # encabezados del detalle
    assert 'class="sem-detail"' in r.text                  # sub-tabla anidada
    assert code in r.text                                  # fila por bono
