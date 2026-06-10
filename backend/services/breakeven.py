"""Break-even inflation — método de Fisher (no iterativo).

Compara la curva CER (TIREA **real**) contra la curva de tasa fija / LECAP
(TIREA **nominal**) y despeja la inflación implícita por paridad de Fisher:

    1 + i_nominal = (1 + i_real) · (1 + i_breakeven)
    ⇒  BE_anual = (1 + TIR_nom) / (1 + TIR_real) − 1
       BE_TEM   = (1 + BE_anual) ** (30/360) − 1     # tasa efectiva mensual

Para cada bono CER se toma la TIREA nominal **a su misma duration**,
interpolada linealmente sobre la curva LECAP (clamp en los extremos → marcado
como extrapolado). Es la versión rápida/robusta: NO itera ni toca las
proyecciones de inflación. Reusa las TIREAs ya cacheadas por el motor de
curvas, así que el costo extra es aritmética trivial.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# Filtramos TIREAs absurdas (errores de escala de precio) igual que el histórico:
# real plausible entre -90% y +200%.
_TIR_MIN, _TIR_MAX = -0.90, 2.0


def _clean_points(rows: List[Dict[str, Any]]) -> List[Tuple[float, float, str]]:
    """(duration, tirea, code) de las filas con duration>0 y TIREA finita/plausible."""
    out: List[Tuple[float, float, str]] = []
    for r in rows:
        d, t = r.get("duration"), r.get("tirea")
        if d is None or t is None or d != d or t != t:   # None / NaN
            continue
        if d <= 0 or not (_TIR_MIN < t < _TIR_MAX):
            continue
        out.append((float(d), float(t), r.get("code", "")))
    out.sort(key=lambda p: p[0])
    return out


def _interp(pts: List[Tuple[float, float, str]], x: float) -> Tuple[Optional[float], bool]:
    """TIREA nominal a la duration `x` por interpolación lineal sobre `pts`
    (ordenados por duration). Devuelve (valor, extrapolado?). Clamp en los
    extremos: fuera del rango usa el punto del borde y marca extrapolado."""
    if not pts:
        return None, False
    if x <= pts[0][0]:
        return pts[0][1], x < pts[0][0]
    if x >= pts[-1][0]:
        return pts[-1][1], x > pts[-1][0]
    for i in range(1, len(pts)):
        x1, y1 = pts[i][0], pts[i][1]
        if x <= x1:
            x0, y0 = pts[i - 1][0], pts[i - 1][1]
            t = (x - x0) / (x1 - x0) if x1 > x0 else 0.0
            return y0 + t * (y1 - y0), False
    return pts[-1][1], True


def compute_fisher(cer_rows: List[Dict[str, Any]],
                   lecap_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Tabla break-even por bono CER + resumen. Todo en fracción (0.07 = 7%)."""
    lecap = _clean_points(lecap_rows)
    cer = _clean_points(cer_rows)
    rows: List[Dict[str, Any]] = []
    bes: List[float] = []
    for dur, tir_real, code in cer:
        tir_nom, extrap = _interp(lecap, dur)
        be_anual = be_tem = None
        if tir_nom is not None and (1.0 + tir_real) != 0.0:
            be_anual = (1.0 + tir_nom) / (1.0 + tir_real) - 1.0
            be_tem = (1.0 + be_anual) ** (30.0 / 360.0) - 1.0
            bes.append(be_anual)
        rows.append({
            "code": code, "duration": dur,
            "tirea_real": tir_real, "tirea_nom": tir_nom,
            "be_anual": be_anual, "be_tem": be_tem, "extrapolado": extrap,
        })
    rows.sort(key=lambda r: r["duration"])
    resumen = None
    if bes:
        avg = sum(bes) / len(bes)
        resumen = {
            "n": len(bes),
            "be_anual_prom": avg,
            "be_tem_prom": (1.0 + avg) ** (30.0 / 360.0) - 1.0,
            "be_anual_min": min(bes), "be_anual_max": max(bes),
        }
    return {
        "rows": rows, "resumen": resumen,
        "n_cer": len(cer), "n_lecap": len(lecap),
    }
