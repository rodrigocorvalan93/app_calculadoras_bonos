"""Break-even inflation — pestaña (método Fisher, no iterativo).

Reusa `_rows_for` del motor de curvas (TIREA/duration ya cacheadas) para CER
y tasa fija, y `services.breakeven.compute_fisher` despeja la inflación
implícita. Costo extra ≈ aritmética sobre filas ya calculadas → mismo perfil
sub-50 ms que /curves/table. NO toca proyecciones de inflación ni itera.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from backend.routes.curves import _rows_for
from backend.services import bond_universe, breakeven as be_svc

router = APIRouter(tags=["breakeven"])

# Curva nominal contra la que se despeja: LECAP/tasa fija (la misma que usa
# el legacy). La curva real es siempre CER observada.
_NOMINAL_CURVE = "lecap"


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, template, ctx)


def _cer_conocido_hasta():
    """Última fecha de la serie CER PUBLICADA (BCRA la publica hacia adelante
    una vez que sale el IPC): hasta ahí el ajuste ya está determinado."""
    try:
        from backend.services.pricing import _last_series_value
        fecha, _ = _last_series_value("CER", "CER")
        if fecha is None:
            return None
        return fecha.date() if hasattr(fecha, "date") else fecha
    except Exception:  # noqa: BLE001 — sin serie: nadie se marca definido
        return None


async def _ctx(plazo: str, incl: Optional[List[str]] = None,
               incl_set: bool = False) -> Dict[str, Any]:
    cer_rows, _ = await _rows_for("cer", plazo, only_quoting=True)
    lecap_rows, _ = await _rows_for(_NOMINAL_CURVE, plazo, only_quoting=True)
    # Lag de ajuste de la especie (típ. −10 hábiles) → mes de referencia.
    for r in cer_rows:
        obj = bond_universe.get(r.get("code", ""))
        r["lag"] = getattr(obj, "dias_lag_ajuste", -10) if obj is not None else -10
    # `incl` = tildes del usuario (viaja en cada request; `incl_set` distingue
    # "primera carga" de "destildó todo"). Sin tildes explícitos → default:
    # todos menos los DEFINIDOS (CER ya publicado cubre su fix).
    incluir = set(incl or []) if incl_set else None
    data = be_svc.compute_fisher(cer_rows, lecap_rows,
                                 cer_conocido_hasta=_cer_conocido_hasta(),
                                 incluir=incluir)
    return {**data, "plazo": plazo}


def _chart_ctx(data: Dict[str, Any], metric: str) -> Dict[str, Any]:
    """Geometría SVG del gráfico de barras — el MISMO layout (svg_charts) y las
    mismas clases fc-* que el sendero de deva de Futuros, para que las capturas
    de pantalla de los dos queden con idéntico estilo. Sólo bonos INCLUIDOS."""
    from backend.services.svg_charts import barras_pct

    m = "anual" if (metric or "").lower().startswith("an") else "tem"
    key = "be_anual" if m == "anual" else "be_tem"
    segs = [{"label": r["code"], "mes": r.get("mes_ref") or "", "val": r[key]}
            for r in data["rows"] if r.get(key) is not None and r.get("incluido")]
    res = data.get("resumen") or {}
    prom = res.get("be_anual_prom" if m == "anual" else "be_tem_prom")
    # height 300 / pad_b 96 → MISMA altura de plot que el sendero de deva
    # (194 uds), con aire extra para los labels largos "CÓDIGO · mes".
    return {"be_chart": barras_pct(segs, prom, ticks=4, pad_l=88,
                                   height=300, pad_b=96), "be_metric": m}


@router.get("/breakeven", response_class=HTMLResponse)
async def breakeven_page(request: Request, plazo: str = "24hs") -> HTMLResponse:
    bond_universe.ensure_loaded()
    data = await _ctx(plazo)
    return _render(request, "breakeven.html", **data, **_chart_ctx(data, "tem"))


@router.get("/breakeven/table", response_class=HTMLResponse)
async def breakeven_table(request: Request, plazo: str = "24hs",
                          incl: Optional[List[str]] = Query(None),
                          incl_set: Optional[str] = None) -> HTMLResponse:
    bond_universe.ensure_loaded()
    return _render(request, "partials/breakeven_table.html",
                   **(await _ctx(plazo, incl=incl, incl_set=bool(incl_set))))


@router.get("/breakeven/chart", response_class=HTMLResponse)
async def breakeven_chart(request: Request, plazo: str = "24hs",
                          metric: str = Query("tem", alias="be-metric"),
                          incl: Optional[List[str]] = Query(None),
                          incl_set: Optional[str] = None) -> HTMLResponse:
    """Partial htmx del gráfico de barras BE (SVG server-side). Respeta los
    tildes de la tabla (incl/incl_set, mismos params que /breakeven/table)."""
    bond_universe.ensure_loaded()
    data = await _ctx(plazo, incl=incl, incl_set=bool(incl_set))
    return _render(request, "partials/breakeven_chart.html",
                   **_chart_ctx(data, metric))
