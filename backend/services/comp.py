"""Históricos · COMP — evolución de varios activos en un mismo gráfico, al
estilo COMP de Bloomberg: cada serie rebasada a 100 en su primera rueda con
dato del rango (o variación %, o nivel), alineadas a la unión de ruedas, con
cuadro de inicio / fin / variación / máximo / mínimo / caída desde el máximo /
vol anualizada por activo.

Fuentes: las mismas del price action (`price_action.serie_de`): acciones /
CEDEARs / Merval del parquet de acciones; bonos del cierre completo
(`cierres`, matriz numpy) con fallback a la base px/tasas. ÷ FX opcional
(A3500 / CCL / MEP del mismo día, con el forward-fill acotado de
`price_action._alinear`). Todo numpy sobre datos que ya están en memoria
(los caches por firma de cada fuente se rearman 1×/día): ~1-3 ms para 10
activos × 500 ruedas. Acá no se lee ningún archivo.
"""
from __future__ import annotations

import bisect
import math
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from backend.services import price_action as pa

MAX_TICKERS = 10
# Días calendario hacia atrás desde `hasta`; None = sin tope ("ytd" = 1/1 del
# año de `hasta`, "todo" = toda la historia guardada).
RANGOS: Dict[str, Optional[int]] = {"1m": 31, "3m": 92, "6m": 183, "ytd": None, "1a": 365, "2a": 731, "todo": None}
RANGOS_LABEL = {"1m": "1M", "3m": "3M", "6m": "6M", "ytd": "YTD", "1a": "1A", "2a": "2A", "todo": "Todo"}
MODOS = {"base": "Base 100", "pct": "Variación %", "nivel": "Nivel"}
FUENTES = {"acciones": "Acciones", "cierres": "Cierre completo", "base": "Base px/tasas"}
_RUEDAS_ANUAL = 252
# Misma paleta que charts.js (palette()): el punto de color de la tabla y la
# línea del gráfico salen del mismo `color` del payload.
PALETA = ["#e74c3c", "#3498db", "#2ecc71", "#f39c12", "#9b59b6", "#1abc9c",
          "#e67e22", "#16a085", "#fd79a8", "#00b894", "#0984e3", "#fdcb6e",
          "#6c5ce7", "#d63031", "#00cec9", "#a78bfa", "#e84393", "#55efc4"]
_DEFAULTS = (("GGAL", "YPFD", "MERVAL"), ("AL30D", "GD30C", "TX26"))


def parse_tickers(texto: str) -> List[str]:
    """'GGAL, al30d TX26 ggal' → ['GGAL', 'al30d', 'TX26']: separadores espacio /
    coma / punto y coma, sin repetidos (sin distinguir mayúsculas), tope
    MAX_TICKERS. Se respeta el caso tipeado: los códigos de calc proyectados
    llevan `j` minúscula (TX26j) y `serie_de` prueba tal cual y en mayúsculas."""
    out: List[str] = []
    vistos: set = set()
    for tok in re.split(r"[\s,;]+", texto or ""):
        tok = tok.strip()
        if not tok:
            continue
        k = tok.upper()
        if k in vistos:
            continue
        vistos.add(k)
        out.append(tok)
        if len(out) >= MAX_TICKERS:
            break
    return out


def default_tickers(names: Sequence[str]) -> List[str]:
    """Qué comparar cuando el usuario todavía no eligió: acciones líderes +
    Merval si hay historia de acciones, si no soberanos; si no, los dos
    primeros con historia."""
    s = set(names)
    for grupo in _DEFAULTS:
        sel = [t for t in grupo if t in s]
        if len(sel) >= 2:
            return sel
    return list(names[:2])


def _epoch(iso: str) -> int:
    """Medianoche UTC del día (uPlot dibuja con tzDate UTC en charts.js)."""
    return int(datetime.fromisoformat(iso[:10]).replace(tzinfo=timezone.utc).timestamp())


def _lim(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f, 6) if math.isfinite(f) else None


def _desde_por_rango(rango: str, hasta: str) -> Optional[str]:
    h = date.fromisoformat(hasta)
    if rango == "ytd":
        return date(h.year, 1, 1).isoformat()
    dias = RANGOS.get(rango)
    return (h - timedelta(days=dias)).isoformat() if dias else None


def _stats(f: List[str], v: np.ndarray, es_tir: bool) -> Dict[str, Any]:
    """Cuadro del rango sobre la serie YA recortada y sin huecos (nivel en la
    unidad de la serie: precio, precio ÷ FX o TIR en %)."""
    v0, v1 = float(v[0]), float(v[-1])
    imax, imin = int(np.argmax(v)), int(np.argmin(v))
    out: Dict[str, Any] = {
        "desde": f[0], "hasta": f[-1], "n": int(len(v)),
        "inicio": _lim(v0), "fin": _lim(v1),
        "max": _lim(v[imax]), "max_fecha": f[imax], "min": _lim(v[imin]), "min_fecha": f[imin],
        "var_pct": None, "delta_pp": None, "dd_pct": None, "vol_anual": None,
    }
    if es_tir:
        out["delta_pp"] = _lim(v1 - v0)
        return out
    out["var_pct"] = _lim((v1 / v0 - 1.0) * 100.0) if v0 else None
    vmax = float(v[imax])
    out["dd_pct"] = _lim((v1 / vmax - 1.0) * 100.0) if vmax else None
    if len(v) > 3:
        r = np.diff(np.log(v))
        out["vol_anual"] = _lim(float(np.std(r, ddof=1)) * math.sqrt(_RUEDAS_ANUAL) * 100.0)
    return out


def comparar(tickers: Sequence[str], campo: str = "precio", base: str = "ars", modo: str = "base",
             rango: str = "6m", desde: Optional[str] = None, hasta: Optional[str] = None) -> Dict[str, Any]:
    """Payload del COMP: `x` (epoch UTC por rueda de la unión), `series`
    ([{ticker, fuente, color, y (alineada, null en los huecos), stats}]),
    `faltantes` (sin historia guardada) y `sin_rango` (con historia pero no en
    el rango). `desde`/`hasta` mandan sobre `rango`; `hasta` default = última
    rueda con dato entre las series. TIR → modo nivel, en %, sin ÷ FX."""
    es_tir = campo == "tir"
    campo = "tir" if es_tir else "precio"
    modo = "nivel" if es_tir else (modo if modo in MODOS else "base")
    base = base if (base in pa.BASES and not es_tir) else "ars"
    rango = rango if rango in RANGOS else "6m"
    out: Dict[str, Any] = {"ok": False, "campo": campo, "modo": modo, "modo_label": MODOS[modo],
                           "base": base, "base_label": pa.BASES[base], "rango": rango,
                           "desde": desde, "hasta": hasta, "x": [], "fechas": [], "n": 0,
                           "series": [], "faltantes": [], "sin_rango": []}
    crudas: List[Dict[str, Any]] = []
    for t in tickers:
        try:
            s = pa.serie_de(t, campo)
        except Exception:  # noqa: BLE001 — una fuente rota no tapa a las demás
            s = None
        if not s or len(s.get("fechas") or []) < 2:
            out["faltantes"].append(t)
            continue
        s = dict(s)
        s.setdefault("ticker", str(t).upper())
        crudas.append(s)
    if not crudas:
        return out

    fin = hasta or max(s["fechas"][-1] for s in crudas)
    ini = desde if (desde or hasta) else _desde_por_rango(rango, fin)
    fx = pa.fx_por_fecha(base) if base != "ars" else {}
    recortadas: List[tuple] = []
    for s in crudas:
        f = list(s["fechas"])
        v = np.asarray(s["ultimo"], dtype=float)          # copia: los arrays de las fuentes son compartidos
        if fx:
            al = pa._alinear(f, fx)
            v = np.array([x / q if (q is not None and q > 0) else np.nan for x, q in zip(v, al)], dtype=float)
        i0 = bisect.bisect_left(f, ini) if ini else 0
        i1 = bisect.bisect_right(f, fin)
        f, v = f[i0:i1], v[i0:i1]
        ok = np.isfinite(v) if es_tir else (np.isfinite(v) & (v > 0))
        if int(ok.sum()) < 2:
            out["sin_rango"].append(s["ticker"])
            continue
        recortadas.append((s, [x for x, o in zip(f, ok) if o], v[ok]))
    if not recortadas:
        out.update(desde=ini, hasta=fin)
        return out

    fechas = sorted({x for _, f, _ in recortadas for x in f})
    idx = {x: i for i, x in enumerate(fechas)}
    series: List[Dict[str, Any]] = []
    for k, (s, f, v) in enumerate(recortadas):
        y = np.full(len(fechas), np.nan)
        y[[idx[d] for d in f]] = v
        v0 = float(v[0])
        if modo == "base":
            y = y / v0 * 100.0
        elif modo == "pct":
            y = (y / v0 - 1.0) * 100.0
        fuente = s.get("fuente") or ""
        series.append({
            "ticker": s["ticker"], "fuente": fuente, "fuente_label": FUENTES.get(fuente, fuente or "—"),
            "panel": s.get("panel") or "", "color": PALETA[k % len(PALETA)],
            "y": [_lim(x) for x in y], "stats": _stats(f, v, es_tir),
        })
    out.update(ok=True, desde=fechas[0], hasta=fechas[-1], fechas=fechas, n=len(fechas),
               x=[_epoch(d) for d in fechas], series=series)
    return out
