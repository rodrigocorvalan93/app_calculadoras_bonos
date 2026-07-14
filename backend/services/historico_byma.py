"""Histórico BYMA — precios y tasas por bono y fecha, desde el Excel local
`Delta - historico_byma_px_tasas.xlsx` (OneDrive). Fuente de la vista
"tasas por curva" de Históricos.

El Excel NO está en el repo: se resuelve por env vars (igual que el legacy
`OMSweb_app._resolve_historico_path`). Si no está, todo degrada a vacío y la
pestaña muestra cómo configurarlo — el resto de la app no se entera.

Diseño de performance: el Excel se lee UNA vez y se cachea ya pre-indexado en
arrays paralelos por código (`dates` + `vals[metric]`), así cada request sólo
filtra por rango de fechas y arma el SVG — sin pandas en el path caliente.
"""
from __future__ import annotations

import logging
import os
import threading
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from backend.services import deltapaths

logger = logging.getLogger(__name__)

_HISTORICO_FILENAME = "Delta - historico_byma_px_tasas.xlsx"
_METRICS = ("TIREA", "TNA", "TEM", "Paridad")          # métricas de tasa/paridad
_EXTRA = ("Last Price", "Duration")                    # para la vista "un bono" (futuro)

_lock = threading.Lock()
_cache: Optional[Dict[str, Any]] = None


def _empty(error: Optional[str] = None, path: Optional[str] = None) -> Dict[str, Any]:
    return {"loaded": False, "error": error, "path": path, "by_code": {},
            "bounds": (None, None), "n_codes": 0, "n_dates": 0, "n_obs": 0,
            "last_update": None}


def _resolve_named(filename: str) -> Optional[str]:
    """Busca `filename` en DELTA_HISTORICO_DIR y junto a DELTA_BASES_DIR
    (padre de Carteras). Mismo orden que el legacy."""
    env_dir = os.getenv("DELTA_HISTORICO_DIR")
    if env_dir:
        env_dir = deltapaths.expand(env_dir, want="dir")
        cand = os.path.join(env_dir, filename)
        if os.path.isfile(cand):
            return cand
    env_bases = os.getenv("DELTA_BASES_DIR")
    if env_bases:
        env_bases = deltapaths.expand(env_bases, want="dir")
        cand = os.path.join(os.path.dirname(env_bases.rstrip("\\/")), filename)
        if os.path.isfile(cand):
            return cand
    return None


def _resolve_path() -> Optional[str]:
    """El Excel canónico: DELTA_HISTORICO_PATH (archivo) → DELTA_HISTORICO_DIR
    (carpeta) → DELTA_BASES_DIR/.. (junto a Carteras)."""
    env = os.getenv("DELTA_HISTORICO_PATH")
    if env:
        env = deltapaths.expand(env, want="file")
        if os.path.isfile(env):
            return env
    return _resolve_named(_HISTORICO_FILENAME)


def _parquet_sibling(xlsx_path: str) -> str:
    return os.path.splitext(xlsx_path)[0] + ".parquet"


def _pick_source(xlsx: Optional[str]) -> Tuple[Optional[str], str]:
    """(path, formato) a leer. El parquet espejo gana si existe y no es más
    viejo que el Excel (bymaapi y el autosave escriben ambos; si alguien
    actualizó SOLO el Excel — bymaapi viejo, edición a mano — el Excel manda
    y el parquet se regenera después de leerlo). Sin Excel, vale el parquet
    suelto: la base sigue disponible."""
    pq = _parquet_sibling(xlsx) if xlsx else _resolve_named(
        os.path.splitext(_HISTORICO_FILENAME)[0] + ".parquet")
    pq_ok = pq is not None and os.path.isfile(pq)
    if xlsx is None:
        return (pq, "parquet") if pq_ok else (None, "")
    if pq_ok:
        try:
            # 60 s de gracia: bymaapi escribe xlsx y parquet en tándem y el
            # orden/mtime puede variar con OneDrive de por medio.
            if os.path.getmtime(pq) >= os.path.getmtime(xlsx) - 60.0:
                return pq, "parquet"
        except OSError:
            pass
    return xlsx, "xlsx"


def _regen_parquet(xlsx_path: str, df) -> None:
    """Cache best-effort: espeja el Excel recién leído a .parquet (atómico)
    para que la PRÓXIMA carga sea ~100× más rápida. Nunca rompe la carga."""
    pq = _parquet_sibling(xlsx_path)
    tmp = pq + ".tmp"
    try:
        df.to_parquet(tmp, index=False)
        os.replace(tmp, pq)
        logger.info("[historico_byma] parquet espejo regenerado: %s", pq)
    except Exception as exc:  # noqa: BLE001 — sin pyarrow / sin permisos: seguimos con xlsx
        logger.info("[historico_byma] no pude regenerar el parquet (%s)", exc)
        try:
            os.remove(tmp)
        except OSError:
            pass


def _build(df) -> Dict[str, Any]:
    """DataFrame limpio → estructura cacheada (arrays paralelos por código)."""
    from backend.services import symbols as syms

    by_code: Dict[str, Any] = {}
    all_dates: set = set()
    n_obs = 0
    has_proy = "Proy" in df.columns
    for code, sub in df.groupby("Código", sort=False):
        sub = sub.sort_values("fecha_hoy")
        dates = [d.date().isoformat() for d in sub["fecha_hoy"]]
        vals: Dict[str, List[Optional[float]]] = {}
        for m in _METRICS + _EXTRA:
            if m in sub.columns:
                vals[m] = [float(x) if x == x else None for x in sub[m]]   # NaN → None
        proy = 0
        if has_proy:
            try:
                proy = int(sub["Proy"].iloc[-1])
            except (TypeError, ValueError):
                proy = 0
        elif str(code).lower().endswith("j"):
            proy = 1
        by_code[str(code)] = {"base": syms.calc_to_md_code(code), "proy": proy,
                              "dates": dates, "vals": vals}
        all_dates.update(dates)
        n_obs += len(dates)
    bounds = (min(all_dates), max(all_dates)) if all_dates else (None, None)
    return {"loaded": bool(by_code), "error": None if by_code else "Excel sin filas válidas",
            "by_code": by_code, "bounds": bounds, "n_codes": len(by_code),
            "n_dates": len(all_dates), "n_obs": n_obs, "last_update": bounds[1]}


def _load() -> Dict[str, Any]:
    xlsx = _resolve_path()
    path, fmt = _pick_source(xlsx)
    if path is None:
        return _empty("No se encontró el Excel histórico (configurá DELTA_HISTORICO_PATH / "
                      "DELTA_HISTORICO_DIR / DELTA_BASES_DIR).")
    try:
        import pandas as pd
        if fmt == "parquet":
            df = pd.read_parquet(path)
        else:
            df = pd.read_excel(path, sheet_name="Sheet1")
            if xlsx:
                _regen_parquet(xlsx, df)     # la próxima carga lee el espejo rápido
        df["fecha_hoy"] = pd.to_datetime(df["fecha_hoy"], errors="coerce")
        df = df.dropna(subset=["fecha_hoy", "Código"]).copy()
        df["Código"] = df["Código"].astype(str)
        for col in _METRICS + _EXTRA + ("tem_spread",):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        # dedup (Código, fecha) keep last; drop filas muertas y TIREAs absurdas.
        # Defensivo ante variaciones de columnas en el Excel (sólo aplico la
        # máscara si las columnas existen).
        df = df.sort_values(["Código", "fecha_hoy"]).drop_duplicates(["Código", "fecha_hoy"], keep="last")
        cols = set(df.columns)
        if {"TIREA", "Duration", "Paridad"} <= cols:
            dead = (df["TIREA"].fillna(0) == 0) & (df["Duration"].fillna(0) == 0) & (df["Paridad"].fillna(0) == 0)
            df = df[~dead].copy()
        if "TIREA" in cols:
            df = df[~((df["TIREA"] > 2.0) | (df["TIREA"] <= -0.99))].copy()
        out = _build(df)
        out["path"] = path
        logger.info("[historico_byma] %d códigos · %d fechas · %d obs (fuente %s)",
                    out["n_codes"], out["n_dates"], out["n_obs"], fmt)
        return out
    except Exception as exc:  # noqa: BLE001
        logger.exception("[historico_byma] load falló")
        return _empty(f"Error leyendo histórico: {exc}", path)


def ensure_loaded() -> Dict[str, Any]:
    global _cache
    if _cache is None:
        with _lock:
            if _cache is None:
                _cache = _load()
    return _cache


def refresh() -> Dict[str, Any]:
    global _cache
    with _lock:
        _cache = _load()
    return _cache


def available() -> bool:
    return ensure_loaded()["loaded"]


def meta() -> Dict[str, Any]:
    c = ensure_loaded()
    return {"loaded": c["loaded"], "error": c["error"], "n_codes": c["n_codes"],
            "n_dates": c["n_dates"], "n_obs": c["n_obs"], "last_update": c["last_update"],
            "dmin": c["bounds"][0], "dmax": c["bounds"][1]}


def curves_with_history(desde: Optional[str] = None, hasta: Optional[str] = None,
                        proy: str = "todos") -> List[str]:
    """Keys de curva que tienen ≥1 código con historia en el rango/filtro."""
    from backend.services import curves
    c = ensure_loaded()
    if not c["loaded"]:
        return []
    present_bases = {
        e["base"] for e in c["by_code"].values()
        if (proy == "todos" or (proy == "base" and e["proy"] == 0) or (proy == "proy" and e["proy"] == 1))
        and _has_in_range(e, desde, hasta)
    }
    out = []
    groups = curves.build_curve_codes()
    from backend.services import symbols as syms
    for cv in curves.list_curves():
        bases = {syms.calc_to_md_code(x) for x in groups.get(cv.key, [])}
        if bases & present_bases:
            out.append(cv.key)
    return out


def _has_in_range(entry: Dict[str, Any], desde: Optional[str], hasta: Optional[str]) -> bool:
    # ≥2 puntos: `curve_series` descarta los códigos con <2 (no se puede trazar una
    # línea con uno solo), así que ofrecer la curva con 1 daba un gráfico vacío.
    n = 0
    for d in entry["dates"]:
        if (not desde or d >= desde) and (not hasta or d <= hasta):
            n += 1
            if n >= 2:
                return True
    return False


def curve_series(curve_key: str, metric: str = "TIREA", desde: Optional[str] = None,
                 hasta: Optional[str] = None, proy: str = "todos") -> Dict[str, Any]:
    """Series por bono de la curva: cada línea = `metric` histórica de un código.
    Devuelve líneas + agregado (prom/mín/máx) para las bandas de referencia."""
    from backend.services import curves, symbols as syms
    c = ensure_loaded()
    metric = metric if metric in _METRICS + ("Last Price",) else "TIREA"
    is_price = metric == "Last Price"
    if not c["loaded"]:
        return {"loaded": False, "lines": [], "metric": metric}
    base_set = {syms.calc_to_md_code(x) for x in curves.build_curve_codes().get(curve_key, [])}
    is_yield = metric in ("TIREA", "TNA", "TEM")
    dfac, dunit = (10000.0, "bps") if is_yield else (100.0, "pp")
    lines: List[Dict[str, Any]] = []
    all_vals: List[float] = []
    for code, e in c["by_code"].items():
        if e["base"] not in base_set:
            continue
        if proy == "base" and e["proy"] != 0:
            continue
        if proy == "proy" and e["proy"] != 1:
            continue
        series = e["vals"].get(metric)
        if not series:
            continue
        pts = [(d, v) for d, v in zip(e["dates"], series)
               if v is not None and (not desde or d >= desde) and (not hasta or d <= hasta)]
        if len(pts) < 2:
            continue
        if is_price:
            # Precio: la variación se lee en % (fin/inicio − 1), no en pp.
            delta = (pts[-1][1] / pts[0][1] - 1.0) * 100.0 if pts[0][1] else 0.0
            dunit_row = "%"
        else:
            delta = (pts[-1][1] - pts[0][1]) * dfac
            dunit_row = dunit
        lines.append({"code": code, "points": pts, "last": pts[-1][1],
                      "delta": delta, "delta_unit": dunit_row})
        all_vals.extend(v for _, v in pts)
    lines.sort(key=lambda ln: ln["last"], reverse=True)
    agg = None
    if all_vals:
        agg = {"mean": sum(all_vals) / len(all_vals), "min": min(all_vals),
               "max": max(all_vals), "n": len(all_vals)}
    label = next((cv.label for cv in curves.list_curves() if cv.key == curve_key), curve_key)
    # scale: las métricas son fracciones (×100 → %); el precio va tal cual.
    return {"loaded": True, "lines": lines, "agg": agg, "metric": metric,
            "curve_label": label, "is_yield": is_yield,
            "scale": 1.0 if is_price else 100.0}


def scatter_by_dates(curve_key: str, fechas: List[str], metric: str = "TEM",
                     proy: str = "todos") -> Dict[str, Any]:
    """Foto de la curva en VARIAS fechas: por cada fecha, puntos
    (Duration, metric) de los bonos de la curva con dato a esa fecha (último
    conocido ≤ fecha, con tolerancia de 7 días). Puro índice en memoria —
    costo ~µs por punto, sin pricing."""
    from backend.services import curves, symbols as syms
    c = ensure_loaded()
    metric = metric if metric in _METRICS else "TEM"
    if not c["loaded"]:
        return {"loaded": False, "series": [], "metric": metric}
    base_set = {syms.calc_to_md_code(x) for x in curves.build_curve_codes().get(curve_key, [])}
    series: List[Dict[str, Any]] = []
    for f in fechas:
        if not f:
            continue
        pts = []
        lim = (date.fromisoformat(f) - timedelta(days=7)).isoformat()
        for code, e in c["by_code"].items():
            if e["base"] not in base_set:
                continue
            if proy == "base" and e["proy"] != 0:
                continue
            if proy == "proy" and e["proy"] != 1:
                continue
            v, dv = _value_and_date_at(e, metric, f)
            dur, dd = _value_and_date_at(e, "Duration", f)
            if v is None or dur is None or dv is None or dv < lim or dd is None or dd < lim:
                continue
            pts.append({"code": code, "dur": dur, "v": v})
        if pts:
            pts.sort(key=lambda p: p["dur"])
            series.append({"fecha": f, "points": pts})
    label = next((cv.label for cv in curves.list_curves() if cv.key == curve_key), curve_key)
    return {"loaded": True, "series": series, "metric": metric, "curve_label": label}


def _value_and_date_at(entry: Dict[str, Any], metric: str, target_iso: str
                       ) -> tuple:
    """(valor, fecha ISO) de la última observación de `metric` ≤ target."""
    vals = entry["vals"].get(metric)
    if not vals:
        return None, None
    best_v = best_d = None
    for d, v in zip(entry["dates"], vals):
        if d > target_iso:
            break
        if v is not None:
            best_v, best_d = v, d
    return best_v, best_d


# ── Resumen semanal por segmento (Δprecio + ΔTIR) ────────────────────────────
def _value_at(entry: Dict[str, Any], metric: str, target_iso: str) -> Optional[float]:
    """Último valor conocido de `metric` hasta `target_iso` (fecha ≤ target)."""
    vals = entry["vals"].get(metric)
    if not vals:
        return None
    best = None
    for d, v in zip(entry["dates"], vals):
        if d > target_iso:
            break
        if v is not None:
            best = v
    return best


def _avg_seg(xs: List[float]) -> Optional[float]:
    ys = [x for x in xs if x is not None and x == x]
    return sum(ys) / len(ys) if ys else None


def _ix_to_date(d: Any) -> Optional[date]:
    """Normaliza una etiqueta de índice a `date`. Robusto a date / Timestamp / str
    ISO (el poller de FX inyecta hoy en inputs['a3500'] con índice string → índice
    MIXTO; sin esto una sola etiqueta string rompía toda la comparación de A3500)."""
    if isinstance(d, date) and not hasattr(d, "hour"):   # date puro (no datetime)
        return d
    if hasattr(d, "date"):                                # Timestamp / datetime
        try:
            return d.date()
        except Exception:  # noqa: BLE001
            return None
    try:
        return date.fromisoformat(str(d)[:10])
    except Exception:  # noqa: BLE001
        return None


def _index_series(key: str, col: str):
    """Serie del índice global (R/O), robusta a columna faltante (cae a la 1ª) y a
    que inputs[key] sea ya una Series."""
    import rentafija
    obj = rentafija.inputs.get(key)
    if obj is None:
        return None
    if hasattr(obj, "columns"):                          # DataFrame
        return obj[col] if col in obj.columns else (obj.iloc[:, 0] if obj.shape[1] else None)
    return obj                                            # Series


def _index_at(key: str, col: str, target_iso: str) -> Optional[float]:
    """Último valor de un índice global hasta `target` (R/O). Salta etiquetas no
    parseables en vez de abortar (una sola string rompía A3500 entero)."""
    try:
        s = _index_series(key, col)
        if s is None or target_iso is None:
            return None
        tgt = date.fromisoformat(target_iso)
        best = None
        for d, v in s.items():
            dd = _ix_to_date(d)
            if dd is not None and dd <= tgt and v == v:
                best = float(v)                          # serie ordenada → último ≤ tgt
        return best
    except Exception:  # noqa: BLE001
        return None


def _index_last(key: str, col: str) -> Optional[float]:
    try:
        s = _index_series(key, col)
        return float(s.iloc[-1]) if s is not None and len(s) else None
    except Exception:  # noqa: BLE001
        return None


def _window_indices(start_iso: str, end_iso: Optional[str] = None) -> Dict[str, Any]:
    """Evolución de CER, A3500 y TAMAR en la ventana [start, end]. CER/A3500 = % de
    cambio (acumulación CER / deva oficial); TAMAR = nivel inicio→fin (es una tasa) y
    su Δ en pp. El extremo final usa el valor AL `end` de la ventana (consistente con
    el Δprecio de los bonos); si no hay end, cae al último dato del índice."""
    def _end(key: str, col: str) -> Optional[float]:
        return _index_at(key, col, end_iso) if end_iso else _index_last(key, col)

    def _pct(key: str, col: str) -> Optional[float]:
        a0, a1 = _index_at(key, col, start_iso), _end(key, col)
        return (a1 / a0 - 1.0) if (a0 and a0 > 0 and a1 is not None) else None

    t0, t1 = _index_at("tamar", "TAMAR", start_iso), _end("tamar", "TAMAR")
    return {
        "cer": _pct("CER", "CER"),
        "a3500": _pct("a3500", "tca3500"),
        "tamar_ini": t0, "tamar_fin": t1,
        "tamar_delta": (t1 - t0) if (t0 is not None and t1 is not None) else None,
    }


def _floater_index(code: str) -> Optional[str]:
    """Índice de referencia (TAMAR/BADLAR) si el bono es tasa variable
    benchmarkeada; si no None — criterio de comparador._margen_aplica / pricing."""
    from backend.services import bond_universe
    o = bond_universe.get(code)
    if o is None:
        return None
    tipo = (getattr(o, "tipo_tasa_interes", "") or "").upper()
    idx = (getattr(o, "index", "") or "").upper()
    return idx if (tipo in ("VARIABLE", "VARIABLE_CAP") and idx in ("TAMAR", "BADLAR")) else None


def _margen_tna(entry: Dict[str, Any], bench_pct: Optional[float],
                target_iso: str) -> Optional[float]:
    """Margen histórico (decimal) = TNA a 30 días de la TIR del bono − tasa de
    referencia, al `target_iso`:

        TNA_30 = ((1 + TIREA) ** (30/365) − 1) × (365/30)
        margen = TNA_30 − bench/100

    `bench_pct` = nivel TAMAR/BADLAR del día en %. None si falta el benchmark o la
    TIR del bono."""
    if bench_pct is None or bench_pct != bench_pct:
        return None
    tirea = _value_at(entry, "TIREA", target_iso)
    if tirea is None:
        return None
    tna30 = ((1.0 + tirea) ** (30.0 / 365.0) - 1.0) * (365.0 / 30.0)
    return tna30 - bench_pct / 100.0


def weekly_segments(days: int = 7) -> Dict[str, Any]:
    """Resumen de la ventana (default 1 semana) por SEGMENTO —las categorías de
    Escenario MÁS los segmentos duales (base + pata TAMAR, ver esc.DUAL_CATEGORIES)—:
    Δ Precio % (Last Price fin/inicio ≈ total return de la ventana, en el precio
    NATIVO del bono) y Δ TIR (pp). Promedio simple por segmento + `rows` con el
    detalle por bono (Δprecio / ΔTIR / ΔTEM y margen = TNA 30d de la TIR −
    TAMAR/BADLAR, sólo tasa variable), más la deva del A3500."""
    from backend.services import curves, escenario as esc, symbols as syms
    data = ensure_loaded()
    end = (data.get("bounds") or (None, None))[1]
    if not data.get("loaded") or not end:
        return {"loaded": False, "error": data.get("error") or "sin fechas",
                "segments": [], "days": days}
    start = (date.fromisoformat(end) - timedelta(days=int(days))).isoformat()
    by_code = data["by_code"]
    codes_by_curve = curves.build_curve_codes()
    # Benchmark (TAMAR/BADLAR, en %) al inicio/fin de la ventana — una vez, igual
    # para todos los bonos del índice (alimenta el margen TNA histórico).
    bench_ini = {"TAMAR": _index_at("tamar", "TAMAR", start), "BADLAR": _index_at("badlar", "BADLAR", start)}
    bench_fin = {"TAMAR": _index_at("tamar", "TAMAR", end), "BADLAR": _index_at("badlar", "BADLAR", end)}
    segments: List[Dict[str, Any]] = []
    for cat in esc.CATEGORIES + esc.DUAL_CATEGORIES:
        dprices: List[float] = []
        dtirs: List[float] = []
        cups: List[float] = []
        tirs_fin: List[float] = []
        durs_fin: List[float] = []
        members: List[str] = []
        rows: List[Dict[str, Any]] = []
        for code in codes_by_curve.get(cat.curve, []):
            # La pata dual '…v' no tiene ticker propio en BYMA: el Excel la guarda
            # bajo el ticker base (TTS26v → TTS26). Probamos el código exacto y,
            # si no está, su forma base (sin sufijo j/v).
            entry = by_code.get(code) or by_code.get(syms.calc_to_md_code(code))
            dur = _value_at(entry, "Duration", end) if entry is not None else None
            if entry is None or not esc.in_bucket(cat, dur):
                continue
            p0, f0 = _value_and_date_at(entry, "Last Price", start)
            p1, f1 = _value_and_date_at(entry, "Last Price", end)
            t0, t1 = _value_at(entry, "TIREA", start), _value_at(entry, "TIREA", end)
            m0, m1 = _value_at(entry, "TEM", start), _value_at(entry, "TEM", end)
            dprice = (p1 / p0 - 1.0) if (p0 and p1 and p0 > 0) else None
            # Cortes de cupón en la ventana: como se opera DIRTY, el precio cae
            # discreto el día del corte y el Δ Precio solo "miente". Acá va el
            # cobro (renta+amort de la ficha, cacheado por bono+ventana) como %
            # del precio inicial — Δ Precio + cupones ≈ TR realizado.
            cup_pct = None
            if dprice is not None and f0 and f1 and f0 < f1:
                from backend.services import tr_realizado
                cup = tr_realizado.cupones_entre_cached(code, f0, f1)
                cup_pct = (cup / p0) if p0 else 0.0
            dtir = (t1 - t0) if (t0 is not None and t1 is not None) else None
            dtem = (m1 - m0) if (m0 is not None and m1 is not None) else None
            # Margen = TNA(30d) de la TIR − tasa de referencia; SÓLO tasa variable
            # (TAMAR/BADLAR). CER / tasa fija / HD no llevan margen.
            margen = dmargen = None
            idx = _floater_index(code)
            if idx is not None:
                mg0 = _margen_tna(entry, bench_ini.get(idx), start)
                mg1 = _margen_tna(entry, bench_fin.get(idx), end)
                margen = mg1
                dmargen = (mg1 - mg0) if (mg0 is not None and mg1 is not None) else None
            if dprice is not None:
                dprices.append(dprice)
                cups.append(cup_pct or 0.0)   # mismo set que dprices → Δp + cup ≈ TR
            if dtir is not None:
                dtirs.append(dtir)
            if t1 is not None:
                tirs_fin.append(t1)           # nivel de TIR al cierre de la ventana
            if dur is not None:
                durs_fin.append(dur)          # duration al cierre de la ventana
            members.append(code)
            rows.append({"code": code, "dur": dur, "dprice": dprice, "dtir": dtir,
                         "cup_pct": cup_pct,
                         "dtem": dtem, "margen": margen, "dmargen": dmargen,
                         # TIREA absoluta al inicio/fin de la ventana → alimenta el
                         # gráfico "curva antes/ahora" (TIR vs duration). El Δ ya está
                         # en dtir; acá van los niveles para poder trazar las 2 curvas.
                         "tir0": t0, "tir1": t1})
        if members:
            rows.sort(key=lambda r: (r["dur"] is None, r["dur"] or 0.0))
            segments.append({"key": cat.key, "label": cat.label, "n": len(members),
                             "dprice": _avg_seg(dprices), "dtir": _avg_seg(dtirs),
                             "cup_pct": _avg_seg(cups),
                             "tir_avg": _avg_seg(tirs_fin), "dur_avg": _avg_seg(durs_fin),
                             "members": members, "rows": rows,
                             "has_margen": any(r["margen"] is not None for r in rows)})
    return {"loaded": True, "start": start, "end": end, "days": days,
            "segments": segments, "indices": _window_indices(start, end)}
