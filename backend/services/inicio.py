"""Inicio — el resumen del mercado en una pantalla (07/10).

Arma el payload de las tarjetas de la página de aterrizaje a partir de lo que
YA está en memoria: el store del feed (vía las filas de curvas que comparte
con Mercado / Curvas, `routes.curves._rows_en_seq`), `dolares.summary`
(oficial / MEP / CCL / brecha / canje), las cauciones BYMA del riel y las de
MAE, las series macro (TAMAR / BADLAR), las acciones del panel líder, los
futuros de dólar y el riesgo país del poller. Todo son lookups y aritmética
sobre dicts: µs por tarjeta. Nada de acá toca la red ni el disco.

Tarjetas de bonos: una por segmento soberano con las columnas que pidió el
desk — último · var · var % · TIR · Δ TIR (bps, TIR al último vs TIR al
cierre previo, el `delta_yield_bps` de la fila) · TEM · margen (sólo si el
segmento lo tiene: floaters y la pata TAMAR de los duales). Para que la página
quede sintética cada tarjeta muestra hasta `MAX_FILAS` bonos: los más operados
hoy (VN; sin VN, efectivo) completados con los de vencimiento más corto, y el
resultado ordenado por vencimiento; el pie dice cuántos quedaron afuera y
linkea a la curva completa. Con ≤ MAX_FILAS bonos en el segmento se muestran
todos.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Dict, Iterable, List, Optional, Tuple

from backend.services import cauciones, dolares, equities, futuros, historico, mae, riesgo_pais

logger = logging.getLogger("backend.inicio")

MAX_FILAS = 10
# (key de la tarjeta, título, subtítulo). La key es la curva de Mercado salvo
# "duales", que junta las patas BASE de los tres tipos de dual (fija / CER /
# DLK: `DUALES_BASE`) y les cruza el margen de la pata TAMAR (`dualtamar`,
# que valúa el código base con el sufijo 'v').
TARJETAS_BONOS: Tuple[Tuple[str, str, str], ...] = (
    ("globales", "Globales", "ley Nueva York · USD"),
    ("bonares", "Bonares", "ley argentina · USD"),
    ("cer", "CER", "soberanos ajustados por inflación"),
    ("lecap", "Tasa fija", "LECAP · BONCAP · tasa fija ARS"),
    ("dolarlinked", "Dólar linked", "soberanos A3500"),
    ("tamar", "TAMAR", "soberanos tasa variable · margen s/ TAMAR"),
    ("duales", "Duales", "pata base fija · CER · DLK · margen TAMAR"),
)
DUALES_BASE: Tuple[str, ...] = ("dualfija", "dualcer", "dualdlk")
# Las curvas que hay que armar para las tarjetas.
CURVAS_NECESARIAS: Tuple[str, ...] = tuple(k for k, _, _ in TARJETAS_BONOS if k != "duales") \
    + DUALES_BASE + ("dualtamar",)
MAX_FUTUROS = 12
MAX_LIDERES = 24


def _f(v: Any) -> Optional[float]:
    """float finito o None (NaN / inf / texto / None → None)."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _safe(label: str, fn, default: Any) -> Any:
    try:
        return fn()
    except Exception:  # noqa: BLE001 — una fuente caída no tira la página
        logger.exception("[inicio] %s falló; degradado", label)
        return default


# Topes de lectura: una métrica más allá de esto sale de un precio basura (una
# TIR de 1e+20 % no es dato, es ruido) y acá se muestra "—". Curvas / Mercado
# siguen mostrando el valor crudo; el tablero prioriza quedar legible.
_LIM = {"tirea": 5.0, "tem": 1.0, "margen": 5.0, "delta_tir_bps": 1e5}


def _acotado(v: Any, lim: float) -> Optional[float]:
    x = _f(v)
    return x if x is not None and abs(x) <= lim else None


# ── bonos por segmento ───────────────────────────────────────────────────────
def _fila(r: Dict[str, Any], margen: Optional[float] = None) -> Dict[str, Any]:
    """Proyección de una fila de curva a lo que muestra la tarjeta."""
    m = margen if margen is not None else r.get("margen_tna")
    return {
        "code": r.get("code"),
        "nombre": r.get("nombre") or r.get("code"),
        "last": _f(r.get("last")),
        "last_cls": r.get("last_cls") or "",
        "var_px": _f(r.get("var_px")),
        "var_pct": _f(r.get("var_pct")),                 # en pp (como Mercado)
        "tirea": _acotado(r.get("tirea"), _LIM["tirea"]),                      # fracción
        "delta_tir_bps": _acotado(r.get("delta_yield_bps"), _LIM["delta_tir_bps"]),  # TIR(último) − TIR(cierre), bps
        "tem": _acotado(r.get("tem"), _LIM["tem"]),                            # fracción
        "margen": _acotado(m, _LIM["margen"]),                                 # fracción (NaN → None)
        "duration": _f(r.get("duration")),
        "vencimiento": r.get("vencimiento"),
        "nominal": _f(r.get("nominal")),
        "volume": _f(r.get("volume")),
    }


def _orden_vto(f: Dict[str, Any]) -> tuple:
    v = f.get("vencimiento")
    to_ord = getattr(v, "toordinal", None)
    if callable(to_ord):
        try:
            return (0, float(to_ord()), str(f.get("code") or ""))
        except Exception:  # noqa: BLE001
            pass
    d = f.get("duration")
    if d is not None:
        return (1, float(d), str(f.get("code") or ""))
    return (2, 0.0, str(f.get("code") or ""))


def _operado(f: Dict[str, Any]) -> float:
    return f.get("nominal") or f.get("volume") or 0.0


def seleccionar(filas: List[Dict[str, Any]], max_filas: int = MAX_FILAS) -> List[Dict[str, Any]]:
    """Hasta `max_filas` bonos: los más operados hoy, completados con los de
    vencimiento más corto; el resultado ordenado por vencimiento. Con pocas
    filas, todas (por vencimiento)."""
    if len(filas) <= max_filas:
        return sorted(filas, key=_orden_vto)
    con_vol = sorted((f for f in filas if _operado(f) > 0), key=lambda f: -_operado(f))
    sel = con_vol[:max_filas]
    if len(sel) < max_filas:
        ids = {id(f) for f in sel}
        resto = sorted((f for f in filas if id(f) not in ids), key=_orden_vto)
        sel += resto[:max_filas - len(sel)]
    return sorted(sel, key=_orden_vto)


def tarjetas_bonos(rows_by: Dict[str, List[Dict[str, Any]]],
                   max_filas: int = MAX_FILAS) -> Dict[str, Dict[str, Any]]:
    """{key: tarjeta} con las filas elegidas de cada segmento. `rows_by` son las
    filas de `routes.curves._rows_en_seq` por curva (las mismas de Mercado)."""
    # Margen de la pata TAMAR de los duales: la curva dualtamar valúa el código
    # base con el sufijo 'v' (TTD26 → TTD26v); se cruza por el base.
    margen_dual: Dict[str, float] = {}
    for r in rows_by.get("dualtamar") or []:
        c = str(r.get("code") or "")
        m = _f(r.get("margen_tna"))
        if c and m is not None:
            margen_dual[c[:-1] if c.endswith("v") else c] = m
    out: Dict[str, Dict[str, Any]] = {}
    for key, titulo, sub in TARJETAS_BONOS:
        if key == "duales":
            # Un dual por fila (su pata base; el mismo código no se repite
            # aunque esté en dos curvas) con el margen TAMAR de su variante 'v'.
            vistos: set = set()
            filas = []
            for k in DUALES_BASE:
                for r in rows_by.get(k) or []:
                    c = str(r.get("code") or "")
                    if c in vistos:
                        continue
                    vistos.add(c)
                    filas.append(_fila(r, margen_dual.get(c)))
        else:
            filas = [_fila(r) for r in rows_by.get(key) or []]
        sel = seleccionar(filas, max_filas)
        out[key] = {"key": key, "titulo": titulo, "sub": sub, "filas": sel,
                    "total": len(filas), "ocultas": len(filas) - len(sel),
                    "margen": any(f["margen"] is not None for f in sel)}
    return out


# ── tarjetas KPI ─────────────────────────────────────────────────────────────
# Cada fila KPI: {label, sub, fmt, value, …} con
#   fmt = "num" (precio, ar_num 2) | "int" (nivel, ar_num 0) |
#         "pct" (fracción → ar_pct) | "pp" (ya en %, ar_pct_pp)
#   var_px / var_pct  → variación en unidades del valor y en fracción
#   var_pp            → variación en PUNTOS porcentuales (brecha, canje, tasas)
def _var_px_desde_pct(last: Optional[float], var_pct: Optional[float]) -> Optional[float]:
    if last is None or var_pct is None or var_pct <= -1.0:
        return None
    return last - last / (1.0 + var_pct)


def _fecha_ar(s: Any) -> Optional[str]:
    """'AAAA-MM-DD[…]' → 'DD/MM/AAAA'; cualquier otra cosa pasa tal cual."""
    t = str(s or "")
    if len(t) >= 10 and t[4] == "-" and t[7] == "-":
        return f"{t[8:10]}/{t[5:7]}/{t[0:4]}"
    return t or None


def tipos_de_cambio(summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    ofi = summary.get("oficial") or {}
    last, close = _f(ofi.get("last")), _f(ofi.get("close"))
    rows: List[Dict[str, Any]] = [{
        "label": f"Oficial · {ofi.get('source') or '—'}",
        "sub": "mayorista" if ofi.get("source") == "SIOPEL" else _fecha_ar(ofi.get("date")),
        "fmt": "num", "value": last,
        "var_px": (last - close) if (last is not None and close) else None,
        "var_pct": _f(ofi.get("var_pct")),
    }]
    for key, label in (("usb", "USD MEP"), ("usd", "USD CCL")):
        leg = summary.get(key) or {}
        v, vp = _f(leg.get("last")), _f(leg.get("var_pct"))
        rows.append({"label": label, "sub": leg.get("base") or None, "fmt": "num", "value": v,
                     "var_px": _var_px_desde_pct(v, vp), "var_pct": vp})
    bvar = _f(summary.get("brecha_var_pp"))
    rows.append({"label": "Brecha", "sub": "CCL / oficial", "fmt": "pct",
                 "value": _f(summary.get("brecha")),
                 "var_pp": bvar * 100.0 if bvar is not None else None})
    cj = summary.get("canje") or {}
    cvar = _f(cj.get("var_pct"))                     # Δ del canje (fracción) vs cierre
    rows.append({"label": "Canje", "sub": f"CCL / MEP · {cj['base']}" if cj.get("base") else "CCL / MEP",
                 "fmt": "pct", "value": _f(cj.get("last")),
                 "var_pp": cvar * 100.0 if cvar is not None else None})
    return rows


def _es_usd(moneda: Any) -> bool:
    m = str(moneda or "").upper()
    return any(t in m for t in ("USD", "U$S", "US$", "DOLAR", "DÓLAR"))


def _mae_pick(rows: Iterable[Dict[str, Any]], usd: bool) -> Optional[Dict[str, Any]]:
    """Caución MAE más corta con tasa, de la moneda pedida (las filas vienen
    ordenadas por plazo)."""
    for r in rows:
        if _es_usd(r.get("moneda")) != usd:
            continue
        if _f(r.get("tasa")) is not None:
            return r
    return None


def tasas() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    macro = {m["key"]: m for m in _safe("macro_snapshot", historico.macro_snapshot, [])}
    for k, label in (("tamar", "TAMAR"), ("badlar", "BADLAR")):
        m = macro.get(k)
        rows.append({"label": label, "sub": f"BCRA · {m['date']}" if m else None, "fmt": "pp",
                     "value": _f(m.get("value")) if m else None,
                     "var_pp": None, "aplicable": _f(m.get("aplicable")) if m else None})
    for moneda, label in (("PESOS", "Caución ARS · BYMA"), ("DOLAR", "Caución USD · BYMA")):
        p = _safe(f"rail_pick {moneda}", lambda moneda=moneda: cauciones.rail_pick(moneda), None)
        sub = None
        if p:
            sub = str(p.get("plazo") or "") + (" · cierre previo" if p.get("es_cierre") else "")
        rows.append({"label": label, "sub": sub or None, "fmt": "pp",
                     "value": _f(p.get("tasa")) if p else None,
                     "var_pp": _f(p.get("var")) if p else None})      # ya en puntos de TNA
    mae_rows = _safe("mae.cauciones_rows", mae.cauciones_rows, [])
    for usd, label in ((False, "Caución ARS · MAE"), (True, "Caución USD · MAE")):
        p = _mae_pick(mae_rows, usd)
        t, tc = (_f(p.get("tasa")), _f(p.get("tasa_cierre"))) if p else (None, None)
        plazo = str(p.get("plazo") or "").lstrip("0") if p else ""
        rows.append({"label": label, "sub": f"{plazo or '0'} día{'s' if plazo not in ('', '1') else ''}" if p else None,
                     "fmt": "pp", "value": t,
                     "var_pp": (t - tc) if (t is not None and tc is not None) else None})
    return rows


def mercado(summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    mv = _safe("merval_row", equities.merval_row, None) or {}
    last, close = _f(mv.get("last")), _f(mv.get("close"))
    vpct = _f(mv.get("var_pct"))
    rows.append({"label": "MERVAL", "sub": "ARS", "fmt": "int", "value": last,
                 "var_px": (last - close) if (last is not None and close) else None,
                 "var_pct": vpct / 100.0 if vpct is not None else None})
    usd = summary.get("usd") or {}
    ccl, ccl_vp = _f(usd.get("last")), _f(usd.get("var_pct"))
    v_ccl = px_ccl = vp_ccl = None
    if last is not None and ccl:
        v_ccl = last / ccl
        if close and ccl_vp is not None and ccl_vp > -1.0:
            close_ccl = close / (ccl / (1.0 + ccl_vp))
            px_ccl = v_ccl - close_ccl
            vp_ccl = v_ccl / close_ccl - 1.0 if close_ccl else None
    rows.append({"label": "MERVAL", "sub": f"en CCL · {usd.get('base')}" if usd.get("base") else "en CCL",
                 "fmt": "int", "value": v_ccl, "var_px": px_ccl, "var_pct": vp_ccl})
    rp = _safe("riesgo_pais", riesgo_pais.snapshot, {}) or {}
    rows.append({"label": "Riesgo país", "sub": f"EMBI · {rp['fecha']}" if rp.get("fecha") else "EMBI",
                 "fmt": "int", "value": _f(rp.get("valor")),
                 "var_px": _f(rp.get("var")), "var_pct": _f(rp.get("var_pct"))})
    for code in ("SPY", "EWZ"):
        r = _safe(f"row_for {code}", lambda code=code: equities.row_for(code), None) or {}
        vp = _f(r.get("var_pct"))
        rows.append({"label": code, "sub": "CEDEAR · ARS", "fmt": "num", "value": _f(r.get("last")),
                     "var_px": _f(r.get("var_px")), "var_pct": vp / 100.0 if vp is not None else None})
    return rows


def futuros_rows(max_n: int = MAX_FUTUROS) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in _safe("futuros.rows", lambda: futuros.rows("may"), []):
        if r.get("dias") is not None and r["dias"] < 0:
            continue
        out.append({"code": r.get("code"), "label": r.get("label"), "dias": r.get("dias"),
                    "last": _f(r.get("last")), "var_pct": _f(r.get("var_pct")),
                    "tna": _f(r.get("tna")), "tem": _f(r.get("tem")), "td": _f(r.get("td"))})
        if len(out) >= max_n:
            break
    return out


def lideres(max_n: int = MAX_LIDERES) -> List[Dict[str, Any]]:
    rows = _safe("panel_rows lideres", lambda: equities.panel_rows("lideres"), [])
    return [{"code": r.get("code"), "last": _f(r.get("last")), "var_pct": _f(r.get("var_pct")),
             "volume": _f(r.get("volume")), "indice": bool(r.get("indice"))}
            for r in rows[:max_n]]


def resumen(plazo: str = "24hs") -> Dict[str, Any]:
    """Todo lo que NO son las filas de curvas (que vienen del cache async de
    Mercado). Sincrónico, µs; nunca lanza."""
    summary = _safe("dolares.summary", lambda: dolares.summary(plazo), None) or dolares._summary_default(plazo)
    # `tc` y no `fx`: en el template `fx` es el módulo de macros (_fx_macros).
    return {"plazo": plazo, "tc": tipos_de_cambio(summary), "tasas": tasas(),
            "mercado": mercado(summary), "futuros": futuros_rows(), "lideres": lideres()}
