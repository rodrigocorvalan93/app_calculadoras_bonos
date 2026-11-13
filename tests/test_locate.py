"""📍 Ubicación en la curva — reverse lookup + contenedores en YAS/Comparador."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

from backend.services import bond_universe, curves


def test_curve_key_for() -> None:
    bond_universe.ensure_loaded()
    # Los códigos cortos van tomados de la PROPIA curva: hardcodear un ticker
    # era una bomba de tiempo — al vencer sale de la curva (build_curve_codes
    # filtra vencidos) y el lookup devuelve None (pasó con S31L6, jul-2026).
    table = curves.build_curve_codes()
    assert curves.curve_key_for(table["cer"][0]) == "cer"
    assert curves.curve_key_for(table["lecap"][0]) == "lecap"
    assert curves.curve_key_for("TXMJ9") == "dualcer"    # dual jun-2029
    assert curves.curve_key_for("TXMJ9v") == "dualtamar"
    assert curves.curve_key_for("GGAL") is None          # acciones: sin curva


@pytest.mark.asyncio
async def test_yas_locate_container() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.post("/yas/recompute", data={
            "code": "TX28", "mode": "precio", "value": "1450,00", "plazo": "24hs"})
    assert r.status_code == 200
    assert "data-locate" in r.text and 'data-curve="cer"' in r.text
    assert "Ubicación en la curva" in r.text


@pytest.mark.asyncio
async def test_comparador_locate_solo_misma_curva() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        # TZX27 y TX28 son ambos CER (par robusto; TZX26, TZXO6 y TX26 se
        # reclasificaron a tasa fija → lecap, desk 23/10).
        same = await ac.get("/comparador/result?a=TZX27&b=TX28&mode=precio&val_a=1450&val_b=1500&plazo=24hs")
        cross = await ac.get("/comparador/result?a=TX28&b=S31L6&mode=precio&val_a=1500&val_b=132&plazo=24hs")
    assert same.status_code == 200 and cross.status_code == 200
    assert "data-locate" in same.text and 'data-curve="cer"' in same.text   # cer vs cer ✓
    assert "data-locate" not in cross.text                                  # cer vs lecap ✗


def test_mix_label_y_orden() -> None:
    """El label sintético de la combinada y el dedup en orden."""
    from backend.services import curves as cv
    bond_universe.ensure_loaded()
    assert cv.mix_label(["globales", "bonares"]).startswith("Combinada:")
    # dedup preservando orden: la misma curva dos veces no duplica códigos
    once = cv.mix_codes(["cer"])
    twice = cv.mix_codes(["cer", "cer"])
    assert once == twice


@pytest.mark.asyncio
async def test_curvas_combinada_adhoc() -> None:
    """mix:a,b → unión de curvas; el endpoint y el label sintético andan."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.services import curves as cv

    bond_universe.ensure_loaded()
    union = cv.mix_codes(["globales", "bonares"])
    assert set(union) == set(cv.build_curve_codes()["globales"]) | set(cv.build_curve_codes()["bonares"])
    assert cv.curve_key_for("TX28") == "cer"             # reverse-map intacto
    assert cv.curve_key_for("T30J7") == "lecap"          # soberano ARS tasa fija (TX26 venció el 09/11/2026)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/curves/table", params={"curve": "mix:globales,bonares", "plazo": "24hs"})
    assert r.status_code == 200 and "Combinada" in r.text


@pytest.mark.asyncio
async def test_graficos_data_lleva_los_codigos_alineados_a_xs() -> None:
    """El widget de Ubicación etiqueta cada punto con `codes[i]`: tiene que
    venir alineado a `xs` (un None donde el x no es un bono de la curva)."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.services import marketdata_store as mds
    from backend.services import symbols as syms

    bond_universe.ensure_loaded()
    codes = curves.build_curve_codes().get("cer", [])
    if len(codes) < 4:
        pytest.skip("curva CER insuficiente")
    store = mds.get_store()                                   # la suite corre sin feed: sembrar precios
    for i, c in enumerate(codes):
        store.update_from_md(syms.md_symbol(c, "24hs"), {"LA": {"price": 95.0 + i * 0.7},
                                                         "CL": {"price": 94.9 + i * 0.7}, "EV": 2e7, "NV": 2e5})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/graficos/data?curve=cer&plazo=24hs&only_quoting=false")
    assert r.status_code == 200
    d = r.json()
    assert len(d["codes"]) == len(d["xs"]) and d["ylabel"]
    assert any(c for c in d["codes"])


@pytest.mark.skipif(shutil.which("node") is None, reason="node no disponible")
def test_locate_etiqueta_los_codigos_y_muestra_tooltip_en_node() -> None:
    """13/11 (desk): en el gráfico de YAS se leen los códigos de los bonos de la
    curva — etiqueta tenue sobre cada punto (el resaltado primero y en su
    color) y tooltip código · TIR · duration al pasar el mouse; se oculta al
    salir. Corre el bloque real de charts.js con un uPlot falso."""
    r = subprocess.run([shutil.which("node"), str(ROOT / "tests" / "locate_harness.cjs")],
                       capture_output=True, text=True, encoding="utf-8", timeout=120, check=False)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["ok"] and out["xs"] == [0.5, 0.8, 1.0, 1.5]              # el resaltado se intercala en su duration
    assert out["labels_series"] == ["ARS", "USD", "NSS", "S29G6"]
    assert out["etiquetas"][0] == "S29G6" and sorted(out["etiquetas"]) == ["AL30C", "S29G6", "S31L6", "T30E6"]
    assert out["tip_curva"] == "<b>AL30C</b><br>TIREA 8,00% · Dur 1,00"
    assert out["tip_resaltado"].startswith("<b>S29G6</b> · a tu precio<br>TIREA 32,50%")
    assert out["tip_oculto"] == "none"
