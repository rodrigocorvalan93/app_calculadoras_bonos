"""Futuros de dólar (DLR) — tasas implícitas (mayorista/minorista) + un panel
de los Dólar Linked soberanos con su tasa SINTÉTICA contra el futuro más cercano
a la duration de cada bono.

Lee todo de cache (store + official_fx + curva DLK) → sub-50 ms.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from backend.locale_ar import hoy_ba, parse_ar_num
from backend.services import bond_universe, dolares, futuros as fut, marketdata_store
from backend.cache_seq import seq_cached

logger = logging.getLogger("backend.futuros")

router = APIRouter(tags=["futuros"])


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, template, ctx)


def _parse_num(s: Optional[str]) -> Optional[float]:
    """Override de spot, positivo. Usa el parser es-AR canónico: antes '1.435'
    (miles) daba 1,435 → spot 1000× chico y todas las tasas implícitas mal."""
    v = parse_ar_num(s)
    return v if (v is not None and v > 0) else None


def _bond_tna(tirea: float, freq: float = 90.0, base: float = 365.0) -> float:
    """TNA del DLK desde su TIREA (convención 90/365)."""
    return ((1.0 + tirea) ** (freq / base) - 1.0) * (base / freq)


async def _ctx(spot_override: str = "") -> Dict[str, Any]:
    bond_universe.ensure_loaded()
    sp_over = _parse_num(spot_override)
    may_rows = fut.rows("may", sp_over)
    min_rows = fut.rows("min", sp_over)
    spot = sp_over if sp_over else fut.spot()
    near = next((r for r in may_rows if r["dias"] and r["dias"] > 0 and r["tna"] is not None), None) \
        or next((r for r in min_rows if r["dias"] and r["dias"] > 0 and r["tna"] is not None), None)

    # Curvas DLK + Todos ARS en paralelo (cada una usa el threadpool por dentro).
    try:
        from backend.routes.curves import _rows_for
        dlk_rows, ars_rows = await asyncio.gather(
            _rows_for("dolarlinked", "24hs", False, "native"),
            _rows_for("todos_ars_proyectado", "24hs", False, "native"),
        )
        dlk_rows, ars_rows = dlk_rows[0], ars_rows[0]
    except Exception:  # noqa: BLE001
        # visible en el log: sin esto, un fallo de pricing dejaba los dos
        # paneles de sintéticos vacíos y se leía como 'no hay datos'.
        logger.exception("[futuros] curvas DLK/ARS fallaron — paneles de sintéticos vacíos")
        dlk_rows, ars_rows = [], []

    matchable = [r for r in may_rows if r["dias"] and r["dias"] > 0 and r.get("td") is not None]

    def _match(dur: Optional[float]):
        if not matchable or not dur:
            return None
        m = min(matchable, key=lambda f: abs(f["dias"] - dur * 365.0))
        return m, (1.0 + m["td"]) ** (365.0 / m["dias"]) - 1.0   # (futuro, TEA implícita)

    # 1) DLK soberanos → sintético PESO: (1+TIR_bono)·(1+TEA_fut)−1 ; TNA_bono + TNA_fut.
    dlk: List[Dict[str, Any]] = []
    for r in dlk_rows:
        tirea, dur = r.get("tirea"), r.get("duration")
        if tirea is None:
            continue
        b: Dict[str, Any] = {"code": r["code"], "tirea": tirea, "duration": dur, "last": r.get("last")}
        mm = _match(dur)
        if mm:
            m, tea_fut = mm
            b.update({"fut_label": m["label"], "fut_code": m["code"], "fut_tna": m["tna"], "fut_tea": tea_fut,
                      "tir_sint": (1.0 + tirea) * (1.0 + tea_fut) - 1.0,
                      "tna_sint": (_bond_tna(tirea) + m["tna"]) if m["tna"] is not None else None})
        dlk.append(b)
    dlk.sort(key=lambda x: (x["duration"] if x["duration"] is not None else 9999.0))

    # 2) Curva ARS (≤1.5y dur) → sintético DÓLAR LINKED (al revés): le sacamos la
    #    deval del futuro. TIR sint = (1+TIR_ars)/(1+TEA_fut)−1 ; TNA sint = TNA_ars − TNA_fut.
    ars: List[Dict[str, Any]] = []
    for r in ars_rows:
        tirea, dur, tna = r.get("tirea"), r.get("duration"), r.get("tna")
        if tirea is None or dur is None or dur > 1.5:
            continue
        a: Dict[str, Any] = {"code": r["code"], "tirea": tirea, "tna": tna, "duration": dur, "last": r.get("last")}
        mm = _match(dur)
        if mm:
            m, tea_fut = mm
            a.update({"fut_label": m["label"], "fut_tna": m["tna"], "fut_tea": tea_fut,
                      "tir_sint": (1.0 + tirea) / (1.0 + tea_fut) - 1.0,
                      "tna_sint": (tna - m["tna"]) if (tna is not None and m["tna"] is not None) else None})
        ars.append(a)
    ars.sort(key=lambda x: x["duration"])

    # Gráficos: curva de TNA implícita + sendero de deva mensual. Sobre el
    # mayorista (referencia); si está frío, caen al minorista.
    base_rows, charts_canal = may_rows, "mayorista (DLR/…M)"
    if not any(r.get("tna") is not None for r in may_rows):
        base_rows, charts_canal = min_rows, "minorista (DLR/…)"
    # Variación del oficial para la strip — sólo sin override (la var es DEL
    # oficial; al lado de un spot manual sería engañosa).
    spot_var = None if sp_over else (dolares.official_fx() or {}).get("var_pct")
    oi_may = sum(r["oi"] for r in may_rows if r.get("oi"))
    oi_min = sum(r["oi"] for r in min_rows if r.get("oi"))
    return {"may_rows": may_rows, "min_rows": min_rows, "spot": spot, "near": near,
            "dlk": dlk, "ars": ars, "spot_override": spot_override or "",
            "spot_var": spot_var, "oi_may": oi_may, "oi_min": oi_min,
            "curve_chart": fut.rate_curve_chart(base_rows),
            "deva_chart": fut.deva_path_chart(base_rows, spot),
            "charts_canal": charts_canal}


@router.get("/futuros", response_class=HTMLResponse)
async def futuros_page(request: Request, spot_override: str = "") -> HTMLResponse:
    return _render(request, "futuros.html", **(await _ctx(spot_override)))


@router.get("/futuros/table", response_class=HTMLResponse)
@seq_cached(ttl=2.0)          # partial live (md-update): 1 build por tick
async def futuros_table(request: Request, spot_override: str = "") -> HTMLResponse:
    return _render(request, "partials/futuros_table.html", **(await _ctx(spot_override)))


@router.get("/futuros/book", response_class=HTMLResponse)
@seq_cached(ttl=2.0)          # se auto-refresca con md-update: 1 build por tick
async def futuros_book(request: Request, code: str = "", spot_override: str = "") -> HTMLResponse:
    """Libro de un contrato a paridad del de Mercado: stats completas del día
    (last / var vs ajuste / open / mín / máx / volumen / OI) + profundidad con
    acumulado y la TNA IMPLÍCITA por nivel — la columna donde en bonos va la
    TIR. Vive: el card se re-renderiza con el motor md-update."""
    store = marketdata_store.get_store()
    snap = store.get(code)
    sp = _parse_num(spot_override) or fut.spot()
    vto = fut._parse_vto(code)
    dias = (vto - hoy_ba()).days if vto else None

    def impl(px):
        return fut._impl(px, sp, dias)      # (deva td, TNA, TEM)

    def levels(raw):
        out, cum = [], 0.0
        for lvl in (raw or []):
            px, sz = lvl.get("price"), lvl.get("size")
            cum += (sz or 0.0)
            out.append({"price": px, "size": sz, "cum": cum, "tna": impl(px)[1]})
        total = cum
        for lvl in out:                     # fracción → degradé de profundidad
            lvl["frac"] = (lvl["cum"] / total) if total > 0 else 0.0
        return out

    last = snap.last if snap else None
    close = snap.close if snap else None
    var_pct = None
    try:
        if last is not None and close not in (None, 0):
            var_pct = (last / close - 1.0) * 100.0
    except (TypeError, ZeroDivisionError):
        var_pct = None
    td_last, tna_last, tem_last = impl(last)
    return _render(request, "partials/futuros_book.html",
                   code=code, label=fut._label(code), snap=snap, dias=dias, spot=sp,
                   vto=vto.isoformat() if vto else None,
                   spot_override=spot_override or "", var_pct=var_pct,
                   bids=levels(snap.bids if snap else None),
                   offers=levels(snap.offers if snap else None),
                   td_last=td_last, tna_last=tna_last, tem_last=tem_last,
                   tna_close=impl(close)[1],
                   tna_low=impl(snap.low if snap else None)[1],
                   tna_high=impl(snap.high if snap else None)[1],
                   volume=(snap.volume if snap.volume is not None else snap.nominal) if snap else None)
