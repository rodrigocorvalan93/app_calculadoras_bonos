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
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("backend.historico")

REPO_ROOT = Path(__file__).resolve().parents[2]

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
