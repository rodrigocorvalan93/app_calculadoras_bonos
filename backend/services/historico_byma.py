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


def _resolve_path() -> Optional[str]:
    """DELTA_HISTORICO_PATH (archivo) → DELTA_HISTORICO_DIR (carpeta) →
    DELTA_BASES_DIR/.. (junto a Carteras). Mismo orden que el legacy."""
    env = os.getenv("DELTA_HISTORICO_PATH")
    if env:
        env = os.path.expandvars(os.path.expanduser(env))
        if os.path.isfile(env):
            return env
    env_dir = os.getenv("DELTA_HISTORICO_DIR")
    if env_dir:
        env_dir = os.path.expandvars(os.path.expanduser(env_dir))
        cand = os.path.join(env_dir, _HISTORICO_FILENAME)
        if os.path.isfile(cand):
            return cand
    env_bases = os.getenv("DELTA_BASES_DIR")
    if env_bases:
        env_bases = os.path.expandvars(os.path.expanduser(env_bases))
        cand = os.path.join(os.path.dirname(env_bases.rstrip("\\/")), _HISTORICO_FILENAME)
        if os.path.isfile(cand):
            return cand
    return None


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
    path = _resolve_path()
    if path is None:
        return _empty("No se encontró el Excel histórico (configurá DELTA_HISTORICO_PATH / "
                      "DELTA_HISTORICO_DIR / DELTA_BASES_DIR).")
    try:
        import pandas as pd
        df = pd.read_excel(path, sheet_name="Sheet1")
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
        logger.info("[historico_byma] %d códigos · %d fechas · %d obs", out["n_codes"], out["n_dates"], out["n_obs"])
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
    metric = metric if metric in _METRICS else "TIREA"
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
        delta = (pts[-1][1] - pts[0][1]) * dfac
        lines.append({"code": code, "points": pts, "last": pts[-1][1],
                      "delta": delta, "delta_unit": dunit})
        all_vals.extend(v for _, v in pts)
    lines.sort(key=lambda ln: ln["last"], reverse=True)
    agg = None
    if all_vals:
        agg = {"mean": sum(all_vals) / len(all_vals), "min": min(all_vals),
               "max": max(all_vals), "n": len(all_vals)}
    label = next((cv.label for cv in curves.list_curves() if cv.key == curve_key), curve_key)
    return {"loaded": True, "lines": lines, "agg": agg, "metric": metric,
            "curve_label": label, "is_yield": is_yield}


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


def _index_at(key: str, col: str, target_iso: str) -> Optional[float]:
    """Último valor de un índice global (rentafija.inputs[key][col]) hasta target (R/O)."""
    try:
        import rentafija
        s = rentafija.inputs[key][col]
        tgt = date.fromisoformat(target_iso)
        prev = [float(v) for d, v in s.items()
                if (d.date() if hasattr(d, "date") else d) <= tgt and v == v]
        return prev[-1] if prev else None
    except Exception:  # noqa: BLE001
        return None


def _index_last(key: str, col: str) -> Optional[float]:
    try:
        import rentafija
        return float(rentafija.inputs[key][col].iloc[-1])
    except Exception:  # noqa: BLE001
        return None


def _window_indices(start_iso: str) -> Dict[str, Any]:
    """Evolución de CER, A3500 y TAMAR en la ventana. CER/A3500 = % de cambio
    (acumulación CER / deva); TAMAR = nivel inicio→fin (es una tasa) y su Δ en pp."""
    def _pct(key: str, col: str) -> Optional[float]:
        a0, a1 = _index_at(key, col, start_iso), _index_last(key, col)
        return (a1 / a0 - 1.0) if (a0 and a0 > 0 and a1 is not None) else None

    t0, t1 = _index_at("tamar", "TAMAR", start_iso), _index_last("tamar", "TAMAR")
    return {
        "cer": _pct("CER", "CER"),
        "a3500": _pct("a3500", "tca3500"),
        "tamar_ini": t0, "tamar_fin": t1,
        "tamar_delta": (t1 - t0) if (t0 is not None and t1 is not None) else None,
    }


def weekly_segments(days: int = 7) -> Dict[str, Any]:
    """Resumen de la ventana (default 1 semana) por SEGMENTO —mismas categorías que
    Escenario (curva + bucket de duration)—: Δ Precio % (Last Price fin/inicio ≈ total
    return de la ventana, en el precio NATIVO del bono) y Δ TIR (pp). Promedio simple
    por segmento + los códigos que toma, más la deva del dólar A3500 de la ventana."""
    from backend.services import curves, escenario as esc
    data = ensure_loaded()
    end = (data.get("bounds") or (None, None))[1]
    if not data.get("loaded") or not end:
        return {"loaded": False, "error": data.get("error") or "sin fechas",
                "segments": [], "days": days}
    start = (date.fromisoformat(end) - timedelta(days=int(days))).isoformat()
    by_code = data["by_code"]
    codes_by_curve = curves.build_curve_codes()
    segments: List[Dict[str, Any]] = []
    for cat in esc.CATEGORIES:
        dprices: List[float] = []
        dtirs: List[float] = []
        members: List[str] = []
        for code in codes_by_curve.get(cat.curve, []):
            entry = by_code.get(code)
            if entry is None or not esc.in_bucket(cat, _value_at(entry, "Duration", end)):
                continue
            p0, p1 = _value_at(entry, "Last Price", start), _value_at(entry, "Last Price", end)
            t0, t1 = _value_at(entry, "TIREA", start), _value_at(entry, "TIREA", end)
            if p0 and p1 and p0 > 0:
                dprices.append(p1 / p0 - 1.0)
            if t0 is not None and t1 is not None:
                dtirs.append(t1 - t0)
            members.append(code)
        if members:
            segments.append({"key": cat.key, "label": cat.label, "n": len(members),
                             "dprice": _avg_seg(dprices), "dtir": _avg_seg(dtirs),
                             "members": members})
    return {"loaded": True, "start": start, "end": end, "days": days,
            "segments": segments, "indices": _window_indices(start)}
