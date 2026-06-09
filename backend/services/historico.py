"""Históricos macro (BCRA) — lee bcra_data_backup.json una vez, cacheado.

El json mapea cada variable a un string {fecha_ISO: {col: valor}}
(DataFrame.to_json orient=index). Lo parseamos sin pandas y cacheamos; la
data macro cambia 1x/día, así que releer es explícito (refresh()).

Series: a3500 (FX mayorista), BADLAR, TAMAR, CER, UVA, inflación mensual.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("backend.historico")

REPO_ROOT = Path(__file__).resolve().parents[2]

# La data macro del BCRA cambia ~1x/día. NO se re-lee en cada request (el riel
# pega cada 15s): sólo se re-lee el backup al cruzar estos horarios (hora local),
# que es cuando se actualiza el archivo. Como mucho 2 re-lecturas por día.
_MACRO_REFRESH_TIMES = ((11, 0), (15, 30))
_macro_slot: Optional[Tuple[Any, int]] = None

# key del json → (columna interna, label de display)
_SERIES_META: Dict[str, Tuple[str, str]] = {
    "a3500": ("tca3500", "A3500 · FX mayorista"),
    "badlar": ("BADLAR", "BADLAR (%)"),
    "tamar": ("TAMAR", "TAMAR (%)"),
    "CER": ("CER", "CER (índice)"),
    "UVA": ("UVA", "UVA ($)"),
    "inflamom": ("inflacionmom", "Inflación mensual (%)"),
}

_lock = threading.Lock()
_cache: Optional[Dict[str, Any]] = None


def _json_path() -> str:
    env = os.getenv("BCRA_BACKUP_PATH")
    if env:
        env = os.path.expandvars(os.path.expanduser(env))
        if os.path.isfile(env):
            return env
    return str(REPO_ROOT / "bcra_data_backup.json")


def _load() -> Dict[str, Any]:
    out: Dict[str, Any] = {"loaded": False, "error": None, "series": {}, "path": None}
    path = _json_path()
    out["path"] = path
    if not os.path.isfile(path):
        out["error"] = f"No se encontró {path}"
        return out
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"Error leyendo bcra_data_backup.json: {exc}"
        return out

    series: Dict[str, Dict[str, Any]] = {}
    for key, (col, label) in _SERIES_META.items():
        s = raw.get(key)
        if not s:
            continue
        try:
            inner = json.loads(s) if isinstance(s, str) else s
        except (ValueError, TypeError):
            continue
        if not isinstance(inner, dict):
            continue
        pts: List[Tuple[str, float]] = []
        for dstr, rec in inner.items():
            v = rec.get(col) if isinstance(rec, dict) else rec
            if v is None:
                continue
            try:
                val = float(v)
            except (TypeError, ValueError):
                continue
            pts.append((str(dstr)[:10], val))   # 'YYYY-MM-DD'
        pts.sort(key=lambda p: p[0])
        if pts:
            series[key] = {"label": label, "points": pts}
    out["series"] = series
    out["loaded"] = bool(series)
    if not series:
        out["error"] = out["error"] or "Sin series macro en el json."
    logger.info("[historico] %d series macro cargadas", len(series))
    return out


def ensure_loaded() -> Dict[str, Any]:
    global _cache
    with _lock:
        if _cache is None:
            _cache = _load()
        return _cache


def refresh() -> Dict[str, Any]:
    global _cache
    with _lock:
        _cache = _load()
        return _cache


def status() -> Dict[str, Any]:
    c = ensure_loaded()
    return {"loaded": c["loaded"], "error": c["error"], "path": c["path"], "n": len(c["series"])}


def series_list() -> List[Dict[str, Any]]:
    c = ensure_loaded()
    return [{"key": k, "label": v["label"], "n": len(v["points"])} for k, v in c["series"].items()]


def macro_maybe_refresh() -> None:
    """Re-lee el backup BCRA (barato; NO toca la API del BCRA) sólo cuando se
    cruza un horario programado (11:00 / 15:30 hora local). Idempotente: dispara
    como mucho 1 re-lectura por horario por día, aunque el riel pegue cada 15s.
    """
    global _macro_slot
    now = datetime.now()
    idx = None
    for i, (h, m) in enumerate(_MACRO_REFRESH_TIMES):
        if (now.hour, now.minute) >= (h, m):
            idx = i                                   # último horario ya cruzado hoy
    if idx is None:
        return
    key = (now.date(), idx)
    with _lock:
        if _macro_slot == key:
            return
        _macro_slot = key
    refresh()                                          # fuera del lock (refresh lo toma)


def macro_snapshot() -> List[Dict[str, Any]]:
    """Resumen macro para el riel del dólar: última observación (valor + fecha)
    de cada serie YA cacheada, más 'aplicable' (promedio de los últimos N días
    hábiles, igual que el legacy `indices.py`) para TAMAR/BADLAR.

    Reusa los puntos en memoria → NO hace fetch al BCRA; el riel lo puede pedir
    cada 15s sin costo. La re-lectura del backup la dispara `macro_maybe_refresh`
    (a las 11:00 / 15:30), no esta función — que queda pura (sin side-effects).

    Cada item: {key, label, fmt, value, date, aplicable?}
      fmt = 'pct' (el valor ya viene en %, formatear con ar_pct_pp) |
            'num' (índice/$, formatear con ar_num).
    """
    series = ensure_loaded()["series"]

    def _last(key: str) -> Optional[Tuple[str, float]]:
        s = series.get(key)
        return s["points"][-1] if s and s["points"] else None

    def _tail_mean(key: str, n: int) -> Optional[float]:
        s = series.get(key)
        if not s or not s["points"]:
            return None
        vals = [v for _, v in s["points"][-n:]]
        return sum(vals) / len(vals) if vals else None

    def _ar_date(iso: str) -> str:
        return f"{iso[8:10]}/{iso[5:7]}/{iso[0:4]}" if iso and len(iso) >= 10 else iso

    # (key del json, label, formato, ventana 'aplicable' o None)
    specs = [
        ("tamar", "TAMAR", "pct", 5),
        ("badlar", "BADLAR", "pct", 5),
        ("CER", "CER", "num", None),
        ("UVA", "UVA", "num", None),
        ("inflamom", "Inflación m/m", "pct", None),
    ]
    out: List[Dict[str, Any]] = []
    for key, label, fmt, n in specs:
        p = _last(key)
        if not p:
            continue
        item: Dict[str, Any] = {"key": key.lower(), "label": label, "fmt": fmt,
                                "value": p[1], "date": _ar_date(p[0])}
        if n:
            item["aplicable"] = _tail_mean(key, n)
        out.append(item)
    return out


def series_points(key: str, days: Optional[int] = None,
                  desde: Optional[str] = None, hasta: Optional[str] = None) -> Dict[str, Any]:
    """Puntos de una serie. Si se pasan `desde`/`hasta` (ISO 'YYYY-MM-DD') se
    recorta a ese rango exacto (tienen prioridad sobre `days`); si no, `days`
    recorta a los últimos N días calendario desde la última observación."""
    c = ensure_loaded()
    s = c["series"].get(key)
    if not s:
        return {"label": "", "points": []}
    pts = s["points"]
    if (desde or hasta) and pts:
        pts = [p for p in pts if (not desde or p[0] >= desde) and (not hasta or p[0] <= hasta)]
    elif days and pts:
        from datetime import date, timedelta
        try:
            cutoff = (date.fromisoformat(pts[-1][0]) - timedelta(days=days)).isoformat()
            pts = [p for p in pts if p[0] >= cutoff]
        except ValueError:
            pass
    return {"label": s["label"], "points": pts}
