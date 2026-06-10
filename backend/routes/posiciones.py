"""Posiciones + Matriz de tenencias (pestañas separadas).

Sirve del cache de `services.positions` (carga única; ?refresh=1 relee).
Enriquece cada tenencia con métricas vivas (TIREA/TNA/Duration/last) vía el
motor de curvas y arma el resumen de composición (Clase / Categoría / Tasa /
Calificación × Monto/%PN) matcheando Cod_Delta ↔ ticker del universo.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from backend.routes.curves import _row_for_code
from backend.services import bond_universe, positions

router = APIRouter(tags=["posiciones"])


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, template, ctx)


# ── categorización (lee atributos del Bono del universo) ───────────────────
def _bono(code: Optional[str]):
    return bond_universe.get(code) if code else None


def _dual_label(obj) -> Optional[str]:
    """Etiqueta de bono dual, leída del campo `Industria` de la especie (p.ej.
    'Soberano ARS Dual CER/Tamar' o '… Dual Fija/Tamar'). None si no es dual.

    Detección por CONVENCIÓN DE NOMBRE, NO por lista de tickers: cualquier dual
    nuevo que emita el Tesoro entra solo, siempre que su `Industria` diga
    'Dual … Tamar'. No hay nada hardcodeado por código de especie.
    """
    if obj is None:
        return None
    ind = (getattr(obj, "industria", "") or "").upper()
    if "DUAL" not in ind or "TAMAR" not in ind:
        return None
    if "CER" in ind:
        return "Dual CER / TAMAR"
    if "FIJA" in ind:
        return "Dual Fija / TAMAR"
    return "Dual / TAMAR"                       # fallback para algún dual futuro


def _tasa(obj) -> str:
    if obj is None:
        return "(sin clasif.)"
    dual = _dual_label(obj)                     # dual = fija + variable (TAMAR)
    if dual:
        return dual
    if getattr(obj, "step_up", False):
        return "Step Up"
    tipo = (getattr(obj, "tipo_tasa_interes", "") or "").upper()
    idx = (getattr(obj, "index", "") or "").upper()
    if tipo in ("VARIABLE", "VARIABLE_CAP"):
        return idx or "Variable"
    if tipo == "FIJA":
        return "Fija"
    return "(sin clasif.)"


def _categoria(obj) -> str:
    if obj is None:
        return "(sin clasif.)"
    # Duales primero (antes del chequeo de CER): aunque ajustan por CER, los
    # queremos agrupados como duales. Sólo afecta esta categoría/display — NO el
    # pricing (TNA/TIREA siguen saliendo de ajuste/tipo_tasa, sin cambios).
    dual = _dual_label(obj)
    if dual:
        return dual
    aj = (getattr(obj, "ajuste_sobre_capital", "") or "").upper()
    mon = (getattr(obj, "moneda", "") or "").upper()
    if "CER" in aj:
        return "CER"
    if "UVA" in aj:
        return "UVA"
    if "A3500" in aj:
        return "USD-Linked"
    if mon == "USD":
        return "USD"
    if mon == "USB":
        return "USB"
    tasa = _tasa(obj)
    return {"Fija": "ARS Fija", "TAMAR": "ARS TAMAR", "BADLAR": "ARS BADLAR",
            "Step Up": "ARS Step Up"}.get(tasa, "ARS (s/tasa)")


def _calif(obj) -> str:
    if obj is None:
        return "(sin clasif.)"
    clas = getattr(obj, "clasificacion", "") or ""
    if "Soberano" in clas:
        return "Soberano"
    cal = (getattr(obj, "calificacion", "") or "").strip()
    return cal or "(sin clasif.)"


def _cat_for(h: Dict[str, Any], obj) -> str:
    """Categoría de la tenencia. Bonos → `_categoria(obj)`; especies fuera del
    universo (acciones, CEDEARs, FCI…) → se infiere de la 'Clase de Activo' del
    Excel de cartera, así no caen en '(sin clasif.)'."""
    if obj is not None:
        return _categoria(obj)
    cl = (h.get("clase") or "").lower()
    if "cedear" in cl:
        return "CEDEARs"
    if "accion" in cl or "acción" in cl or "equity" in cl:
        return "Acciones"
    if "fondo" in cl or "fci" in cl:
        return "FCI"
    if "caucion" in cl or "caución" in cl or "plazo fijo" in cl:
        return "Liquidez"
    return h.get("clase") or "(sin clasif.)"


def _emisor_for(code: Optional[str], obj) -> Optional[str]:
    """Emisor: del Excel Delta-Especies (cacheado, lookup µs); soberanos sin
    ficha ahí → 'Tesoro Nacional'."""
    from backend.services import delta_especies
    em = (delta_especies.info(code) or {}).get("Emisor / Sponsor") if code else None
    if not em and obj is not None and "Soberano" in (getattr(obj, "clasificacion", "") or ""):
        em = "Tesoro Nacional"
    return em


def _composicion_summary(hs: List[Dict[str, Any]], pn: Optional[float]) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, Dict[str, float]] = {
        "Clase de Activo": {}, "Categoría": {}, "Tasa": {}, "Calificación": {},
    }
    for h in hs:
        valor = h.get("valor") or 0.0
        obj = _bono(h.get("cod_delta"))
        keys = {
            "Clase de Activo": h.get("clase") or "(sin clasif.)",
            "Categoría": _cat_for(h, obj),
            "Tasa": _tasa(obj),
            "Calificación": _calif(obj),
        }
        for g, k in keys.items():
            groups[g][k] = groups[g].get(k, 0.0) + valor
    out: Dict[str, List[Dict[str, Any]]] = {}
    for g, d in groups.items():
        rows = [{"cat": k, "monto": v, "pct": (v / pn) if (pn and pn > 0) else None}
                for k, v in d.items()]
        rows.sort(key=lambda r: -abs(r["monto"]))
        out[g] = rows
    return out


def _enrich(hs: List[Dict[str, Any]], pn: Optional[float], plazo: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for h in hs:
        code = h.get("cod_delta")
        obj = _bono(code)
        m = _row_for_code(code, plazo) if code else None
        valor = h.get("valor")
        cant = h.get("cantidad")
        # Precio al que está valuada la tenencia (monto / VN). El retorno del
        # día (vs Last, editable) se calcula EN EL NAVEGADOR — cero requests.
        px_val = (valor / cant) if (valor and cant) else None
        rows.append({
            **h,
            "in_universe": m is not None,
            "pct_pn": (valor / pn) if (valor is not None and pn and pn > 0) else None,
            "emisor": _emisor_for(code, obj),
            "categoria": _cat_for(h, obj),
            "rating": _calif(obj) if obj is not None else "—",
            "px_val": px_val,
            "tirea": (m or {}).get("tirea"),
            "tna": (m or {}).get("tna"),
            "tna_convention_label": (m or {}).get("tna_convention_label"),
            "duration": (m or {}).get("duration"),
            "last": (m or {}).get("last"),
            "price_source": (m or {}).get("price_source"),
        })
    rows.sort(key=lambda r: (r.get("valor") or 0.0), reverse=True)
    return rows


# ── Posiciones ─────────────────────────────────────────────────────────────
@router.get("/posiciones", response_class=HTMLResponse)
async def posiciones_page(
    request: Request,
    fondo: Optional[int] = None,
    plazo: str = "24hs",
    refresh: bool = False,
) -> HTMLResponse:
    bond_universe.ensure_loaded()
    if refresh:
        positions.refresh()
    fs = positions.fondos()
    selected = fondo if (fondo is not None and any(f["cod"] == fondo for f in fs)) \
        else (fs[0]["cod"] if fs else None)
    return _render(
        request, "posiciones.html",
        fondos=fs, selected=selected, plazo=plazo, status=positions.status(),
        **_fondo_ctx(selected, plazo),
    )


def _fondo_ctx(selected: Optional[int], plazo: str) -> Dict[str, Any]:
    if selected is None:
        return {"rows": [], "summary": {}, "pn": None, "total_valor": 0.0, "nombre": ""}
    pn = positions.pn_of(selected)
    hs = positions.holdings(selected)
    rows = _enrich(hs, pn, plazo)
    return {
        "rows": rows,
        "summary": _composicion_summary(hs, pn),
        "pn": pn,
        "total_valor": sum((r.get("valor") or 0.0) for r in rows),
        "nombre": positions.fondo_label(selected),
        "fondo": selected,
    }


@router.get("/posiciones/table", response_class=HTMLResponse)
async def posiciones_table(request: Request, fondo: Optional[int] = None, plazo: str = "24hs") -> HTMLResponse:
    # `fondo` opcional: el poll live (md-update) puede llegar sin selección
    # (sin carteras cargadas) y no debe romper con 422.
    bond_universe.ensure_loaded()
    return _render(request, "partials/posiciones_fondo.html", plazo=plazo, **_fondo_ctx(fondo, plazo))


# ── Matriz de tenencias (pestaña aparte) ───────────────────────────────────
@router.get("/matriz", response_class=HTMLResponse)
async def matriz_page(request: Request, view: str = "vn", refresh: bool = False) -> HTMLResponse:
    bond_universe.ensure_loaded()
    if refresh:
        positions.refresh()
    return _render(request, "matriz.html", view=view, status=positions.status(), **_matriz_ctx())


@router.get("/matriz/table", response_class=HTMLResponse)
async def matriz_table(request: Request, view: str = "vn") -> HTMLResponse:
    bond_universe.ensure_loaded()
    return _render(request, "partials/matriz_table.html", view=view, **_matriz_ctx())


def _matriz_ctx() -> Dict[str, Any]:
    c = positions.ensure_loaded()
    fs = positions.fondos()
    esps: Dict[str, Dict[int, Dict[str, float]]] = {}
    for h in c["holdings"]:
        e = h.get("cod_delta") or h.get("especie")
        if not e:
            continue
        d = esps.setdefault(e, {})
        cell = d.setdefault(h["cod_fondo"], {"vn": 0.0, "valor": 0.0})
        cell["vn"] += (h.get("cantidad") or 0.0)
        cell["valor"] += (h.get("valor") or 0.0)
    rows = []
    for e, byf in sorted(esps.items(), key=lambda kv: -sum(c2["valor"] for c2 in kv[1].values())):
        cells = []
        for f in fs:
            cell = byf.get(f["cod"])
            pct = (cell["valor"] / f["pn"]) if (cell and f.get("pn")) else None
            cells.append({"vn": cell["vn"] if cell else None,
                          "valor": cell["valor"] if cell else None, "pct": pct})
        rows.append({"especie": e, "cells": cells})
    return {"fondos": fs, "rows": rows}
