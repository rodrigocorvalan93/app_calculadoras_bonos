"""Curve definitions and code grouping.

Phase 2 step 1: port `CurveDef`, `CURVES`, `AGGREGATES` and the
`build_curve_codes` partition from `OMSweb_app.py` so we can list the
available curves and resolve which bond codes belong to each one.

The market data layer (live prices + TIREA per row) lands in the next
step; for now this module is pure metadata over `especies.py`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

from . import bond_universe

logger = logging.getLogger("backend.curves")


@dataclass(frozen=True)
class CurveDef:
    key: str
    label: str
    bond_type: str  # used later by the metrics layer (cer / lecap / dual / etc.)


CURVES: List[CurveDef] = [
    CurveDef("cer", "CER", "cer"),
    CurveDef("lecap", "LECAP / Tasa Fija", "lecap"),
    CurveDef("tamar", "TAMAR", "tamar"),
    CurveDef("cerproy", "CER Proyectado", "cerproy"),
    CurveDef("todos_ars_proyectado", "Todos ARS (Proyectado)", "_aggregate"),
    CurveDef("dolarlinked", "Dólar Linked", "dlksob"),
    CurveDef("globales", "Globales (Ley Extranjera)", "hdsob"),
    CurveDef("bonares", "Bonares (Ley Argentina)", "hdsob"),
    CurveDef("bopreales", "Bopreales (Ley Argentina)", "bopreal"),
    CurveDef("dualfija", "Dual Fija (base)", "dual"),
    CurveDef("dualtamar", "Dual TAMAR (v)", "dual"),
    CurveDef("dualcer", "Dual CER (base)", "dual"),
    CurveDef("corp_tamar", "Corp. TAMAR", "tamar"),
    CurveDef("corp_badlar", "Corp. BADLAR", "tamar"),
    CurveDef("corp_tasafija", "Corp. Tasa Fija", "lecap"),
    CurveDef("corp_uva", "Corp. UVA/CER", "cer"),
    CurveDef("corp_dlk", "Corp. Dólar Linked", "corp_dlk"),
    CurveDef("corp_hdmep", "Corp. USD MEP", "hdmep"),
    CurveDef("corp_hdcable", "Corp. USD Cable", "hdcable"),
]


# Aggregate curves are unions of other curves. They show up as
# `<curve_key>` whose codes = sorted union of the listed sub-keys.
AGGREGATES: Dict[str, List[str]] = {
    # Todos los ARS por tipo de ajuste (proyectados): TAMAR + CER Proyectado +
    # Tasa Fija, incluyendo los duales en su bucket (dual TAMAR/CER/Fija).
    "todos_ars_proyectado": ["cerproy", "tamar", "lecap", "dualfija", "dualtamar", "dualcer"],
}


def mix_codes(keys: List[str]) -> List[str]:
    """Unión (dedup, en orden) de los códigos de varias curvas — para las
    combinaciones que arma el usuario AL VUELO desde la UI (`mix:a,b,c`).

    No persiste ni clasifica nada: son uniones efímeras de curvas que ya
    existen. `curve_key_for` ni se entera, así que Posiciones / locate quedan
    intactos. Acepta cualquier key de `build_curve_codes()` (base o agregada).
    """
    table = build_curve_codes()
    seen: Set[str] = set()
    out: List[str] = []
    for k in keys:
        for c in table.get(k, []):
            if c not in seen:
                seen.add(c)
                out.append(c)
    return out


def mix_label(keys: List[str]) -> str:
    by = {c.key: c.label for c in CURVES}
    return "Combinada: " + " + ".join(by.get(k, k) for k in keys)


# Curve key → calc-code suffix para derivar la variante desde el código BASE.
# Sólo dualtamar lo necesita (TTD26 → TTD26v); cerproy NO va acá porque la
# industria "…Proyectado" ya devuelve los códigos con 'j' (ver build_curve_codes).
CURVE_EVAL_SUFFIX: Dict[str, str] = {
    "dualtamar": "v",
}


def _apply_curve_suffix(curve_key: str, base_code: str) -> str:
    suf = CURVE_EVAL_SUFFIX.get(str(curve_key), "")
    return f"{base_code}{suf}" if suf else base_code


def _codigo_obj(b) -> str:
    return (
        getattr(b, "codigo", None)
        or getattr(b, "ticker", None)
        or getattr(b, "symbol", None)
        or b.__class__.__name__
    )


# Cached partition. Bond universe is static at process boot so we
# compute once and reuse forever. `build_curve_codes` is keyed by the
# universe size (cheap invariant) — if the universe ever changes (hot
# reload of especies), bump that and the result is recomputed.
_codes_cache: Tuple[int, Dict[str, List[str]]] | None = None


def build_curve_codes() -> Dict[str, List[str]]:
    """Partition every Bono in `especies` into the curve buckets.

    Ported verbatim from `OMSweb_app.build_curve_codes` — same
    industry/clasificacion/quote-price filters. The legacy guarded
    membership against `BONDS` (market-data ticker set); since we don't
    yet have a live broker session in Phase 2, we accept every code
    whose `Bono` exists in the universe.
    """
    global _codes_cache
    bond_universe.ensure_loaded()
    all_codes = bond_universe.all_codes()
    cache_key = len(all_codes)
    if _codes_cache and _codes_cache[0] == cache_key:
        return _codes_cache[1]

    # by_ind[ind] = [(code, clasificacion, quote_price_cnv)]
    by_ind: Dict[str, List[Tuple[str, str, str]]] = {}
    by_ind_clas: Dict[Tuple[str, str], List[Tuple[str, str]]] = {}

    for code in all_codes:
        b = bond_universe.get(code)
        if b is None:
            continue
        ind = getattr(b, "industria", None) or ""
        clas = getattr(b, "clasificacion", None) or ""
        qpc = (getattr(b, "quote_price_cnv", None) or "").strip().upper()
        by_ind.setdefault(ind, []).append((code, clas, qpc))
        by_ind_clas.setdefault((ind, clas), []).append((code, qpc))

    def _all(ind: str) -> List[Tuple[str, str, str]]:
        return by_ind.get(ind, [])

    cer = sorted({c for c, _, _ in _all("Soberano Inflación")})

    lecap_set: Set[str] = set()
    for c, clas, _ in _all("Soberano ARS Tasa Fija"):
        if clas == "Soberano":
            lecap_set.add(c)
    for c, _, _ in _all("Soberano Letras Zero Cupón (Ledes y Letes)"):
        lecap_set.add(c)
    lecap = sorted(lecap_set)

    tamar = sorted({c for c, _, _ in _all("Soberano ARS TAMAR")})

    globales = sorted({
        c for c, _, qpc in _all("Soberano USD Ley Extranjera") if qpc == "DIRTY"
    })

    dolarlinked = sorted({c for c, _, _ in _all("Soberanos Dolar Linked")})

    # Los códigos de la industria "…Proyectado" ya vienen con la 'j' (TX26j),
    # así que NO se les aplica sufijo — antes salían "TX26jj", que no existe en
    # el universo y dejaba la curva CER Proyectado vacía.
    cerproy = sorted({
        c
        for c, clas, _ in _all("Soberano Inflación Proyectado")
        if clas == "Soberano"
    })

    dualfija = sorted({
        c for c, clas, _ in _all("Soberano ARS Dual Fija/Tamar")
        if clas == "Soberano"
    })
    dualcer = sorted({
        c for c, clas, _ in _all("Soberano ARS Dual CER/Tamar")
        if clas == "Soberano"
    })
    dualtamar = sorted({_apply_curve_suffix("dualtamar", c) for c in dualfija + dualcer})

    bonares = sorted({
        c for c, qpc in by_ind_clas.get(("Soberano USD Ley Argentina D", "Soberano"), [])
        if qpc == "DIRTY"
    })
    bopreales = sorted({
        c for c, _ in by_ind_clas.get(("Soberanos USD BCRA D", "Soberano"), [])
    })

    corp_tamar_set: Set[str] = set()
    corp_badlar_set: Set[str] = set()
    corp_tasafija_set: Set[str] = set()
    corp_uva_set: Set[str] = set()
    corp_hdmep_set: Set[str] = set()
    corp_hdcable_set: Set[str] = set()
    corp_dlk_set: Set[str] = set()

    for code in all_codes:
        b = bond_universe.get(code)
        if b is None:
            continue
        clas = (getattr(b, "clasificacion", None) or "").strip()
        qpc = (getattr(b, "quote_price_cnv", None) or "").strip().upper()
        if clas == "Corporativo TAMAR":
            corp_tamar_set.add(code)
        elif clas == "Corporativo BADLAR":
            corp_badlar_set.add(code)
        elif clas == "Corporativo Tasa Fija":
            corp_tasafija_set.add(code)
        elif clas == "Corporativo UVA":
            corp_uva_set.add(code)
        elif clas == "Corporativo Dolar Linked":
            corp_dlk_set.add(code)
        elif clas == "Corporativo Hard Dolar MEP":
            corp_hdmep_set.add(code)
        elif clas == "Corporativo Hard Dolar":
            byma_c = code[:-1] + "C" if code.endswith("O") else code
            if byma_c in bond_universe.all_codes() and qpc == "CLEAN":
                corp_hdcable_set.add(byma_c)
            elif qpc == "DIRTY":
                corp_hdcable_set.add(code)

    out: Dict[str, List[str]] = {
        "cer": cer,
        "lecap": lecap,
        "tamar": tamar,
        "globales": globales,
        "dolarlinked": dolarlinked,
        "cerproy": cerproy,
        "bonares": bonares,
        "bopreales": bopreales,
        "dualfija": dualfija,
        "dualcer": dualcer,
        "dualtamar": dualtamar,
        "corp_tamar": sorted(corp_tamar_set),
        "corp_badlar": sorted(corp_badlar_set),
        "corp_tasafija": sorted(corp_tasafija_set),
        "corp_uva": sorted(corp_uva_set),
        "corp_dlk": sorted(corp_dlk_set),
        "corp_hdmep": sorted(corp_hdmep_set),
        "corp_hdcable": sorted(corp_hdcable_set),
    }

    for agg_key, sub_keys in AGGREGATES.items():
        union: Set[str] = set()
        for sk in sub_keys:
            union.update(out.get(sk, []))
        out[agg_key] = sorted(union)

    _codes_cache = (cache_key, out)
    logger.info(
        "[curves] partition built: %d curves, %d total codes",
        len(out),
        sum(len(v) for v in out.values()),
    )
    return out


_rev_cache: Dict[str, str] | None = None


def curve_key_for(code: str) -> str | None:
    """Curva ESPECÍFICA a la que pertenece `code` (exacto, j/v incluidos);
    None si no está en ninguna (acciones, etc.). Excluye agregados. Cacheado
    junto al particionado — lookup O(1) tras el primer uso."""
    global _rev_cache
    if _rev_cache is None:
        rev: Dict[str, str] = {}
        for key, codes in build_curve_codes().items():
            if key in AGGREGATES:
                continue
            for c in codes:
                rev.setdefault(c, key)
        _rev_cache = rev
    return _rev_cache.get(code)


def curve_def(key: str) -> CurveDef | None:
    for c in CURVES:
        if c.key == key:
            return c
    return None


def list_curves() -> List[CurveDef]:
    return list(CURVES)
