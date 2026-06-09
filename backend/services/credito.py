"""Análisis de créditos — scoring crediticio corporativo (porteado de OMSweb_app
vía el módulo legacy `OMScredit`).

Lee `credit_scores.json` (lo genera el equipo de research con
export_credit_scores.py); si no está, degrada a vacío y la pestaña lo avisa.
Todo se cachea en el primer uso → sub-50 ms.
"""
from __future__ import annotations

import logging
import math
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_state: Dict[str, Any] = {"inited": False, "issuers": [], "available": False, "error": None}


def _clean(v: Any) -> Any:
    if isinstance(v, float) and math.isnan(v):
        return None
    return v


def _ensure() -> None:
    if _state["inited"]:
        return
    with _lock:
        if _state["inited"]:
            return
        try:
            import OMScredit

            from backend.services import bond_universe
            bond_universe.ensure_loaded()
            bonos = [b for b in (bond_universe.get(c) for c in bond_universe.all_codes()) if b is not None]
            OMScredit.init(bonos)
            df = OMScredit.get_all_issuers_df()
            if df is not None and not df.empty:
                _state["issuers"] = [{k: _clean(v) for k, v in r.items()} for r in df.to_dict("records")]
            _state["available"] = bool(_state["issuers"])
            if not _state["available"]:
                _state["error"] = "No se encontró credit_scores.json (corré export_credit_scores.py)."
            logger.info("[credito] %d emisores cargados", len(_state["issuers"]))
        except Exception as exc:  # noqa: BLE001
            logger.exception("[credito] init falló")
            _state["error"] = str(exc)
        _state["inited"] = True


def refresh() -> None:
    with _lock:
        _state.update({"inited": False, "issuers": [], "available": False, "error": None})
    # forzar reinit del cache legacy también
    try:
        import OMScredit
        OMScredit._CACHE.clear()
    except Exception:  # noqa: BLE001
        pass
    _ensure()


def available() -> bool:
    _ensure()
    return _state["available"]


def status() -> Dict[str, Any]:
    _ensure()
    return {"available": _state["available"], "error": _state["error"], "n": len(_state["issuers"])}


def sectors() -> List[str]:
    _ensure()
    return sorted({r.get("Sector") for r in _state["issuers"] if r.get("Sector")})


def issuers(sector: Optional[List[str]] = None, score_min: Optional[float] = None,
            solo_ons: bool = False) -> List[Dict[str, Any]]:
    """Tabla de emisores filtrada (sector / score mínimo / sólo con ONs)."""
    _ensure()
    out: List[Dict[str, Any]] = []
    for r in _state["issuers"]:
        if sector and r.get("Sector") not in sector:
            continue
        sc = r.get("Score")
        if score_min is not None and (sc is None or sc != sc or sc < score_min):
            continue
        if solo_ons and not r.get("ONs cargadas"):
            continue
        out.append(r)
    return out


def detail(ticker: str) -> Dict[str, Any]:
    """Ficha del emisor + sus ONs cargadas (con métricas live el route)."""
    _ensure()
    try:
        import OMScredit
        return {"credit": OMScredit.get_credit(ticker) or {}, "bonds": OMScredit.get_bonds_for_issuer(ticker)}
    except Exception:  # noqa: BLE001
        return {"credit": {}, "bonds": []}
