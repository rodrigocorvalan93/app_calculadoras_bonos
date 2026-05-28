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
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("backend.bonds")

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
    for name in dir(especies):
        if name.startswith("_"):
            continue
        candidate = getattr(especies, name, None)
        if isinstance(candidate, rentafija.Bono):
            objs[name] = candidate

    codes = sorted(objs.keys())
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
