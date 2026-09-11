"""La duration de compute_metrics sale de los cashflows YA generados por
calcula_tirea/calcula_precio (misma fórmula que Bono.calcula_duration, sin la
3ª generación de flujos por cálculo). Tiene que ser IDÉNTICA a la del método
para toda clase de ficha: LECAP, CER, hard-dollar, TAMAR."""
from __future__ import annotations

import math

import pytest

from backend.services import bond_universe, curves, pricing


def _muestra():
    bond_universe.ensure_loaded()
    cc = curves.build_curve_codes()
    out = []
    for key in ("lecap", "cer", "globales", "tamar", "corp_hdmep", "dolarlinked"):
        codes = cc.get(key) or []
        if codes:
            out.append(codes[0])
    return out


@pytest.mark.parametrize("code", _muestra())
def test_duration_identica_a_calcula_duration(code: str) -> None:
    settle = pricing.settlement_date_str("24hs")
    m = pricing.compute_metrics(code, "precio", 100.0, settle=settle)
    if m.get("error") or not math.isfinite(m.get("tirea", float("nan"))):
        pytest.skip(f"{code}: sin métricas a precio 100 ({m.get('error')})")
    obj = pricing._bond_obj_copy(code)
    ref = float(obj.calcula_duration(m["tirea"], settle))
    assert m["duration"] == pytest.approx(ref, abs=1e-12), code
