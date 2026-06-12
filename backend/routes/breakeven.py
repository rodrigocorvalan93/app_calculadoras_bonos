"""Break-even inflation — pestaña (método Fisher, no iterativo).

Reusa `_rows_for` del motor de curvas (TIREA/duration ya cacheadas) para CER
y tasa fija, y `services.breakeven.compute_fisher` despeja la inflación
implícita. Costo extra ≈ aritmética sobre filas ya calculadas → mismo perfil
sub-50 ms que /curves/table. NO toca proyecciones de inflación ni itera.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from backend.routes.curves import _rows_for
from backend.services import bond_universe, breakeven as be_svc

router = APIRouter(tags=["breakeven"])

# Curva nominal contra la que se despeja: LECAP/tasa fija (la misma que usa
# el legacy). La curva real es siempre CER observada.
_NOMINAL_CURVE = "lecap"


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, template, ctx)


async def _ctx(plazo: str) -> Dict[str, Any]:
    import json

    cer_rows, _ = await _rows_for("cer", plazo, only_quoting=True)
    lecap_rows, _ = await _rows_for(_NOMINAL_CURVE, plazo, only_quoting=True)
    # Lag de ajuste de la especie (típ. −10 hábiles) → mes de referencia.
    for r in cer_rows:
        obj = bond_universe.get(r.get("code", ""))
        r["lag"] = getattr(obj, "dias_lag_ajuste", -10) if obj is not None else -10
    data = be_svc.compute_fisher(cer_rows, lecap_rows)
    # JSON para el gráfico de barras (TEM/TIR en pp, client-side, sin endpoint extra).
    chart = [r for r in data["rows"] if r.get("be_anual") is not None]
    be_json = json.dumps({
        "labels": [r["code"] for r in chart],
        "mes": [r.get("mes_ref") or "" for r in chart],
        "tem": [round(r["be_tem"] * 100.0, 4) for r in chart],
        "anual": [round(r["be_anual"] * 100.0, 4) for r in chart],
    })
    return {**data, "plazo": plazo, "be_json": be_json}


@router.get("/breakeven", response_class=HTMLResponse)
async def breakeven_page(request: Request, plazo: str = "24hs") -> HTMLResponse:
    bond_universe.ensure_loaded()
    return _render(request, "breakeven.html", **(await _ctx(plazo)))


@router.get("/breakeven/table", response_class=HTMLResponse)
async def breakeven_table(request: Request, plazo: str = "24hs") -> HTMLResponse:
    bond_universe.ensure_loaded()
    return _render(request, "partials/breakeven_table.html", **(await _ctx(plazo)))
