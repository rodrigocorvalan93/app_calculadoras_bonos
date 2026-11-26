"""Fondos — cálculo numérico puro (numpy): períodos, retornos, riesgo y
benchmark compuesto. Sin I/O ni estado: lo usan `services.fondos`, la
atribución y los tests.

Convenciones
- Fechas = `numpy.datetime64[D]` ordenadas ascendente (grilla de RUEDAS: los
  días en que algún fondo movió su cuotaparte).
- Una serie de nivel (VCP, índice) es un vector float alineado a la grilla,
  NaN antes del inicio. El retorno de un período es nivel_fin / nivel_base − 1
  con la base en la ÚLTIMA rueda ≤ la fecha de corte del período.
- El benchmark compuesto replica al legacy (`Delta_Benchmarks.csv`): variación
  diaria = Σ peso × variación del componente; las tasas (Badlar, TAMAR, …)
  devengan TNA / 365 por día CALENDARIO y el spread se suma a la tasa.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

D = "datetime64[D]"
_DIA = np.timedelta64(1, "D")

# (clave, etiqueta corta, etiqueta larga). `dN` = N días corridos hacia atrás.
PERIODOS: List[Tuple[str, str, str]] = [
    ("d1", "Día", "Última rueda"),
    ("d7", "7d", "7 días"),
    ("mtd", "MTD", "Mes en curso"),
    ("d30", "30d", "30 días"),
    ("d90", "90d", "90 días"),
    ("d180", "180d", "180 días"),
    ("ytd", "YTD", "Año en curso"),
    ("d365", "1 año", "12 meses"),
    ("d730", "2 años", "24 meses"),
]
PERIODO_KEYS = tuple(k for k, _, _ in PERIODOS)


def a_fechas(xs: Sequence[Any]) -> np.ndarray:
    return np.asarray(xs, dtype=D)


def idx_hasta(fechas: np.ndarray, corte: Any) -> int:
    """Índice de la última rueda ≤ corte (−1 si no hay)."""
    return int(np.searchsorted(fechas, np.datetime64(corte, "D"), side="right")) - 1


def corte_periodo(fechas: np.ndarray, i_fin: int, periodo: str) -> int:
    """Índice de la rueda BASE del período que termina en `i_fin` (−1 = no hay
    historia). `d1` = la rueda anterior; `mtd` / `ytd` = última rueda del mes /
    año anterior; `dN` = última rueda ≤ fin − N días."""
    if i_fin <= 0:
        return -1
    fin = fechas[i_fin]
    if periodo == "d1":
        return i_fin - 1
    if periodo == "mtd":
        corte = fin.astype("datetime64[M]").astype(D) - _DIA
    elif periodo == "ytd":
        corte = fin.astype("datetime64[Y]").astype(D) - _DIA
    elif periodo.startswith("d") and periodo[1:].isdigit():
        corte = fin - np.timedelta64(int(periodo[1:]), "D")
    else:
        raise ValueError(f"período desconocido: {periodo}")
    i = int(np.searchsorted(fechas, corte, side="right")) - 1
    return i if i < i_fin else i_fin - 1


def ultimo_valido(y: np.ndarray, hasta: Optional[int] = None) -> int:
    """Índice del último valor finito de `y` (hasta `hasta` inclusive); −1 si no hay."""
    n = len(y) if hasta is None else min(len(y), hasta + 1)
    ok = np.flatnonzero(np.isfinite(y[:n]))
    return int(ok[-1]) if len(ok) else -1


def retorno(y: np.ndarray, i0: int, i1: int) -> Optional[float]:
    if i0 < 0 or i1 < 0 or i0 >= len(y) or i1 >= len(y):
        return None
    a, b = y[i0], y[i1]
    if not (np.isfinite(a) and np.isfinite(b)) or a <= 0:
        return None
    return float(b / a - 1.0)


def retornos_periodos(fechas: np.ndarray, y: np.ndarray, i_fin: int,
                      periodos: Sequence[str] = PERIODO_KEYS) -> Dict[str, Optional[float]]:
    """{período: retorno} de la serie de nivel `y` terminando en `i_fin`."""
    out: Dict[str, Optional[float]] = {}
    for p in periodos:
        i0 = corte_periodo(fechas, i_fin, p)
        out[p] = retorno(y, i0, i_fin) if i0 >= 0 else None
    return out


def tna(r: Optional[float], dias: int) -> Optional[float]:
    """Retorno directo → TNA (lineal, base 365)."""
    if r is None or dias <= 0:
        return None
    return float(r * 365.0 / dias)


def anualizar(r: Optional[float], dias: int) -> Optional[float]:
    """Retorno directo → efectiva anual (compuesta, base 365)."""
    if r is None or dias <= 0 or r <= -1.0:
        return None
    return float((1.0 + r) ** (365.0 / dias) - 1.0)


# ── series diarias y riesgo ──────────────────────────────────────────────────
def variaciones(y: np.ndarray) -> np.ndarray:
    """Retorno diario simple, NaN donde falta alguno de los dos niveles."""
    out = np.full(len(y), np.nan)
    if len(y) > 1:
        a, b = y[:-1], y[1:]
        with np.errstate(divide="ignore", invalid="ignore"):
            r = b / a - 1.0
        ok = np.isfinite(a) & np.isfinite(b) & (a > 0)
        out[1:][ok] = r[ok]
    return out


def _dd(y: np.ndarray) -> Tuple[Optional[float], Optional[float]]:
    """(máxima caída, caída actual) desde el pico, sobre los valores finitos."""
    v = y[np.isfinite(y)]
    if len(v) < 2:
        return None, None
    pico = np.maximum.accumulate(v)
    dd = v / pico - 1.0
    return float(dd.min()), float(dd[-1])


def riesgo(fechas: np.ndarray, y: np.ndarray, b: Optional[np.ndarray],
           i0: int, i1: int, ruedas_anio: float = 252.0) -> Dict[str, Any]:
    """Métricas de la ventana [i0, i1] (índices de la grilla, base en i0):
    volatilidad anualizada, máxima caída, mejor / peor rueda y, con benchmark,
    tracking error, information ratio, beta, correlación y % de ruedas arriba."""
    out: Dict[str, Any] = {"n": 0, "vol": None, "max_dd": None, "dd_actual": None,
                           "mejor": None, "peor": None, "te": None, "ir": None,
                           "beta": None, "corr": None, "hit": None, "exceso_anual": None}
    if i0 < 0 or i1 <= i0:
        return out
    ys = y[i0:i1 + 1]
    r = variaciones(ys)[1:]
    ok = np.isfinite(r)
    n = int(ok.sum())
    out["n"] = n
    if n < 2:
        return out
    rr = r[ok]
    raiz = float(np.sqrt(ruedas_anio))
    out["vol"] = float(rr.std(ddof=1) * raiz)
    out["mejor"], out["peor"] = float(rr.max()), float(rr.min())
    out["max_dd"], out["dd_actual"] = _dd(ys)
    if b is None:
        return out
    rb = variaciones(b[i0:i1 + 1])[1:]
    ok2 = ok & np.isfinite(rb)
    m = int(ok2.sum())
    if m < 2:
        return out
    f, g = r[ok2], rb[ok2]
    ex = f - g
    te = float(ex.std(ddof=1) * raiz)
    out["te"] = te
    out["hit"] = float((ex > 0).mean())
    out["exceso_anual"] = float(ex.mean() * ruedas_anio)
    if te > 1e-12:
        out["ir"] = float(ex.mean() * ruedas_anio / te)
    vg = float(g.var(ddof=1))
    if vg > 1e-18:
        out["beta"] = float(np.cov(f, g, ddof=1)[0, 1] / vg)
        sf = float(f.std(ddof=1))
        if sf > 1e-12:
            out["corr"] = float(np.corrcoef(f, g)[0, 1])
    return out


def mensuales(fechas: np.ndarray, y: np.ndarray, i_fin: int, meses: int = 13
              ) -> List[Tuple[str, Optional[float]]]:
    """[(AAAA-MM, retorno del mes)] de los últimos `meses` meses hasta `i_fin`
    (el último es el mes en curso, parcial). Base = última rueda del mes anterior."""
    if i_fin < 0:
        return []
    ms = fechas[: i_fin + 1].astype("datetime64[M]")
    # último índice de cada mes
    corte = np.flatnonzero(ms[1:] != ms[:-1])
    fines = np.append(corte, i_fin)
    out: List[Tuple[str, Optional[float]]] = []
    for k in range(max(1, len(fines) - meses), len(fines)):
        out.append((str(ms[fines[k]]), retorno(y, int(fines[k - 1]), int(fines[k]))))
    if len(fines) <= meses and len(fines):
        # primer mes de la serie: desde el primer dato del mes
        i_ini = ultimo_valido_desde(y, 0)
        if 0 <= i_ini < fines[0]:
            out.insert(0, (str(ms[fines[0]]), retorno(y, i_ini, int(fines[0]))))
    return out


def ultimo_valido_desde(y: np.ndarray, desde: int) -> int:
    """Primer índice ≥ `desde` con valor finito (−1 si no hay)."""
    ok = np.flatnonzero(np.isfinite(y[desde:]))
    return int(ok[0]) + desde if len(ok) else -1


def base100(y: np.ndarray, i0: int, i1: int) -> np.ndarray:
    """Tramo [i0, i1] rebasado a 100 en el primer valor finito."""
    ys = np.array(y[i0:i1 + 1], dtype=float)
    k = ultimo_valido_desde(ys, 0)
    if k < 0 or ys[k] <= 0:
        return np.full(len(ys), np.nan)
    return ys / ys[k] * 100.0


# ── flujos (suscripciones netas estimadas) ───────────────────────────────────
def flujos_netos(pn: np.ndarray, vcp: np.ndarray) -> np.ndarray:
    """Suscripciones netas del día t ≈ PN_t − PN_{t−1} × (VCP_t / VCP_{t−1}):
    lo que el patrimonio cambió y la cuotaparte no explica. NaN sin datos."""
    out = np.full(len(pn), np.nan)
    if len(pn) > 1:
        r = variaciones(vcp)[1:]
        a, b = pn[:-1], pn[1:]
        ok = np.isfinite(r) & np.isfinite(a) & np.isfinite(b)
        out[1:][ok] = b[ok] - a[ok] * (1.0 + r[ok])
    return out


# ── benchmark compuesto ──────────────────────────────────────────────────────
def _a_calendario(f: np.ndarray, v: np.ndarray, cal: np.ndarray) -> np.ndarray:
    """Serie (f, v) llevada a la grilla calendario `cal` con el último valor
    conocido (ffill); NaN antes del primer dato y más de 10 días después del
    último (una serie que dejó de actualizarse no se estira para siempre)."""
    if not len(f):
        return np.full(len(cal), np.nan)
    i = np.searchsorted(f, cal, side="right") - 1
    out = np.where(i >= 0, v[np.clip(i, 0, len(v) - 1)], np.nan).astype(float)
    viejo = cal > (f[-1] + np.timedelta64(10, "D"))
    out[viejo] = np.nan
    return out


def benchmark_var_calendario(cal: np.ndarray,
                             niveles: Dict[str, Tuple[np.ndarray, np.ndarray, float]],
                             tasas: Dict[str, Tuple[np.ndarray, np.ndarray, float]],
                             spread: float = 0.0) -> np.ndarray:
    """Variación diaria del benchmark sobre la grilla CALENDARIO `cal`
    (consecutiva): Σ peso × (nivel_t / nivel_{t−1} − 1) + Σ peso × TNA_t / 365
    + spread / 365. `niveles` / `tasas` = {clave: (fechas, valores, peso)};
    las tasas vienen en % TNA. NaN el día en que falte algún componente (no se
    arma un benchmark con una pata menos)."""
    n = len(cal)
    var = np.zeros(n)
    falta = np.zeros(n, dtype=bool)
    for f, v, w in niveles.values():
        if not w:
            continue
        y = _a_calendario(f, v, cal)
        r = variaciones(y)
        falta |= ~np.isfinite(r)
        var += w * np.where(np.isfinite(r), r, 0.0)
    hay_tasa = False
    for f, v, w in tasas.values():
        if not w:
            continue
        hay_tasa = True
        y = _a_calendario(f, v, cal)
        falta |= ~np.isfinite(y)
        var += w * np.where(np.isfinite(y), y, 0.0) / 36500.0
    if spread:
        var += spread / 365.0
    if n:
        # el primer día no tiene variación de nivel: sin niveles, sí devenga tasa
        if any(w for _, _, w in niveles.values()):
            falta[0] = True
        elif not hay_tasa and not spread:
            falta[:] = True
    var[falta] = np.nan
    return var


def indice_desde_var(var: np.ndarray, base: float = 1.0) -> np.ndarray:
    """Índice acumulado desde variaciones diarias; arranca en `base` el día
    ANTERIOR al primer dato finito y queda NaN desde el primer hueco interior
    (un benchmark no se encadena a través de días sin dato)."""
    out = np.full(len(var), np.nan)
    ok = np.isfinite(var)
    if not ok.any():
        return out
    i0 = int(np.flatnonzero(ok)[0])
    huecos = np.flatnonzero(~ok[i0:])
    i1 = (i0 + int(huecos[0])) if len(huecos) else len(var)
    out[i0:i1] = base * np.cumprod(1.0 + var[i0:i1])
    if i0 > 0:
        out[i0 - 1] = base
    return out


def encadenar(viejo: np.ndarray, nuevo: np.ndarray) -> np.ndarray:
    """Une dos índices sobre la MISMA grilla: `viejo` manda donde tiene dato y
    `nuevo` sigue desde el último dato de `viejo`, re-escalado para empalmar en
    esa fecha (si `nuevo` no tiene dato ahí, no hay empalme: queda `viejo`)."""
    out = np.array(viejo, dtype=float)
    k = ultimo_valido(viejo)
    if k < 0:
        return np.array(nuevo, dtype=float)
    if k >= len(nuevo) - 1 or not np.isfinite(nuevo[k]) or nuevo[k] <= 0:
        return out
    out[k + 1:] = nuevo[k + 1:] * (viejo[k] / nuevo[k])
    return out


# ── ranking contra pares ─────────────────────────────────────────────────────
def percentil(valor: Optional[float], grupo: Sequence[Optional[float]]) -> Optional[Tuple[int, int, float]]:
    """(puesto 1 = mejor, total, percentil 0–100 con 100 = mejor) de `valor`
    dentro de `grupo` (incluye al propio fondo). None si no hay con qué comparar."""
    if valor is None:
        return None
    v = np.array([x for x in grupo if x is not None and np.isfinite(x)], dtype=float)
    if len(v) < 2:
        return None
    puesto = int((v > valor + 1e-12).sum()) + 1
    return puesto, int(len(v)), float(100.0 * (len(v) - puesto) / (len(v) - 1))
