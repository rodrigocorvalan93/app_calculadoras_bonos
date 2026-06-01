"""Históricos — series macro del BCRA (line chart SVG server-side).

Sirve del cache de `services.historico` (lectura única del json; refresh
explícito). El histórico de precios/tasas de bonos (Excel) se suma cuando
tengamos el formato de las columnas.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from backend.services import historico

router = APIRouter(tags=["historicos"])

_RANGOS = {"1m": 30, "3m": 90, "6m": 180, "1a": 365, "3a": 1095, "5a": 1825, "todo": None}


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, template, ctx)


def _line_chart(serie: str, rango: str, width: int = 960, height: int = 420) -> Dict[str, Any]:
    data = historico.series_points(serie, _RANGOS.get(rango, 365))
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


@router.get("/historicos", response_class=HTMLResponse)
async def historicos_page(
    request: Request,
    serie: Optional[str] = None,
    rango: str = "1a",
    refresh: bool = False,
) -> HTMLResponse:
    if refresh:
        historico.refresh()
    series = historico.series_list()
    keys = {s["key"] for s in series}
    selected = serie if serie in keys else (series[0]["key"] if series else None)
    chart = _line_chart(selected, rango) if selected else {"n": 0}
    return _render(
        request, "historicos.html",
        series=series, selected=selected, rango=rango, chart=chart,
        status=historico.status(),
    )


@router.get("/historicos/svg", response_class=HTMLResponse)
async def historicos_svg(request: Request, serie: str = "", rango: str = "1a") -> HTMLResponse:
    return _render(request, "partials/historico_svg.html", chart=_line_chart(serie, rango), serie=serie, rango=rango)
