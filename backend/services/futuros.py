"""Futuros de dólar (DLR ROFEX) — tasas implícitas vs spot A3500.

Símbolos crudos generados dinámicamente: `DLR/MMMYY` (minorista) y `DLR/MMMYYM`
(mayorista), leídos del store (mismo WS que todo lo demás; igual que DLR/SPOT).

OJO nomenclatura: ROFEX/A3 abrevia el mes en ESPAÑOL — ENE, ABR, AGO y DIC
difieren del inglés (JAN/APR/AUG/DEC). Con la tira generada en inglés esos 4
meses nunca matcheaban un símbolo real del broker y desaparecían de la tabla
(el AGO en curso operando, sin ir más lejos). Generamos en español y además
aceptamos/sembramos el alias inglés (data persistida vieja / robustez).

Tasa implícita de cada contrato vs el spot oficial (A3500), como en el OMSweb_app:
    td  = precio / spot − 1                 (devaluación implícita al vto)
    TNA = td · 365 / días                   (lineal)
    TEA = (1 + td · 30/días) ^ 12 − 1       (mensual capitalizada → anual)
    TEM = (1 + TEA) ^ (1/12) − 1
Sólo lee de cache → sub-50 ms.
"""
from __future__ import annotations

import math
import re
from calendar import monthrange
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from backend.locale_ar import hoy_ba
from backend.services import dolares, marketdata_store

# Nomenclatura ROFEX/A3: mes en español. 8 de 12 coinciden con el inglés;
# ENE/ABR/AGO/DIC no (y con JAN/APR/AUG/DEC el broker rechaza el símbolo).
_MES = {1: "ENE", 2: "FEB", 3: "MAR", 4: "ABR", 5: "MAY", 6: "JUN",
        7: "JUL", 8: "AGO", 9: "SEP", 10: "OCT", 11: "NOV", 12: "DIC"}
_MES_EN = {1: "JAN", 4: "APR", 8: "AUG", 12: "DEC"}   # alias inglés (≠ español)
_MES_INV = {v: k for k, v in _MES.items()}
_MES_INV.update({v: k for k, v in _MES_EN.items()})
_N_MONTHS = 14
_MES_ES = {1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
           7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic"}
_DIAS_MES = 30.4375   # 365.25/12 — mes promedio para normalizar TEM por tramo


def symbols(canal: str = "may", n_months: int = _N_MONTHS) -> List[str]:
    """DLR/MMMYY (minorista) o DLR/MMMYYM (mayorista), desde el mes actual."""
    suf = "M" if canal == "may" else ""
    today = hoy_ba()   # el mes "actual" de la tira es el de BA, no el del server
    y, m = today.year, today.month
    out: List[str] = []
    for _ in range(n_months):
        out.append(f"DLR/{_MES[m]}{y % 100:02d}{suf}")
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def _parse_vto(code: str) -> Optional[date]:
    """'DLR/AGO26' / 'DLR/AGO26M' (o alias 'DLR/AUG26') → último día del mes."""
    m = re.match(r"^DLR/([A-Z]{3})(\d{2})M?$", str(code).strip().upper())
    if not m:
        return None
    mes = _MES_INV.get(m.group(1))
    if not mes:
        return None
    yy = 2000 + int(m.group(2))
    return date(yy, mes, monthrange(yy, mes)[1])


def _alias(code: str) -> Optional[str]:
    """El mismo contrato en el otro idioma ('DLR/AGO26M' ⇄ 'DLR/AUG26M') para
    los 4 meses que difieren; None si no aplica. Sirve para leer data vieja
    persistida con el código inglés y para sembrar ambos en el WS (el broker
    descarta el inexistente)."""
    m = re.match(r"^DLR/([A-Z]{3})(\d{2})(M?)$", str(code).strip().upper())
    if not m:
        return None
    mes = _MES_INV.get(m.group(1))
    if mes not in _MES_EN:
        return None
    other = _MES_EN[mes] if m.group(1) == _MES[mes] else _MES[mes]
    return f"DLR/{other}{m.group(2)}{m.group(3)}"


def _label(code: str) -> str:
    v = _parse_vto(code)
    return f"{_MES_ES[v.month]}-{v.year % 100:02d}" if v else code


def spot() -> Optional[float]:
    """Spot mayorista de referencia (oficial A3500/SIOPEL)."""
    o = dolares.official_fx() or {}
    s = o.get("last")
    try:
        return float(s) if s and float(s) > 0 else None
    except (TypeError, ValueError):
        return None


def _impl(px: Optional[float], sp: Optional[float], dias: Optional[int]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """(devaluación td, TNA, TEM) implícitas de un precio de futuro vs spot."""
    if px is None or not sp or not dias or dias <= 0:
        return None, None, None
    try:
        td = px / sp - 1.0
        tna = td * 365.0 / dias
        tea = (1.0 + td * 30.0 / dias) ** 12 - 1.0
        tem = (1.0 + tea) ** (1.0 / 12.0) - 1.0
        return td, tna, tem
    except (ValueError, ZeroDivisionError, OverflowError):
        return None, None, None


def rows(canal: str = "may", spot_v: Optional[float] = None) -> List[Dict[str, Any]]:
    """Filas de futuros con su tasa implícita, ordenadas por vencimiento.
    `spot_v` overridea el spot oficial (para el input de la pestaña)."""
    store = marketdata_store.get_store()
    sp = spot_v if (spot_v and spot_v > 0) else spot()
    today = hoy_ba()   # días al vto en fecha BA: naive restaba 1 día de más de noche (TNA implícita sesgada)
    out: List[Dict[str, Any]] = []
    for sym in symbols(canal):
        snap = store.get(sym)
        alias = _alias(sym)
        if alias:
            alt = store.get(alias)
            if alt is not None and (snap is None or (alt.updated_at or 0) >= (snap.updated_at or 0)):
                snap = alt
        if snap is None:
            continue
        last, bid, offer, close = snap.last, snap.bid, snap.offer, snap.close
        if last is None and bid is None and offer is None:
            continue
        vto = _parse_vto(sym)
        dias = (vto - today).days if vto else None
        td, tna_last, tem_last = _impl(last, sp, dias)
        _, tna_bid, _ = _impl(bid, sp, dias)
        _, tna_off, _ = _impl(offer, sp, dias)
        tea = None                                   # TIR efectiva anual directa
        if td is not None and dias and dias > 0 and td > -1.0:
            try:
                tea = (1.0 + td) ** (365.0 / dias) - 1.0
            except (ValueError, OverflowError, ZeroDivisionError):
                tea = None
        var = None
        try:
            if last is not None and close not in (None, 0):
                var = last / close - 1.0
        except (TypeError, ZeroDivisionError):
            var = None
        out.append({
            # code = el símbolo que REALMENTE tiene data (canónico o alias):
            # el click a /futuros/book lo usa como key del store tal cual.
            "code": snap.symbol, "label": _label(sym), "vto": vto.isoformat() if vto else None,
            "dias": dias, "last": last, "bid": bid, "offer": offer, "close": close,
            "bid_size": snap.bid_size, "offer_size": snap.offer_size,
            "var_pct": var, "td": td, "tna": tna_last, "tea": tea, "tem": tem_last,
            "tna_bid": tna_bid, "tna_offer": tna_off,
            # ROFEX no siempre publica EV: el volumen cae al NV (nominal
            # acumulado, contratos) para no mostrar "—" con mercado operando.
            "volume": snap.volume if snap.volume is not None else snap.nominal,
            "oi": snap.open_interest,
        })
    out.sort(key=lambda r: (r["dias"] if r["dias"] is not None else 9999))
    return out


def nearest(canal: str = "may") -> Optional[Dict[str, Any]]:
    """Contrato más cercano con tasa implícita (para el panel DLK)."""
    for r in rows(canal):
        if r["dias"] and r["dias"] > 0 and r["tna"] is not None:
            return r
    return None


def all_symbols() -> List[str]:
    """Para sembrar en el WS (minorista + mayorista). Incluye el alias inglés
    de los meses que difieren: el broker rechaza el que no existe (el WS lo
    descarta solo) y el que sí existe alimenta la misma fila (ver rows)."""
    out: List[str] = []
    for s in symbols("min") + symbols("may"):
        out.append(s)
        a = _alias(s)
        if a:
            out.append(a)
    return out


# ── Gráficos (geometría SVG server-side; el template sólo dibuja) ────────────

def _nice_ticks(lo: float, hi: float, n: int = 5) -> List[float]:
    """Ticks 'lindos' (1/2/2.5/5 × 10^k) dentro de [lo, hi]."""
    span = hi - lo
    if span <= 0 or not math.isfinite(span):
        return [lo]
    raw = span / max(1, n)
    step = 10.0 ** math.floor(math.log10(raw))
    for mult in (1.0, 2.0, 2.5, 5.0, 10.0):
        if step * mult >= raw:
            step *= mult
            break
    out: List[float] = []
    v = math.ceil(lo / step) * step
    while v <= hi + step * 1e-6:
        out.append(round(v, 10))
        v += step
    return out


# El front a días de vencer anualiza ruido (±1 peso vs spot ÷ 2 días →
# ±cientos de % de TNA) y aplasta la escala: fuera de los GRÁFICOS con menos
# de esta cantidad de días (la tabla sigue mostrando todo).
_MIN_DIAS_CHART = 3


def rate_curve_chart(rws: List[Dict[str, Any]], *, width: int = 880,
                     height: int = 280) -> Optional[Dict[str, Any]]:
    """Curva de TNA implícita por contrato: x = días al vto (escala real de
    tiempo, 0 = hoy), y = TNA (fracción; el template formatea con ar_pct)."""
    pts = [r for r in (rws or [])
           if r.get("tna") is not None and r.get("dias") and r["dias"] >= _MIN_DIAS_CHART]
    if len(pts) < 2:
        return None
    pts = sorted(pts, key=lambda r: r["dias"])
    xmax = pts[-1]["dias"] * 1.03
    ys = [r["tna"] for r in pts]
    ymin, ymax = min(ys), max(ys)
    yspan = (ymax - ymin) or 0.01
    ymin -= yspan * 0.12
    ymax += yspan * 0.12
    pad_l, pad_r, pad_t, pad_b = 54, 14, 12, 46
    plot_w, plot_h = width - pad_l - pad_r, height - pad_t - pad_b

    def X(d: float) -> float:
        return round(pad_l + d / xmax * plot_w, 2)

    def Y(v: float) -> float:
        return round(pad_t + (ymax - v) / (ymax - ymin) * plot_h, 2)

    nodes = [{"cx": X(r["dias"]), "cy": Y(r["tna"]), "label": r["label"],
              "dias": r["dias"], "tna": r["tna"], "tem": r.get("tem"),
              "px": r.get("last")} for r in pts]
    return {
        "w": width, "h": height, "x0": pad_l, "x1": width - pad_r,
        "y0": pad_t, "y1": height - pad_b, "xlabel_y": height - pad_b + 15,
        "poly": " ".join(f"{n['cx']},{n['cy']}" for n in nodes), "nodes": nodes,
        "yticks": [{"v": v, "y": Y(v)} for v in _nice_ticks(ymin, ymax, 5)],
    }


def deva_path_chart(rws: List[Dict[str, Any]], spot_v: Optional[float], *,
                    width: int = 880, height: int = 250) -> Optional[Dict[str, Any]]:
    """Sendero de devaluación mensual implícita: barras con la TEM del tramo
    entre cada contrato y el anterior (el primero, contra el spot). Cada tramo
    se normaliza a mes de 30,44 días — el stub del mes en curso no distorsiona
    y un contrato faltante se promedia (geométrico) en la barra siguiente.
    Precio del contrato: last → mid(bid/offer) → close."""
    if not spot_v or spot_v <= 0:
        return None
    segs: List[Dict[str, Any]] = []
    prev_d, prev_px = 0.0, float(spot_v)
    ordered = sorted((r for r in rws or []
                      if r.get("dias") and r["dias"] >= _MIN_DIAS_CHART),
                     key=lambda r: r["dias"])
    for r in ordered:
        px = r.get("last")
        if px is None and r.get("bid") is not None and r.get("offer") is not None:
            px = (r["bid"] + r["offer"]) / 2.0
        if px is None:
            px = r.get("close")
        if not px or px <= 0:
            continue
        dd = r["dias"] - prev_d
        if dd <= 0:
            continue
        try:
            tem = (px / prev_px) ** (_DIAS_MES / dd) - 1.0
        except (ValueError, ZeroDivisionError, OverflowError):
            continue
        segs.append({"label": r["label"], "val": tem, "dias": int(dd), "px": px})
        prev_d, prev_px = float(r["dias"]), float(px)
    if not segs:
        return None
    # TEM promedio del sendero: la tasa mensual CONSTANTE que compone al mismo
    # punto final (geométrica spot → último contrato). Cae dentro del rango de
    # las barras, así que no altera la escala.
    try:
        avg_val = (prev_px / float(spot_v)) ** (_DIAS_MES / prev_d) - 1.0
    except (ValueError, ZeroDivisionError, OverflowError):
        avg_val = None
    vals = [s["val"] for s in segs]
    ymin, ymax = min(0.0, min(vals)), max(0.0, max(vals))
    span = (ymax - ymin) or 0.01
    ymax += span * 0.16                      # aire para el label sobre la barra
    if ymin < 0:
        ymin -= span * 0.10
    pad_l, pad_r, pad_t, pad_b = 54, 14, 10, 46
    plot_w, plot_h = width - pad_l - pad_r, height - pad_t - pad_b

    def Y(v: float) -> float:
        return round(pad_t + (ymax - v) / (ymax - ymin) * plot_h, 2)

    slot = plot_w / len(segs)
    bw = min(44.0, slot * 0.62)
    bars: List[Dict[str, Any]] = []
    for i, s in enumerate(segs):
        cx = round(pad_l + slot * (i + 0.5), 2)
        y_top, y_bot = Y(max(s["val"], 0.0)), Y(min(s["val"], 0.0))
        bars.append({**s, "cx": cx, "x": round(cx - bw / 2.0, 2),
                     "w": round(bw, 2), "y": y_top,
                     "h": round(max(y_bot - y_top, 0.75), 2),
                     "label_y": (y_top - 5) if s["val"] >= 0 else (y_bot + 12)})
    return {"w": width, "h": height, "x0": pad_l, "x1": width - pad_r, "y0": pad_t,
            "zero_y": Y(0.0), "xlabel_y": height - pad_b + 15, "bars": bars,
            "avg": ({"val": avg_val, "y": Y(avg_val)} if avg_val is not None else None),
            "yticks": [{"v": v, "y": Y(v)} for v in _nice_ticks(ymin, ymax, 4)]}
