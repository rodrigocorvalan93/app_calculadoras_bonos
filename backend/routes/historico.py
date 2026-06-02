"""Históricos — series macro del BCRA + histórico de tasas por curva (BYMA).

Macro: cache del json (lectura única; refresh explícito), line chart SVG.
Curvas: Excel local pre-indexado en `services.historico_byma`. La primera
lectura del Excel (~3-4 s, 20k+ filas) se hace en un threadpool para no
bloquear el event loop; después es cache en memoria.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from backend.services import historico, historico_byma

router = APIRouter(tags=["historicos"])

_RANGOS = {"1m": 30, "3m": 90, "6m": 180, "1a": 365, "3a": 1095, "5a": 1825, "todo": None}
# paleta para las líneas de la vista "tasas por curva" (una por bono)
_PALETTE = ["#e74c3c", "#3498db", "#2ecc71", "#f39c12", "#9b59b6", "#1abc9c",
            "#e67e22", "#16a085", "#fd79a8", "#00b894", "#0984e3", "#fdcb6e",
            "#6c5ce7", "#d63031", "#00cec9", "#a29bfe", "#e84393", "#55efc4"]


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, template, ctx)


def _line_chart(serie: str, rango: str, desde: Optional[str] = None,
                hasta: Optional[str] = None, width: int = 960, height: int = 420) -> Dict[str, Any]:
    days = None if (desde or hasta) else _RANGOS.get(rango, 365)
    data = historico.series_points(serie, days, desde, hasta)
    pts = data["points"]
    n = len(pts)
    if n < 2:
        return {"n": n, "label": data["label"]}
    # downsample a ~700 puntos para un path liviano
    step = max(1, n // 700)
    sample = pts[::step]
    if sample[-1] != pts[-1]:
        sample.append(pts[-1])
    m = len(sample)
    ys = [p[1] for p in sample]
    ymin, ymax = min(ys), max(ys)
    if ymax == ymin:
        ymax = ymin + 1.0
    pady = (ymax - ymin) * 0.08
    ymin -= pady; ymax += pady
    ml, mr, mt, mb = 66, 16, 14, 40
    pw, ph = width - ml - mr, height - mt - mb

    def sx(i): return round(ml + i / (m - 1) * pw, 1)
    def sy(v): return round(mt + (1 - (v - ymin) / (ymax - ymin)) * ph, 1)

    path = "M " + " L ".join(f"{sx(i)},{sy(sample[i][1])}" for i in range(m))
    yticks = [{"y": sy(ymin + (ymax - ymin) / 5 * i), "v": round(ymin + (ymax - ymin) / 5 * i, 2)} for i in range(6)]
    xticks = []
    for i in range(6):
        idx = round(i / 5 * (m - 1))
        xticks.append({"x": sx(idx), "v": sample[idx][0]})
    return {
        "n": n, "label": data["label"], "path": path, "yticks": yticks, "xticks": xticks,
        "width": width, "height": height, "x0": ml, "x1": ml + pw, "y0": mt, "y1": mt + ph,
        "last": pts[-1][1], "last_date": pts[-1][0],
    }


def _curve_chart(cs: Dict[str, Any], desde: Optional[str] = None, hasta: Optional[str] = None,
                 width: int = 980, height: int = 520) -> Dict[str, Any]:
    """Multi-línea: una TIREA/TNA/TEM/Paridad por bono de la curva + bandas
    prom/mín/máx. Eje X por fecha (ordinal), todas las métricas ×100 (%)."""
    from datetime import date
    lines = cs.get("lines") or []
    if not lines:
        return {"loaded": cs.get("loaded", False), "n_lines": 0, "metric": cs.get("metric"),
                "curve_label": cs.get("curve_label")}
    scale = 100.0
    ends = [p[0] for ln in lines for p in (ln["points"][0], ln["points"][-1])]
    dmin, dmax = (desde or min(ends)), (hasta or max(ends))
    try:
        o0, o1 = date.fromisoformat(dmin).toordinal(), date.fromisoformat(dmax).toordinal()
    except ValueError:
        o0, o1 = 0, 1
    if o1 <= o0:
        o1 = o0 + 1
    ys = [v * scale for ln in lines for _, v in ln["points"]]
    ymin, ymax = min(ys), max(ys)
    if ymax == ymin:
        ymax = ymin + 1.0
    pad = (ymax - ymin) * 0.08
    ymin -= pad
    ymax += pad
    ml, mr, mt, mb = 60, 104, 16, 42
    pw, ph = width - ml - mr, height - mt - mb

    def sx(diso):
        try:
            o = date.fromisoformat(diso).toordinal()
        except ValueError:
            o = o0
        return round(ml + (o - o0) / (o1 - o0) * pw, 1)

    def sy(v):
        return round(mt + (1 - (v - ymin) / (ymax - ymin)) * ph, 1)

    out_lines = []
    for i, ln in enumerate(lines):
        pts = ln["points"]
        step = max(1, len(pts) // 160)
        sample = pts[::step]
        if sample[-1] != pts[-1]:
            sample.append(pts[-1])
        path = "M " + " L ".join(f"{sx(d)},{sy(v * scale)}" for d, v in sample)
        out_lines.append({"code": ln["code"], "path": path, "color": _PALETTE[i % len(_PALETTE)],
                          "delta": ln["delta"], "delta_unit": ln["delta_unit"], "last": ln["last"] * scale})
    agg = cs.get("agg")
    bands = None
    if agg:
        bands = {k: {"y": sy(agg[k] * scale), "v": round(agg[k] * scale, 1)} for k in ("mean", "min", "max")}
    yticks = [{"y": sy(ymin + (ymax - ymin) / 5 * i), "v": round(ymin + (ymax - ymin) / 5 * i, 1)} for i in range(6)]
    xticks = []
    for i in range(6):
        o = round(o0 + i / 5 * (o1 - o0))
        xticks.append({"x": round(ml + (o - o0) / (o1 - o0) * pw, 1), "v": date.fromordinal(o).isoformat()})
    return {"loaded": True, "n_lines": len(out_lines), "lines": out_lines, "bands": bands,
            "metric": cs.get("metric"), "curve_label": cs.get("curve_label"), "is_yield": cs.get("is_yield"),
            "yticks": yticks, "xticks": xticks, "width": width, "height": height,
            "x0": ml, "x1": ml + pw, "y0": mt, "y1": mt + ph, "dmin": dmin, "dmax": dmax}


def _curve_ctx(curve: Optional[str], metric: str, desde: Optional[str],
               hasta: Optional[str], proy: str) -> Dict[str, Any]:
    from backend.services import curves
    keys = historico_byma.curves_with_history(desde, hasta, proy)
    labels = {cv.key: cv.label for cv in curves.list_curves()}
    sel = curve if curve in keys else (keys[0] if keys else None)
    cs = historico_byma.curve_series(sel, metric, desde, hasta, proy) if sel else {"loaded": False, "lines": []}
    return {"curve_opts": [{"key": k, "label": labels.get(k, k)} for k in keys],
            "curve_sel": sel, "metric": metric, "proy": proy,
            "curve_chart": _curve_chart(cs, desde, hasta), "hist_meta": historico_byma.meta()}


@router.get("/historicos", response_class=HTMLResponse)
async def historicos_page(
    request: Request,
    serie: Optional[str] = None,
    rango: str = "1a",
    desde: Optional[str] = None,
    hasta: Optional[str] = None,
    refresh: bool = False,
) -> HTMLResponse:
    if refresh:
        historico.refresh()
        historico_byma.refresh()
    series = historico.series_list()
    keys = {s["key"] for s in series}
    selected = serie if serie in keys else (series[0]["key"] if series else None)
    chart = _line_chart(selected, rango, desde, hasta) if selected else {"n": 0}
    # La pestaña Curvas se carga lazy (htmx) la primera vez que se abre, para no
    # pagar la lectura del Excel histórico en cada visita a Macro.
    return _render(
        request, "historicos.html",
        series=series, selected=selected, rango=rango, desde=desde or "", hasta=hasta or "",
        chart=chart, status=historico.status(),
    )


@router.get("/historicos/svg", response_class=HTMLResponse)
async def historicos_svg(request: Request, serie: str = "", rango: str = "1a",
                         desde: Optional[str] = None, hasta: Optional[str] = None) -> HTMLResponse:
    return _render(request, "partials/historico_svg.html",
                   chart=_line_chart(serie, rango, desde, hasta), serie=serie, rango=rango,
                   desde=desde or "", hasta=hasta or "")


@router.get("/historicos/curva", response_class=HTMLResponse)
async def historicos_curva(request: Request, curve: str = "", metric: str = "TIREA",
                           desde: Optional[str] = None, hasta: Optional[str] = None,
                           proy: str = "todos") -> HTMLResponse:
    # Sólo arma los controles (curvas con historia + meta); el chart lo dibuja
    # uPlot desde /historicos/curva/data. La 1ª vez lee el Excel (~3-4 s) → executor.
    def _light() -> Dict[str, Any]:
        from backend.services import curves
        keys = historico_byma.curves_with_history(desde, hasta, proy)
        labels = {cv.key: cv.label for cv in curves.list_curves()}
        sel = curve if curve in keys else (keys[0] if keys else None)
        return {"curve_opts": [{"key": k, "label": labels.get(k, k)} for k in keys],
                "curve_sel": sel, "metric": metric, "proy": proy, "hist_meta": historico_byma.meta()}

    loop = asyncio.get_running_loop()
    ctx = await loop.run_in_executor(None, _light)
    return _render(request, "partials/historico_curva.html",
                   desde=desde or "", hasta=hasta or "", **ctx)


def _unix(iso: str) -> Optional[int]:
    """'YYYY-MM-DD' → epoch seconds (UTC), para el eje temporal de uPlot."""
    from datetime import datetime, timezone
    try:
        return int(datetime.fromisoformat(str(iso)[:10]).replace(tzinfo=timezone.utc).timestamp())
    except ValueError:
        return None


@router.get("/historicos/data")
async def historicos_data(serie: str = "", rango: str = "1a",
                          desde: Optional[str] = None, hasta: Optional[str] = None) -> JSONResponse:
    """Serie macro en JSON para uPlot: x = epoch (s), y = valor."""
    days = None if (desde or hasta) else _RANGOS.get(rango, 365)
    data = historico.series_points(serie, days, desde, hasta)
    pts = [(d, v) for d, v in data["points"] if _unix(d) is not None]
    return JSONResponse({"label": data["label"], "n": len(pts),
                         "x": [_unix(d) for d, _ in pts], "y": [v for _, v in pts]})


@router.get("/historicos/curva/data")
async def historicos_curva_data(curve: str = "", metric: str = "TIREA",
                                desde: Optional[str] = None, hasta: Optional[str] = None,
                                proy: str = "todos") -> JSONResponse:
    """Histórico de tasas por curva en JSON para uPlot multilínea: una serie por
    bono (alineadas a la unión de fechas, null en los huecos) + bandas."""
    loop = asyncio.get_running_loop()
    cs = await loop.run_in_executor(None, historico_byma.curve_series, curve, metric, desde, hasta, proy)
    lines = cs.get("lines") or []
    if not lines:
        return JSONResponse({"loaded": cs.get("loaded", False), "x": [], "series": [],
                             "bands": None, "metric": cs.get("metric"), "curve_label": cs.get("curve_label")})
    all_dates = sorted({d for ln in lines for d, _ in ln["points"]})
    idx = {d: i for i, d in enumerate(all_dates)}
    scale = 100.0
    series = []
    for ln in lines:
        y = [None] * len(all_dates)
        for d, v in ln["points"]:
            y[idx[d]] = v * scale
        series.append({"code": ln["code"], "y": y, "last": ln["last"] * scale,
                       "delta": ln["delta"], "delta_unit": ln["delta_unit"]})
    agg = cs.get("agg")
    bands = {k: agg[k] * scale for k in ("mean", "min", "max")} if agg else None
    return JSONResponse({"loaded": True, "x": [_unix(d) for d in all_dates], "series": series,
                         "bands": bands, "metric": cs.get("metric"), "curve_label": cs.get("curve_label")})
