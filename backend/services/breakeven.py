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

_MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def mes_referencia(venc, lag_habiles=-10) -> Optional[str]:
    """Último mes de inflación que el break-even del bono CER realmente captura.

    Metodología INDEC/CER: el bono fija su CER `lag` días HÁBILES antes del
    vencimiento (lag de la especie, típ. −10). El CER de un día D incorpora la
    inflación del mes M según la regla de publicación: entre el 16 de X y el
    15 de X+1, el CER devenga la inflación de X−1 (el dato de mayo sale ~11/6
    y corre en el CER del 16/6 al 15/7). Entonces:
        fix = venc + lag hábiles
        mes_ref = fix.month − 1  si fix.day ≥ 16   (año ajustado)
                  fix.month − 2  si fix.day ≤ 15
    Ej.: TZXO6 vence 31/10/26 → fix 19/10 → BE captura inflación HASTA sep-26
    (no "fines de octubre"). Devuelve 'sep-26' o None si no se puede calcular.
    """
    if venc is None:
        return None
    try:
        from dias_habiles import n_dias_laborales
        f = n_dias_laborales(venc, int(lag_habiles or -10))
    except Exception:  # noqa: BLE001 — sin módulo de feriados: aprox 5/7
        from datetime import timedelta
        f = venc + timedelta(days=round(int(lag_habiles or -10) * 7 / 5))
    m = f.month - (1 if f.day >= 16 else 2)
    y = f.year
    while m <= 0:
        m += 12
        y -= 1
    return f"{_MESES[m - 1]}-{str(y)[2:]}"


def _clean_points(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filas limpias (duration>0, TIREA finita/plausible) como dicts ordenados
    por duration; conserva vencimiento/lag para el mes de referencia."""
    out: List[Dict[str, Any]] = []
    for r in rows:
        d, t = r.get("duration"), r.get("tirea")
        if d is None or t is None or d != d or t != t:   # None / NaN
            continue
        if d <= 0 or not (_TIR_MIN < t < _TIR_MAX):
            continue
        out.append({"d": float(d), "t": float(t), "code": r.get("code", ""),
                    "venc": r.get("vencimiento"), "lag": r.get("lag")})
    out.sort(key=lambda p: p["d"])
    return out


def _interp(pts: List[Tuple[float, float, str]], x: float) -> Tuple[Optional[float], bool]:
    """TIREA nominal a la duration `x` por interpolación lineal sobre `pts`
    (ordenados por duration). Devuelve (valor, extrapolado?). Clamp en los
    extremos: fuera del rango usa el punto del borde y marca extrapolado."""
    if not pts:
        return None, False
    if x <= pts[0]["d"]:
        return pts[0]["t"], x < pts[0]["d"]
    if x >= pts[-1]["d"]:
        return pts[-1]["t"], x > pts[-1]["d"]
    for i in range(1, len(pts)):
        x1, y1 = pts[i]["d"], pts[i]["t"]
        if x <= x1:
            x0, y0 = pts[i - 1]["d"], pts[i - 1]["t"]
            t = (x - x0) / (x1 - x0) if x1 > x0 else 0.0
            return y0 + t * (y1 - y0), False
    return pts[-1]["t"], True


def compute_fisher(cer_rows: List[Dict[str, Any]],
                   lecap_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Tabla break-even por bono CER + resumen. Todo en fracción (0.07 = 7%)."""
    lecap = _clean_points(lecap_rows)
    cer = _clean_points(cer_rows)

    def _pair(venc):
        """Letra de tasa fija con vencimiento más cercano (±45 días) — el par
        natural del usuario (TZXO6 ↔ S30O6): mismos cashflows en fecha, mismo
        horizonte. Si no hay match cercano, se cae a la interpolación."""
        if venc is None:
            return None
        best, bd = None, 46
        for q in lecap:
            if q.get("venc") is None:
                continue
            d = abs((q["venc"] - venc).days)
            if d < bd:
                best, bd = q, d
        return best

    rows: List[Dict[str, Any]] = []
    bes: List[float] = []
    for p in cer:
        dur, tir_real, code = p["d"], p["t"], p["code"]
        par = _pair(p.get("venc"))
        if par is not None:
            tir_nom, extrap = par["t"], False
        else:
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
            "par": par["code"] if par is not None else None,
            "mes_ref": mes_referencia(p.get("venc"), p.get("lag")),
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
