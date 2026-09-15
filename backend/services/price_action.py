"""Price action de acciones / CEDEARs / Merval para Históricos.

Serie diaria de cierres (Delta - historico_acciones, la escribe el autosave
del cierre) → nivel en ARS o dividido por A3500 / CCL / MEP (series diarias
del mismo cierre y del BCRA), retornos diarios, canal de tendencia (regresión
lineal ± 1σ / ± 2σ de residuos — el "rango de tendencia" del histórico de
forwards, pero sobre precio), mín / máx, percentil y z del último, distribución
(histograma vs la normal con la misma μ/σ) y comparación contra el Merval
(β, correlación, retorno relativo, overlay rebasado al nivel inicial).

Costo: numpy sobre ≤ ~1.500 puntos por request (≈ 1 ms) + geometría SVG en
Python; el HTML final lo cachea la ruta por (parámetros, mtime de los
archivos), así el warm es un lookup. Nada de esto corre en el tick de mercado.
"""
from __future__ import annotations

import bisect
import math
from datetime import date
from typing import Any, Dict, List, Optional

import numpy as np

BASES = {"ars": "ARS", "a3500": "÷ A3500", "ccl": "÷ CCL", "mep": "÷ MEP"}
VENTANAS = {"30": 30, "60": 60, "90": 90, "180": 180, "365": 365, "todo": 0}
MERVAL = "MERVAL"
_MIN_CMP = 10                # puntos comunes mínimos para β / correlación
_MAX_GAP_FX = 10             # días calendario máximos de forward-fill del FX
_RUEDAS_ANUAL = 252
_W, _H = 880, 300            # gráfico principal (viewBox)
_WH = 300                    # histograma lateral


# ── FX para dividir la serie ──────────────────────────────────────────────
def fx_por_fecha(base: str) -> Dict[str, float]:
    """{fecha ISO: fx} de la base elegida. A3500 desde la serie del BCRA
    (larga) con fallback al archivo FX del cierre; CCL / MEP sólo del archivo
    FX (arrancan cuando arrancó el cierre diario)."""
    if base == "a3500":
        try:
            from backend.services import historico
            pts = (historico.series_points("a3500") or {}).get("points") or []
            d = {str(p[0]): float(p[1]) for p in pts if p[1] is not None and float(p[1]) > 0}
            if d:
                return d
        except Exception:  # noqa: BLE001 — sin BCRA cae al archivo FX
            pass
        col = "oficial_a3500"
    elif base in ("ccl", "mep"):
        col = base
    else:
        return {}
    from backend.services import fx_hist
    return fx_hist.columna(col)


def _alinear(fechas: List[str], fx: Dict[str, float]) -> List[Optional[float]]:
    """FX por fecha con forward-fill acotado (el archivo FX puede tener
    huecos); None si no hay dato reciente para esa fecha."""
    keys = sorted(fx)
    out: List[Optional[float]] = []
    for f in fechas:
        i = bisect.bisect_right(keys, f)
        if not i:
            out.append(None)
            continue
        k = keys[i - 1]
        try:
            gap = (date.fromisoformat(f) - date.fromisoformat(k)).days
        except ValueError:
            gap = 0
        out.append(fx[k] if gap <= _MAX_GAP_FX else None)
    return out


# ── Estadística ───────────────────────────────────────────────────────────
def serie_de(ticker: str, campo: str = "precio") -> Optional[Dict[str, Any]]:
    """Serie diaria de `ticker` según lo que haya guardado:
      - acciones / CEDEARs / Merval → parquet de acciones (precio);
      - bonos con ficha → cierre completo (services/cierres: precio de pantalla
        o TIREA) con fallback a la base px/tasas (historico_byma), que tiene
        un año de historia. Los códigos proyectados (`…j`) van por la base
        (el cierre completo guarda las métricas de la variante base).
    {"fechas", "ultimo" (ndarray), "volumen", "panel", "fuente"}; la TIR sale
    en % (×100). None si no hay nada."""
    from backend.services import acciones_hist as ah

    raw = (ticker or "").strip()
    if not raw:
        return None
    es_tir = campo == "tir"
    if not es_tir:
        s = ah.serie(raw.upper())
        if s:
            return {**s, "fuente": "acciones"}
    from backend.services import cierres, historico_byma as hb, pricing
    from backend.services import symbols as syms

    # Códigos de calc con sufijo `j`/`v` MINÚSCULA (TX26j): el ticker se
    # respeta tal cual y recién después se prueba en mayúsculas.
    t = next((c for c in (raw, raw.upper()) if pricing.bond_meta(c)), None)
    if t is None:
        return None
    k = 100.0 if es_tir else 1.0
    proy = t.endswith("j")

    def _cierres():
        sym = syms.md_symbol(t, "24hs")
        m = cierres.ensure_loaded()            # corre en el executor de la ruta
        if m is None:
            return None
        f, v = cierres.serie(sym, "tirea" if es_tir else "last")
        if len(f) < 2:
            return None
        vol = None
        j = m.idx_s.get(sym) if not es_tir else None
        if j is not None and "nominal" in m.mat:
            vol = np.array([m.mat["nominal"][m.idx_f[x], j] for x in f], dtype=float)
        return {"fechas": f, "ultimo": np.asarray(v, dtype=float) * k, "volumen": vol,
                "panel": "B", "fuente": "cierres"}

    def _base():
        f, v = hb.serie_codigo(t, "TIREA" if es_tir else "Last Price")
        if len(f) < 2:
            return None
        return {"fechas": f, "ultimo": np.asarray(v, dtype=float) * k, "volumen": None,
                "panel": "B", "fuente": "base"}

    for fn in ((_base, _cierres) if (es_tir and proy) else (_cierres, _base)):
        try:
            s = fn()
        except Exception:  # noqa: BLE001 — una fuente rota no tapa la otra
            s = None
        if s:
            s["ticker"] = t
            return s
    return None


def _percentil(v: np.ndarray, x: float) -> float:
    return float((np.sum(v < x) + 0.5 * np.sum(v == x)) / len(v))


def _es_ruido(x: float, ref: float) -> bool:
    """True si |x| es ruido de punto flotante frente a |ref|. Una serie plana
    (precio que no operó en toda la ventana, TIR fija) deja residuos de
    ~1e-14 en el ajuste lineal: no son un σ ni un rango — tratarlos como
    tales daba z-scores absurdos y un eje sin ancho (loop infinito en los
    ticks con numpy 2.5)."""
    return not (abs(float(x)) > abs(float(ref)) * 1e-9)


def _momentos(v: np.ndarray):
    """(asimetría, curtosis en exceso) — None con menos de 3 datos o σ = 0."""
    n = len(v)
    if n < 3:
        return None, None
    s = float(v.std(ddof=0))
    if s <= 0:
        return 0.0, 0.0
    z = (v - v.mean()) / s
    return float((z ** 3).mean()), float((z ** 4).mean() - 3.0)


def _stats_nivel(f: List[str], y: np.ndarray, es_tir: bool = False) -> Dict[str, Any]:
    """Estadística del nivel. Con `es_tir` el nivel es una tasa en %: las
    variaciones van en puntos porcentuales (Δ, pendiente en pp/rueda) y no
    hay drawdown."""
    n = len(y)
    last, media = float(y[-1]), float(y.mean())
    desv = float(y.std(ddof=1)) if n > 1 else 0.0
    if _es_ruido(desv, media):
        desv = 0.0
    imin, imax = int(y.argmin()), int(y.argmax())
    vmin, vmax = float(y[imin]), float(y[imax])
    x = np.arange(n, dtype=float)
    slope, intercept = np.polyfit(x, y, 1)
    tend = intercept + slope * x
    resid = y - tend
    sigma = float(resid.std(ddof=2)) if n > 2 else 0.0
    if _es_ruido(sigma, media):
        sigma = 0.0
    ss_tot = float(((y - media) ** 2).sum()) if desv > 0 else 0.0
    if es_tir:
        pend_pct: Optional[float] = float(slope)
        ret_ventana = last - float(y[0])
        mdd: Optional[float] = None
    else:
        pend_pct = (float(slope) / float(tend[-1]) * 100.0) if tend[-1] else None
        ret_ventana = (last / float(y[0]) - 1.0) * 100.0
        peak = np.maximum.accumulate(y)
        mdd = float(((y / peak) - 1.0).min() * 100.0)
    return {
        "ultimo": last, "media": media, "desvio": desv,
        "min": vmin, "min_fecha": f[imin], "max": vmax, "max_fecha": f[imax],
        "percentil": _percentil(y, last), "z": ((last - media) / desv) if desv > 0 else None,
        "pos_rango": ((last - vmin) / (vmax - vmin)) if vmax > vmin else None,
        "ret_ventana": ret_ventana,
        "mdd": mdd,
        "tend_ultimo": float(tend[-1]), "sigma_tend": sigma,
        "z_tend": ((last - float(tend[-1])) / sigma) if sigma > 0 else None,
        "pend_pct": pend_pct,
        "pend_anual": (pend_pct * _RUEDAS_ANUAL) if pend_pct is not None else None,
        "r2": (1.0 - float((resid ** 2).sum()) / ss_tot) if ss_tot > 0 else None,
        "_tend": tend,
    }


def _stats_retornos(r_f: List[str], r: np.ndarray) -> Dict[str, Any]:
    m = len(r)
    if m == 0:
        return {"n": 0, "media": None, "desvio": 0.0, "vol_anual": None, "skew": None,
                "kurt": None, "min": None, "max": None, "pos_pct": None, "ultimo": None,
                "z_ultimo": None, "percentil_ultimo": None}
    media = float(r.mean())
    desv = float(r.std(ddof=1)) if m > 1 else 0.0
    if _es_ruido(desv, max(abs(media), float(np.abs(r).max()))):
        desv = 0.0
    imin, imax = int(r.argmin()), int(r.argmax())
    skew, kurt = _momentos(r) if desv > 0 else (None, None)
    last = float(r[-1])
    return {"n": m, "media": media, "desvio": desv,
            "vol_anual": (desv * math.sqrt(_RUEDAS_ANUAL)) if desv > 0 else None,
            "skew": skew, "kurt": kurt,
            "min": float(r[imin]), "min_fecha": r_f[imin], "max": float(r[imax]), "max_fecha": r_f[imax],
            "pos_pct": float((r > 0).mean() * 100.0), "ultimo": last, "ultimo_fecha": r_f[-1],
            "z_ultimo": ((last - media) / desv) if desv > 0 else None,
            "percentil_ultimo": _percentil(r, last)}


def _vs_merval(ah, f: List[str], y: np.ndarray, base: str,
               fx_al: Optional[Dict[str, float]]) -> Optional[Dict[str, Any]]:
    """β / correlación de retornos diarios, retorno relativo en la ventana y el
    Merval rebasado al nivel inicial del ticker (overlay). Sólo ruedas
    comunes; con el Merval dividido por el MISMO FX que el ticker."""
    sm = ah.serie(MERVAL)
    if not sm:
        return None
    md: Dict[str, float] = {}
    for ff, vv in zip(sm["fechas"], sm["ultimo"]):
        if not (vv and vv > 0):
            continue
        if base != "ars":
            fx = (fx_al or {}).get(ff)
            if not fx:
                continue
            vv = vv / fx
        md[ff] = float(vv)
    common = [i for i, ff in enumerate(f) if ff in md]
    if len(common) < _MIN_CMP:
        return {"n": len(common), "insuficiente": True}
    yt = y[common]
    ym = np.array([md[f[i]] for i in common])
    rt, rm = yt[1:] / yt[:-1] - 1.0, ym[1:] / ym[:-1] - 1.0
    beta = corr = None
    if rm.std() > 0 and rt.std() > 0:
        beta = float(np.cov(rt, rm, ddof=1)[0, 1] / rm.var(ddof=1))
        corr = float(np.corrcoef(rt, rm)[0, 1])
    ret_m = (float(ym[-1]) / float(ym[0]) - 1.0) * 100.0
    ret_t = (float(yt[-1]) / float(yt[0]) - 1.0) * 100.0
    return {"n": len(common), "beta": beta, "corr": corr, "ret_merval": ret_m,
            "ret_rel": ret_t - ret_m, "desde": f[common[0]], "hasta": f[common[-1]],
            "_idx": common, "_overlay": ym / float(ym[0]) * float(yt[0])}


def _histograma(v: np.ndarray) -> Optional[Dict[str, Any]]:
    """Histograma de la variable graficada + la normal con su misma μ/σ
    (escalada a cuentas) y qué % de las observaciones cae dentro de ±1σ /
    ±2σ (normal: 68,3 / 95,4) — colas gordas a simple vista."""
    v = np.asarray(v, dtype=float)
    n = len(v)
    if n < 3:
        return None
    k = int(min(30, max(8, round(math.sqrt(n) * 1.4))))
    lo, hi = float(v.min()), float(v.max())
    if hi <= lo or _es_ruido(hi - lo, hi):
        hi = lo + (abs(lo) * 0.01 or 1.0)
    counts, edges = np.histogram(v, bins=k, range=(lo, hi))
    mu = float(v.mean())
    sd = float(v.std(ddof=1)) if n > 1 else 0.0
    if _es_ruido(sd, max(abs(mu), abs(hi))):
        sd = 0.0
    w = float(edges[1] - edges[0])
    xs = np.linspace(lo, hi, 80)
    if sd > 0:
        curva = n * w * np.exp(-0.5 * ((xs - mu) / sd) ** 2) / (sd * math.sqrt(2.0 * math.pi))
    else:
        curva = np.zeros_like(xs)
    skew, kurt = _momentos(v)
    return {"n": n, "k": k, "counts": [int(c) for c in counts], "edges": [float(e) for e in edges],
            "mu": mu, "sd": sd, "lo": lo, "hi": hi, "skew": skew, "kurt": kurt,
            "curva_x": xs.tolist(), "curva_y": curva.tolist(),
            "dentro_1s": (float(np.mean(np.abs(v - mu) <= sd) * 100.0) if sd > 0 else None),
            "dentro_2s": (float(np.mean(np.abs(v - mu) <= 2 * sd) * 100.0) if sd > 0 else None)}


# ── Geometría SVG ─────────────────────────────────────────────────────────
def _xlabels(f: List[str], X, n: int) -> List[Dict[str, Any]]:
    largo = n > 260
    out = []
    for k in range(5):
        i = round(k * (n - 1) / 4)
        d = f[i]
        out.append({"x": X(i), "txt": d[8:10] + "/" + d[5:7] + ("/" + d[2:4] if largo else "")})
    return out


def _geom_precio(f: List[str], y: np.ndarray, st: Dict[str, Any], cmp: Optional[Dict[str, Any]],
                 width: int = _W, height: int = _H) -> Dict[str, Any]:
    from backend.services.svg_charts import _nice_ticks

    n = len(y)
    pad_l, pad_r, pad_t, pad_b = 66, 16, 12, 28
    pw, ph = width - pad_l - pad_r, height - pad_t - pad_b
    tend, sig = st["_tend"], st["sigma_tend"]
    lo = min(float(y.min()), float((tend - 2 * sig).min()))
    hi = max(float(y.max()), float((tend + 2 * sig).max()))
    ov = cmp.get("_overlay") if (cmp and not cmp.get("insuficiente")) else None
    if ov is not None and len(ov):
        lo, hi = min(lo, float(ov.min())), max(hi, float(ov.max()))
    span = hi - lo
    if _es_ruido(span, hi):                  # serie plana: rango de ±1 % alrededor del nivel
        span = abs(hi) * 0.02 or 1.0
        lo, hi = hi - span / 2.0, hi + span / 2.0
    lo -= span * 0.06
    hi += span * 0.06

    def X(i: int) -> float:
        return round(pad_l + (i / (n - 1)) * pw, 2)

    def Y(v: float) -> float:
        return round(pad_t + (hi - v) / (hi - lo) * ph, 2)

    def banda(k: float) -> str:
        arriba = " ".join(f"{X(i)},{Y(float(tend[i]) + k * sig)}" for i in range(n))
        abajo = " ".join(f"{X(i)},{Y(float(tend[i]) - k * sig)}" for i in range(n - 1, -1, -1))
        return arriba + " " + abajo

    return {
        "modo": "precio", "w": width, "h": height, "x0": pad_l, "x1": width - pad_r,
        "y0": pad_t, "y1": height - pad_b,
        "yticks": [{"v": t, "y": Y(t)} for t in _nice_ticks(lo, hi, 5)],
        "xlabels": _xlabels(f, X, n), "xlabel_y": height - 8,
        "poly": " ".join(f"{X(i)},{Y(float(v))}" for i, v in enumerate(y)),
        "band1": banda(1.0) if sig > 0 else None, "band2": banda(2.0) if sig > 0 else None,
        "tend": {"x1": X(0), "y1": Y(float(tend[0])), "x2": X(n - 1), "y2": Y(float(tend[-1]))},
        "min": {"x": X(int(y.argmin())), "y": Y(float(y.min()))},
        "max": {"x": X(int(y.argmax())), "y": Y(float(y.max()))},
        "last": {"cx": X(n - 1), "cy": Y(float(y[-1]))},
        "overlay": (" ".join(f"{X(i)},{Y(float(v))}" for i, v in zip(cmp["_idx"], ov))
                    if ov is not None and len(ov) else None),
    }


def _geom_retornos(r_f: List[str], r: np.ndarray, st: Dict[str, Any],
                   width: int = _W, height: int = _H) -> Dict[str, Any]:
    from backend.services.svg_charts import _nice_ticks

    m = len(r)
    pad_l, pad_r, pad_t, pad_b = 66, 16, 12, 28
    pw, ph = width - pad_l - pad_r, height - pad_t - pad_b
    media, desv = st["media"], st["desvio"]
    lo = min(float(r.min()), media - 2 * desv, 0.0)
    hi = max(float(r.max()), media + 2 * desv, 0.0)
    span = (hi - lo) or 1.0
    lo -= span * 0.06
    hi += span * 0.06

    def X(i: int) -> float:
        return round(pad_l + (i + 0.5) / m * pw, 2)

    def Y(v: float) -> float:
        return round(pad_t + (hi - v) / (hi - lo) * ph, 2)

    zero_y = Y(0.0)
    bw = max(1.0, round(pw / m * 0.7, 2))
    bars = [{"x": round(X(i) - bw / 2, 2), "y": min(Y(float(v)), zero_y), "w": bw,
             "h": max(0.6, round(abs(Y(float(v)) - zero_y), 2)), "neg": bool(v < 0),
             "fecha": r_f[i], "v": float(v)} for i, v in enumerate(r)]
    lineas = [{"y": Y(media), "lbl": "media", "cls": "pa-media"}]
    if desv > 0:
        for k in (1, -1, 2, -2):
            lineas.append({"y": Y(media + k * desv), "lbl": ("+" if k > 0 else "−") + f"{abs(k)}σ",
                           "cls": f"pa-sig{abs(k)}"})
    return {
        "modo": "retornos", "w": width, "h": height, "x0": pad_l, "x1": width - pad_r,
        "y0": pad_t, "y1": height - pad_b, "zero_y": zero_y,
        "yticks": [{"v": t, "y": Y(t)} for t in _nice_ticks(lo, hi, 5)],
        "xlabels": _xlabels(r_f, X, m), "xlabel_y": height - 8,
        "bars": bars, "lineas": lineas,
    }


def _geom_hist(h: Dict[str, Any], ultimo: Optional[float],
               width: int = _WH, height: int = _H) -> Dict[str, Any]:
    pad_l, pad_r, pad_t, pad_b = 10, 10, 14, 28
    pw, ph = width - pad_l - pad_r, height - pad_t - pad_b
    lo, hi = h["lo"], h["hi"]
    cmax = max(max(h["counts"]), max(h["curva_y"]) if h["curva_y"] else 0.0, 1.0)

    def X(v: float) -> float:
        return round(pad_l + (v - lo) / (hi - lo) * pw, 2)

    def Y(c: float) -> float:
        return round(pad_t + (1.0 - c / cmax) * ph, 2)

    edges = h["edges"]
    y_base = Y(0.0)
    bars = [{"x": round(X(edges[i]) + 0.5, 2), "w": max(0.5, round(X(edges[i + 1]) - X(edges[i]) - 1.0, 2)),
             "y": Y(c), "h": round(y_base - Y(c), 2), "lo": edges[i], "hi": edges[i + 1], "n": c}
            for i, c in enumerate(h["counts"])]
    return {
        "w": width, "h": height, "x0": pad_l, "x1": width - pad_r, "y0": pad_t, "y1": y_base,
        "bars": bars,
        "curva": " ".join(f"{X(x)},{Y(c)}" for x, c in zip(h["curva_x"], h["curva_y"])),
        "mu_x": X(h["mu"]),
        "ultimo_x": (X(ultimo) if ultimo is not None and lo <= ultimo <= hi else None),
        "xlabels": [{"x": X(lo), "v": lo, "anchor": "start"}, {"x": X(h["mu"]), "v": h["mu"], "anchor": "middle"},
                    {"x": X(hi), "v": hi, "anchor": "end"}],
        "xlabel_y": height - 8,
    }


def _tabla(f: List[str], y: np.ndarray, v: Optional[np.ndarray], prev: Optional[float],
           es_tir: bool = False) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    p = prev
    for i in range(len(y)):
        val = float(y[i])
        tiene_prev = p is not None and (es_tir or p)
        rows.append({"fecha": f[i], "valor": val,
                     "var": (val - p) if tiene_prev else None,
                     "var_pct": ((val / p - 1.0) * 100.0) if (tiene_prev and not es_tir and p) else None,
                     "volumen": (float(v[i]) if v is not None and np.isfinite(v[i]) else None)})
        p = val
    rows.reverse()
    return rows[:500]


# ── Entrada principal ─────────────────────────────────────────────────────
def analizar(ticker: str, base: str = "ars", modo: str = "precio", dias: int = 90,
             desde: Optional[str] = None, hasta: Optional[str] = None,
             comparar: bool = True, campo: str = "precio") -> Dict[str, Any]:
    """Todo el análisis de un ticker en una ventana. `campo`: "precio" (acciones,
    CEDEARs, Merval y bonos) o "tir" (bonos: la TIREA en %, variaciones en
    pp, sin ÷ FX ni Merval). `ok=False` + `motivo` cuando no hay serie / FX /
    ruedas suficientes."""
    ticker = (ticker or "").strip()
    campo = "tir" if campo == "tir" else "precio"
    es_tir = campo == "tir"
    base = base if (base in BASES and not es_tir) else "ars"
    modo = "retornos" if modo == "retornos" else "precio"
    s = serie_de(ticker, campo)
    if not s:
        que = "TIR guardada (sólo bonos con ficha)" if es_tir else "cierres guardados"
        return {"ok": False, "ticker": ticker, "motivo": f"no hay {que} de {ticker or '—'}"}
    ticker = s.get("ticker") or ticker.upper()          # código resuelto (TX26j conserva la j)
    fechas: List[str] = list(s["fechas"])
    px = np.asarray(s["ultimo"], dtype=float)
    vol = s.get("volumen")
    vol = np.asarray(vol, dtype=float) if vol is not None else None
    ok = np.isfinite(px) if es_tir else (np.isfinite(px) & (px > 0))
    if not ok.all():
        idx_ok = np.flatnonzero(ok)
        fechas = [fechas[i] for i in idx_ok]
        px = px[idx_ok]
        vol = vol[idx_ok] if vol is not None else None
    fx_al: Optional[Dict[str, float]] = None
    if base != "ars":
        al = _alinear(fechas, fx_por_fecha(base))
        keep = [i for i, v in enumerate(al) if v]
        if len(keep) < 2:
            return {"ok": False, "ticker": ticker,
                    "motivo": f"todavía no hay serie de {BASES[base]} para las fechas de {ticker} "
                              "(se llena con el cierre diario)"}
        fx_al = {fechas[i]: float(al[i]) for i in keep}
        fechas = [fechas[i] for i in keep]
        px = np.array([px[i] / al[i] for i in keep])
        vol = vol[keep] if vol is not None else None
    n_all = len(fechas)
    if desde or hasta:
        idx = [i for i, f in enumerate(fechas) if (not desde or f >= desde) and (not hasta or f <= hasta)]
    else:
        idx = list(range(max(0, n_all - int(dias)) if dias else 0, n_all))
    if len(idx) < 2:
        return {"ok": False, "ticker": ticker, "motivo": "menos de 2 ruedas guardadas en la ventana elegida"}
    i0, i1 = idx[0], idx[-1]
    f = fechas[i0:i1 + 1]
    y = px[i0:i1 + 1]
    v = vol[i0:i1 + 1] if vol is not None else None
    n = len(y)
    prev = float(px[i0 - 1]) if i0 > 0 else None
    # Retornos diarios (% — o Δ en pp para la TIR): el primero contra la rueda
    # previa a la ventana si existe (así una ventana de 90 tiene 90, no 89).
    if prev is not None and (es_tir or prev > 0):
        base_r = np.concatenate(([prev], y[:-1]))
        r = (y - base_r) if es_tir else (y / base_r - 1.0) * 100.0
        r_f = f
    else:
        r = (y[1:] - y[:-1]) if es_tir else (y[1:] / y[:-1] - 1.0) * 100.0
        r_f = f[1:]

    st = _stats_nivel(f, y, es_tir)
    rt = _stats_retornos(r_f, r)
    from backend.services import acciones_hist as ah
    cmp = (_vs_merval(ah, f, y, base, fx_al)
           if (comparar and ticker != MERVAL and not es_tir and s.get("fuente") == "acciones") else None)
    if modo == "precio":
        h = _histograma(y)
        geom = _geom_precio(f, y, st, cmp)
        ultimo_h: Optional[float] = float(y[-1])
    else:
        h = _histograma(r)
        geom = _geom_retornos(r_f, r, rt)
        ultimo_h = float(r[-1]) if len(r) else None
    st.pop("_tend", None)
    if cmp:
        cmp.pop("_idx", None)
        cmp.pop("_overlay", None)
    return {
        "ok": True, "ticker": ticker, "panel": s.get("panel", ""), "base": base,
        "base_label": BASES[base], "modo": modo, "n": n, "n_total": n_all,
        "campo": campo, "es_tir": es_tir, "fuente": s.get("fuente", ""),
        "u_nivel": "%" if es_tir else "", "u_delta": " pp" if es_tir else "%",
        "desde": f[0], "hasta": f[-1], "nivel": st, "retornos": rt, "cmp": cmp,
        "hist": h, "geom": geom, "geom_hist": (_geom_hist(h, ultimo_h) if h else None),
        "tabla": _tabla(f, y, v, prev, es_tir),
    }
