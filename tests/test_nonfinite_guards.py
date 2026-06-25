"""Guardas de no-finitos en los cálculos de tasa: una TIR ≤ −100% hace que
`(1+y)**fraccional` devuelva un número COMPLEJO (Python no lanza excepción), que
después revienta `json.dumps` (/graficos/data) o el render (comparador). Cubre
nss._tna/estimate, comparador._forward_implicit y curves._forwards_matrix.
"""
from __future__ import annotations

from backend.routes.comparador import _forward_implicit
from backend.routes.curves import _forwards_matrix
from backend.services import nss


def test_nss_tna_guards_negative_base():
    assert nss._tna(-1.5, 90, 365) is None      # base negativa → sería complejo
    assert nss._tna(-1.0, 90, 365) is None       # base 0
    assert nss._tna(float("nan"), 90, 365) is None
    assert isinstance(nss._tna(0.5, 90, 365), float)


def test_forward_implicit_guards_sub_minus_100():
    bad = _forward_implicit({"code": "A", "tirea": -1.5, "duration": 1.0},
                            {"code": "B", "tirea": 0.10, "duration": 2.0})
    assert bad is None
    ok = _forward_implicit({"code": "A", "tirea": 0.08, "duration": 1.0},
                           {"code": "B", "tirea": 0.10, "duration": 2.0})
    assert ok is not None and isinstance(ok["fwd"], float)


def test_forwards_matrix_excludes_sub_minus_100():
    rows = [{"code": "A", "tirea": 0.08, "duration": 1.0},
            {"code": "B", "tirea": 0.10, "duration": 2.0},
            {"code": "BAD", "tirea": -1.5, "duration": 3.0}]
    m = _forwards_matrix(rows)          # si entrara un complejo, min/max() reventaría acá
    codes = {r["code"] for r in m["rows"]}
    assert "BAD" not in codes and {"A", "B"} <= codes
    assert m["n"] == 2
