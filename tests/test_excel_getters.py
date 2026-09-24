"""Getters del add-in de Excel con el functions.js REAL en Node
(tests/excel_getters_harness.cjs): OMS.TABLA("rofex") mayorista y
"rofex_min" / "futuros_min" minorista (el canal en el nombre gana a la opción),
canal "minorista" / "mayorista" en OMS.ROFEX, OMS.FX("a3500") oficial con
fecha / anterior / variación y fallback al cierre del feed, wantsDate e
isoToSerial de OMS.MACRO."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("node") is None, reason="node no disponible")
def test_getters_js_en_node() -> None:
    r = subprocess.run([shutil.which("node"), str(ROOT / "tests" / "excel_getters_harness.cjs")],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert len(out) >= 25
    malos = {k: v for k, v in out.items() if v is not True}
    assert not malos, malos


def test_docs_y_panel_mencionan_rofex_min() -> None:
    ex = ROOT / "backend/static/excel"
    fj = json.loads((ex / "functions.json").read_text(encoding="utf-8"))
    tabla = next(f for f in fj["functions"] if f["id"] == "TABLA")
    assert "rofex_min" in tabla["parameters"][0]["description"] and "minorista" in tabla["parameters"][1]["description"]
    assert "rofex_min" in (ex / "FORMULAS.md").read_text(encoding="utf-8")
    assert '("rofex_min")' in (ex / "taskpane.html").read_text(encoding="utf-8")
