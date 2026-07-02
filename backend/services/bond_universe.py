"""Bond universe lookup.

Loads `especies` lazily so importing the FastAPI app doesn't immediately
fire `indices.main()` (the BCRA fetch). The first call from a route is what
triggers the cold-start work.

Phase 1 enumerates only the base `rentafija.Bono` instances exposed as
module-level attributes in `especies.py`. The j/v suffix variants that the
legacy app builds dynamically from `CURVES` will be wired in Phase 2.
"""
from __future__ import annotations

import logging
import threading
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("backend.bonds")


def _is_future_vto(vto: object) -> bool:
    """True si la fecha de vencimiento (DD/MM/AAAA o ISO) es hoy o futura."""
    if not vto:
        return False
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(vto), fmt).date() >= date.today()
        except ValueError:
            continue
    return False

_lock = threading.Lock()
_codes: Optional[List[str]] = None
_objs: Optional[Dict[str, object]] = None
_bono_cls = None


def _load_universe() -> Tuple[List[str], Dict[str, object]]:
    """Import especies and enumerate every Bono instance found."""
    import especies  # noqa: WPS433 - intentional lazy import
    import rentafija

    global _bono_cls
    _bono_cls = rentafija.Bono

    objs: Dict[str, object] = {}
    orphans_live: List[str] = []
    for name in dir(especies):
        if name.startswith("_"):
            continue
        candidate = getattr(especies, name, None)
        if isinstance(candidate, rentafija.Bono):
            objs[name] = candidate
        elif isinstance(candidate, dict) and candidate.get("Código"):
            # Ficha definida como dict pero NUNCA envuelta en Bono → invisible
            # para la app (fue el caso de MGCTO). Avisamos sólo si sigue VIVA;
            # las vencidas se dejan sin envolver a propósito.
            if _is_future_vto(candidate.get("Vencimiento")):
                orphans_live.append(str(candidate.get("Código") or name))

    codes = sorted(objs.keys())
    if orphans_live:
        logger.warning(
            "[bond_universe] %d ficha(s) VIVA(s) definidas como dict pero sin "
            "envolver en rentafija.Bono → no aparecen en la app: %s",
            len(orphans_live), ", ".join(sorted(orphans_live)),
        )
    logger.info("[bond_universe] loaded %d bonds", len(codes))
    return codes, objs


def ensure_loaded() -> None:
    global _codes, _objs
    with _lock:
        if _codes is None or _objs is None:
            _codes, _objs = _load_universe()


def all_codes() -> List[str]:
    ensure_loaded()
    return list(_codes)  # type: ignore[arg-type]


def get(code: str):
    """Return the singleton Bono instance (or None if unknown)."""
    ensure_loaded()
    return (_objs or {}).get(code)
