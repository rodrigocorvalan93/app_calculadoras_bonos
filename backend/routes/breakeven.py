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
    import json

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
    # JSON para el gráfico de barras (sólo bonos INCLUIDOS, como el resumen).
    chart = [r for r in data["rows"] if r.get("be_anual") is not None and r.get("incluido")]
    res = data.get("resumen") or {}
    be_json = json.dumps({
        "labels": [r["code"] for r in chart],
        "mes": [r.get("mes_ref") or "" for r in chart],
        "tem": [round(r["be_tem"] * 100.0, 4) for r in chart],
        "anual": [round(r["be_anual"] * 100.0, 4) for r in chart],
        # Promedios del resumen (mismos números que la strip): la línea "prom"
        # del gráfico de barras, en la métrica que esté seleccionada.
        "prom_tem": (round(res["be_tem_prom"] * 100.0, 4)
                     if res.get("be_tem_prom") is not None else None),
        "prom_anual": (round(res["be_anual_prom"] * 100.0, 4)
                       if res.get("be_anual_prom") is not None else None),
    })
    return {**data, "plazo": plazo, "be_json": be_json}


@router.get("/breakeven", response_class=HTMLResponse)
async def breakeven_page(request: Request, plazo: str = "24hs") -> HTMLResponse:
    bond_universe.ensure_loaded()
    return _render(request, "breakeven.html", **(await _ctx(plazo)))


@router.get("/breakeven/table", response_class=HTMLResponse)
async def breakeven_table(request: Request, plazo: str = "24hs",
                          incl: Optional[List[str]] = Query(None),
                          incl_set: Optional[str] = None) -> HTMLResponse:
    bond_universe.ensure_loaded()
    return _render(request, "partials/breakeven_table.html",
                   **(await _ctx(plazo, incl=incl, incl_set=bool(incl_set))))
