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
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from backend.locale_ar import hoy_ba

logger = logging.getLogger("backend.bonds")


def _is_future_vto(vto: object) -> bool:
    """True si la fecha de vencimiento (DD/MM/AAAA o ISO) es hoy o futura (BA)."""
    if not vto:
        return False
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(vto), fmt).date() >= hoy_ba()
        except ValueError:
            continue
    return False

_lock = threading.Lock()
_codes: Optional[List[str]] = None
_objs: Optional[Dict[str, object]] = None
_upper: Optional[Dict[str, str]] = None       # CÓDIGO EN MAYÚSCULAS → código del universo
_bono_cls = None


def _sanear_inyeccion_a3500() -> int:
    """especies.py, al importarse, inyecta en `rentafija.inputs['a3500']` una
    fila con la fecha de HOY (`indices.refresh_a3500_in_rentafija`: el SIOPEL
    del arranque o, si MAE no responde, el último cierre relabelado) — un
    mecanismo del Streamlit legacy. En la app hacía que
    `pricing.a3500_aplicable()` creyera que el BCRA ya publicó el A3500 del día
    y los DLK se valuaban TODO el día contra ese número en vez del mayorista
    intradía (desk 19/10). Acá se saca: en la serie queda sólo lo que publicó
    el BCRA (backup en memoria de `historico`); el FX del día entra por el
    override intradía de pricing. No toca especies.py (regla del 10/09).
    Devuelve cuántas filas sacó."""
    try:
        import rentafija
        from backend.services import historico

        df = rentafija.inputs.get("a3500")
        if df is None or len(df) == 0:
            return 0
        pts = historico.series_points("a3500").get("points") or []
        if not pts:                       # sin backup no se puede distinguir: no tocar
            return 0
        bcra = {str(p[0])[:10]: float(p[1]) for p in pts}
        hoy = hoy_ba()
        col = "tca3500" if "tca3500" in df.columns else df.columns[0]
        malas, pisadas = [], []
        for ix in df.index:
            d = _a_date(ix)
            if d is None or d < hoy:
                continue
            iso = d.isoformat()
            if iso not in bcra:
                malas.append(ix)                                   # fila de hoy que el BCRA no publicó
            else:
                try:
                    v = float(df.loc[ix, col])
                except (TypeError, ValueError, KeyError):
                    continue
                if abs(v - bcra[iso]) > 1e-9:
                    pisadas.append((ix, v, bcra[iso]))              # publicado, pero pisado por la inyección
        if not malas and not pisadas:
            return 0
        nuevo = df.drop(index=malas) if malas else df.copy()
        for ix, _v, bueno in pisadas:
            # La app arrancó DESPUÉS de que el BCRA publicó: la inyección PISÓ
            # el A3500 del día con el SIOPEL/MAE del arranque → se repone el publicado.
            nuevo.loc[ix, col] = bueno
        rentafija.inputs["a3500"] = nuevo
        if malas:
            logger.warning("[bond_universe] saqué %d fila(s) de hoy inyectada(s) en inputs['a3500'] "
                           "(%s) que el BCRA no publicó: el DLK intradía usa el mayorista",
                           len(malas), ", ".join(f"{_a_date(i)} = {float(df.loc[i, col]):.4f}" for i in malas))
        if pisadas:
            logger.warning("[bond_universe] repuse el A3500 publicado en inputs['a3500'] que la inyección "
                           "del arranque había pisado: %s",
                           ", ".join(f"{_a_date(i)}: {v:.4f} → {b:.4f}" for i, v, b in pisadas))
        return len(malas) + len(pisadas)
    except Exception:  # noqa: BLE001 — nunca voltea la carga del universo
        logger.exception("[bond_universe] no pude sanear inputs['a3500']")
        return 0


def _a_date(x: object):
    """date / Timestamp / 'AAAA-MM-DD' → date (None si no se puede; NaT → None)."""
    try:
        if x != x:                                 # pd.NaT / NaN (NaT es instancia de datetime)
            return None
    except Exception:  # noqa: BLE001
        pass
    if isinstance(x, datetime):
        return x.date()
    if hasattr(x, "isoformat") and hasattr(x, "year") and not hasattr(x, "hour"):
        return x                                   # date puro
    if hasattr(x, "date"):
        try:
            return x.date()
        except Exception:  # noqa: BLE001
            return None
    try:
        return datetime.strptime(str(x)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _load_universe() -> Tuple[List[str], Dict[str, object]]:
    """Import especies and enumerate every Bono instance found."""
    import especies  # noqa: WPS433 - intentional lazy import
    import rentafija

    global _bono_cls
    _bono_cls = rentafija.Bono
    _sanear_inyeccion_a3500()

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


def _upper_map(codes: List[str]) -> Dict[str, str]:
    """{CÓDIGO.upper(): código} para resolver sin distinguir mayúsculas. Si dos
    códigos chocaran al pasarlos a mayúsculas (hoy no pasa: 593 códigos, 0
    choques), ninguno entra al mapa: sólo la coincidencia exacta los encuentra
    y nunca se elige uno al azar."""
    out: Dict[str, str] = {}
    dup = set()
    for c in codes:
        k = c.upper()
        if k in out:
            dup.add(k)
        out[k] = c
    for k in dup:
        out.pop(k, None)
    if dup:
        logger.warning("[bond_universe] códigos que sólo difieren en mayúsculas (sin resolución "
                       "insensible): %s", ", ".join(sorted(dup)))
    return out


def ensure_loaded() -> None:
    global _codes, _objs, _upper
    with _lock:
        if _codes is None or _objs is None:
            _codes, _objs = _load_universe()
            _upper = _upper_map(_codes)


def all_codes() -> List[str]:
    ensure_loaded()
    return list(_codes)  # type: ignore[arg-type]


def get(code: str):
    """Return the singleton Bono instance (or None if unknown)."""
    ensure_loaded()
    return (_objs or {}).get(code)


def resolve(code: object) -> Optional[str]:
    """Código del universo para lo que tipeó el usuario, SIN distinguir
    mayúsculas: "tmve8v" / "TMVE8V" → "TMVE8v", "gd30" → "GD30". Las patas
    calculadas llevan sufijo en minúscula (`…j` CER proyectado, `…v` pata TAMAR
    de los duales) y quien normaliza a mayúsculas (el add-in de Excel lo hace
    en el cliente Y en el server) las perdía: "Bono 'TMVE8V' no encontrado".
    Coincidencia exacta primero; None si no existe. O(1)."""
    c = str(code or "").strip()
    if not c:
        return None
    if _objs is None or _upper is None:      # sin lock en el camino caliente (batch del add-in)
        ensure_loaded()
    if c in (_objs or {}):
        return c
    return (_upper or {}).get(c.upper())
