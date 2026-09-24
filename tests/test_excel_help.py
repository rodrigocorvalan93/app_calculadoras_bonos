"""La ayuda del panel del add-in (taskpane.html) está completa y al día.

El panel es lo único que ve un usuario de la mesa sin abrir el repo: tiene
que listar TODAS las funciones publicadas en functions.json con un ejemplo,
decir cuáles van en vivo y cuáles son puntuales (y cómo recalcularlas), y
ofrecer el botón «Recalcular puntuales» (recálculo completo + memo vacío).
FORMULAS.md, la referencia larga, tiene que cubrir las mismas funciones."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCEL = ROOT / "backend/static/excel"


def _ids() -> list[str]:
    fj = json.loads((EXCEL / "functions.json").read_text(encoding="utf-8"))
    return [f["id"] for f in fj["functions"]]


def test_panel_lista_todas_las_funciones_con_ejemplo() -> None:
    tp = (EXCEL / "taskpane.html").read_text(encoding="utf-8")
    ids = _ids()
    assert len(ids) >= 18
    for fid in ids:
        assert f"=OMS.{fid}(" in tp, f"falta un ejemplo de OMS.{fid} en el panel"
    # lo nuevo de esta tanda: A3500 oficial con fecha, MACRO con promedio de 5 ruedas
    assert '=OMS.FX("a3500")' in tp and '("a3500_fecha")' in tp and '("cierre")' in tp
    assert '=OMS.MACRO("tamar5")' in tp and "VERDADERO" in tp
    # DURATION es Macaulay (la del YAS), no "modified"
    assert "Macaulay" in tp and "modified duration" not in tp.lower()
    assert 'href="FORMULAS.md"' in tp


def test_panel_explica_en_vivo_vs_puntuales_y_tiene_recalcular() -> None:
    tp = (EXCEL / "taskpane.html").read_text(encoding="utf-8")
    js = (EXCEL / "taskpane.js").read_text(encoding="utf-8")
    fn = (EXCEL / "functions.js").read_text(encoding="utf-8")
    fj = json.loads((EXCEL / "functions.json").read_text(encoding="utf-8"))
    streaming = {f["id"] for f in fj["functions"] if (f.get("options") or {}).get("stream")}
    puntuales = {f["id"] for f in fj["functions"] if f["id"] not in streaming and f["id"] not in ("PING", "DIAG")}
    assert streaming == {"QUOTE", "FX", "ROFEX", "CAUCION", "TABLA"}
    vivo = tp.split("<strong>Puntuales</strong>")[0].split("<strong>En vivo</strong>")[1]
    punt = tp.split("<strong>Puntuales</strong>")[1].split("<strong>Series macro</strong>")[0]
    for fid in streaming:
        assert f"<code>{fid}</code>" in vivo, fid
    for fid in puntuales:
        assert f"<code>{fid}</code>" in punt, fid
    assert "Ctrl+Alt+F9" in tp and 'id="recalc"' in tp
    # el botón: memo vacío + recálculo completo, y fallback legible sin API de Excel
    assert "OMSCalc.reset()" in js and 'calculate("Full")' in js and "Ctrl+Alt+F9" in js
    assert "function reset() { memo = {}; memoN = 0; }" in fn and "reset: reset" in fn
    # ninguna función custom es volátil (se dispararían con cada edición del libro)
    assert "volatile" not in json.dumps(fj)


def test_referencia_larga_cubre_todas_las_funciones_y_no_promete_f9() -> None:
    doc = (EXCEL / "FORMULAS.md").read_text(encoding="utf-8")
    for fid in _ids():
        if fid in ("PING", "DIAG"):
            continue
        assert f"OMS.{fid}" in doc, fid
    # las puntuales se recalculan con Ctrl+Alt+F9: la doc no puede seguir diciendo "con F9"
    assert not re.search(r"\bcon F9\b|\(F9\)", doc), "FORMULAS.md promete F9 a secas"
    assert "Ctrl+Alt+F9" in doc and "modified duration" not in doc.lower()
