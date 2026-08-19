"""Posiciones + Matriz de tenencias (pestañas separadas).

Sirve del cache de `services.positions` (carga única; ?refresh=1 relee).
Enriquece cada tenencia con métricas vivas (TIREA/TNA/Duration/last) vía el
motor de curvas y arma el resumen de composición (Clase / Categoría / Tasa /
Calificación × Monto/%PN) matcheando Cod_Delta ↔ ticker del universo.
"""
from __future__ import annotations

import asyncio
import threading
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from backend.routes.curves import _row_for_code
from backend.services import auth, bond_universe, positions, pricing

router = APIRouter(tags=["posiciones"])

# Visibilidad de fondos POR USUARIO (auth.visible_fondos_for): None = todos.
# El filtro entra por acá en cada endpoint y baja al provider — un fondo no
# visible no aparece en el selector, ni por ?fondo= a mano (URL-hack), ni como
# columna de la matriz.


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, template, ctx)


# ── categorización (lee atributos del Bono del universo) ───────────────────
def _bono(code: Optional[str]):
    return bond_universe.get(code) if code else None


def _ficha_leg(code: Optional[str]):
    """Fallback de ficha para PATAS FX sin match exacto en el universo: GD46D /
    GD30D (MEP de un global cuya ficha nativa es la …C) o MGCQOD (MEP de una ON
    de base …O) → prueba base, base+C, base+D. Cualquier pata es el MISMO papel
    (mismo vencimiento/emisor). Se usa sólo para atributos estáticos del papel
    (columna Vto); las métricas y la categoría siguen atadas al match exacto,
    que es el que define la valuación."""
    if not code:
        return None
    c = str(code).strip().upper()
    if len(c) > 2 and c[-1] in ("C", "D") and not c.endswith(("CC", "DD")):
        base = c[:-1]
        cands = [base, base + "C", base + "D"]
        if base.endswith("O") and len(base) > 2:
            # ONs: la pata FX REEMPLAZA la O final del ticker ARS (MGCQO →
            # MGCQD/MGCQC), pero el cod_delta de la cartera viene base+sufijo
            # (MGCQOD) → probar también las fichas con la O reemplazada.
            cands += [base[:-1] + "D", base[:-1] + "C"]
        for cand in cands:
            if cand != c:
                obj = _bono(cand)
                if obj is not None:
                    return obj
    return None


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


def _venc_date(obj):
    """Vencimiento de la ficha como date (o None): admite date/datetime/Timestamp
    (los con hora se normalizan con .date(); un date pelado no tiene .hour)."""
    v = getattr(obj, "vencimiento", None) if obj is not None else None
    if v is None:
        return None
    try:
        return v.date() if hasattr(v, "hour") else v
    except Exception:  # noqa: BLE001
        return v


def _calif(obj) -> str:
    """Calificación local de la ficha (AA(arg), CCC-, …). Antes los soberanos
    devolvían el literal "Soberano" y la columna Rating nunca mostraba su
    calificación real; el split soberano/corporativo ya vive en Categoría.
    "Soberano" queda sólo como fallback de una ficha soberana sin dato."""
    if obj is None:
        return "(sin clasif.)"
    cal = (getattr(obj, "calificacion", "") or "").strip()
    if cal:
        return cal
    clas = getattr(obj, "clasificacion", "") or ""
    return "Soberano" if "Soberano" in clas else "(sin clasif.)"


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


def _venc_bucket(obj) -> str:
    """Bucket trimestral del vencimiento ('3Q2026') para la composición.
    Sin ficha o sin vencimiento (acciones, FCI, liquidez) → 'Sin vencimiento'.
    Reusa el obj que el loop ya levantó: cero lookups extra."""
    v = _venc_date(obj)
    if v is None:
        return "Sin vencimiento"
    try:
        return f"{(v.month - 1) // 3 + 1}Q{v.year}"
    except AttributeError:              # vencimiento no-fecha en una ficha rota
        return "Sin vencimiento"


def _venc_sort_key(cat: str):
    """Orden CRONOLÓGICO de los buckets ('1Q2026' < '2Q2026' < …); el bucket
    sin vencimiento va último."""
    try:
        return (int(cat[2:]), int(cat[0]))
    except (ValueError, IndexError):
        return (9999, 9)


# Clasificación regulatoria del fondo de infraestructura ("Crecimiento") —
# misma fuente que el KPI del legacy OMSposiciones (fondo 18): la columna
# `Clasificacion_especifico` del Excel Delta-Especies, servida por el cache en
# memoria de delta_especies (lookup µs). Todo lo que no es infra explícita
# (Pymes, sin ficha, acciones, liquidez) cuenta como "No infraestructura".
_INFRA_ORDEN = ("Multidestino", "Destino Específico", "No infraestructura")


def _infra_bucket(code: Optional[str]) -> str:
    from backend.services import delta_especies
    ce = str((delta_especies.info(code) or {}).get("Clasificacion_especifico") or "") if code else ""
    if "Infraestructura" in ce:
        if "Multidestino" in ce:
            return "Multidestino"
        if "Destino" in ce:
            return "Destino Específico"
    return "No infraestructura"


def _composicion_summary(hs: List[Dict[str, Any]], pn: Optional[float],
                         infra: bool = False) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, Dict[str, float]] = {
        "Clase de Activo": {}, "Categoría": {}, "Tasa": {}, "Calificación": {},
        "Vencimiento": {},
    }
    if infra:
        groups["Activos infra"] = {}
    for h in hs:
        valor = h.get("valor") or 0.0
        code = h.get("cod_delta")
        obj = _bono(code)
        keys = {
            "Clase de Activo": h.get("clase") or "(sin clasif.)",
            "Categoría": _cat_for(h, obj),
            "Tasa": _tasa(obj),
            "Calificación": _calif(obj),
            # mismo fallback de ficha que la columna Vto de la tabla (patas FX)
            "Vencimiento": _venc_bucket(obj if obj is not None else _ficha_leg(code)),
        }
        if infra:
            keys["Activos infra"] = _infra_bucket(code)
        for g, k in keys.items():
            groups[g][k] = groups[g].get(k, 0.0) + valor
    out: Dict[str, List[Dict[str, Any]]] = {}
    for g, d in groups.items():
        # Denominador: PN si lo hay, si no Σ Valor invertido (como el legacy) —
        # sin esto, un fondo sin PN cargado mostraba TODA la columna % en blanco.
        total = sum(d.values())
        denom = pn if (pn and pn > 0) else (total if total > 0 else None)
        rows = [{"cat": k, "monto": v, "pct": (v / denom) if denom else None}
                for k, v in d.items()]
        if g == "Vencimiento":
            rows.sort(key=lambda r: _venc_sort_key(r["cat"]))        # cronológico
        elif g == "Activos infra":
            rows.sort(key=lambda r: _INFRA_ORDEN.index(r["cat"]))    # orden fijo
        else:
            rows.sort(key=lambda r: -abs(r["monto"]))
        out[g] = rows
    return out


def _px_val_like_last(px_val: Optional[float], last: Optional[float]) -> Optional[float]:
    """Reescala el precio de valuación a la MISMA base que el Last BYMA por
    potencias de 10 (el Excel valúa por VN 1 → 0,9160; BYMA cotiza por VN 100
    → 91,85). Mismo criterio de escala automática que usa el Ret. día en el
    navegador, así la columna queda comparable a simple vista. Sin Last usable
    (o escala irreconciliable) se muestra tal cual."""
    if not px_val or not last or px_val <= 0 or last <= 0:
        return px_val
    f, k = 1.0, 0
    while last * f / px_val > 5 and k < 8:
        f /= 10.0
        k += 1
    while last * f / px_val < 0.2 and k < 16:
        f *= 10.0
        k += 1
    ratio = last * f / px_val
    return px_val / f if 0.2 < ratio < 5 else px_val


def _enrich(hs: List[Dict[str, Any]], pn: Optional[float], plazo: str) -> List[Dict[str, Any]]:
    # Denominador del peso por tenencia: PN, si no Σ Valor invertido (fallback legacy).
    total_valor = sum(h["valor"] for h in hs if h.get("valor"))
    denom = pn if (pn and pn > 0) else (total_valor if total_valor > 0 else None)
    settle = pricing.settlement_date_str(plazo)   # CI = hoy, 24hs = t+1 (fecha BA)
    rows: List[Dict[str, Any]] = []
    for h in hs:
        code = h.get("cod_delta")
        obj = _bono(code)
        m = _row_for_code(code, plazo, settle=settle) if code else None
        # Especies fuera del universo de bonos (acciones, CEDEARs): el Last
        # sale directo del store del WS (lookup en memoria, ~µs) — antes estas
        # filas quedaban sin precio porque bond_meta(code) es vacío.
        eq_last = eq_src = None
        if m is None and code:
            from backend.services import equities
            eq = equities.row_for(code, plazo)
            if eq is not None:
                if eq.get("last") is not None:
                    eq_last, eq_src = eq["last"], "LA"
                elif eq.get("close") is not None:
                    eq_last, eq_src = eq["close"], "CL"
        valor = h.get("valor")
        cant = h.get("cantidad")
        last_val = (m or {}).get("last") if m is not None else eq_last
        # Precio al que está valuada la tenencia (monto / VN), reescalado a la
        # base del Last BYMA para que las columnas sean comparables. El retorno
        # del día (vs Last, editable) se calcula EN EL NAVEGADOR — cero requests.
        px_val = (valor / cant) if (valor and cant) else None
        px_val = _px_val_like_last(px_val, last_val)
        rows.append({
            **h,
            "in_universe": m is not None,
            "pct_pn": (valor / denom) if (valor is not None and denom) else None,
            "emisor": _emisor_for(code, obj),
            "categoria": _cat_for(h, obj),
            "rating": _calif(obj) if obj is not None else "—",
            "px_val": px_val,
            "tirea": (m or {}).get("tirea"),
            "tna": (m or {}).get("tna"),
            "tna_convention_label": (m or {}).get("tna_convention_label"),
            "duration": (m or {}).get("duration"),
            # Vto: si el código no tiene ficha propia (pata FX como GD46D),
            # cae a la ficha nativa del mismo papel — antes quedaba "—".
            "vencimiento": _venc_date(obj if obj is not None else _ficha_leg(code)),
            "last": last_val,
            "price_source": (m or {}).get("price_source") if m is not None else eq_src,
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
    loop = asyncio.get_running_loop()
    if refresh:
        await loop.run_in_executor(None, positions.refresh)   # relee Excels (I/O)
    vis = auth.visible_fondos_for(request)
    fs = positions.fondos(vis)
    # `selected` se valida contra la lista YA filtrada: un ?fondo= oculto para
    # este usuario degrada al primero visible, nunca muestra el ajeno.
    selected = fondo if (fondo is not None and any(f["cod"] == fondo for f in fs)) \
        else (fs[0]["cod"] if fs else None)
    # _fondo_ctx valúa cada tenencia (pricing GIL-bound, cold ~200 ms–segundos):
    # fuera del event loop para no congelar todos los tabs live durante el refresh.
    ctx = await loop.run_in_executor(None, _fondo_ctx, selected, plazo, vis)
    return _render(
        request, "posiciones.html",
        fondos=fs, selected=selected, plazo=plazo, status=positions.status(),
        **ctx,
    )


def _agrupar_tenencias(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Tenencias agrupadas por Categoría — el cuadro con 'ramas' del Excel de
    carteras, pero con NUESTRO agrupamiento (el mismo de composición). Grupos
    ordenados por Σ valor desc; las filas adentro conservan su orden (valor
    desc). El subtotal de % PN sólo se muestra si alguna fila lo tiene."""
    by: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        cat = r.get("categoria") or "(sin clasif.)"
        g = by.setdefault(cat, {"cat": cat, "valor": 0.0, "pct_pn": 0.0,
                                "pct_any": False, "n": 0, "rows": []})
        g["rows"].append(r)
        g["n"] += 1
        g["valor"] += r.get("valor") or 0.0
        if r.get("pct_pn") is not None:
            g["pct_pn"] += r["pct_pn"]
            g["pct_any"] = True
    out = sorted(by.values(), key=lambda g: -g["valor"])
    for g in out:
        if not g.pop("pct_any"):
            g["pct_pn"] = None
    return out


def _fondo_ctx(selected: Optional[int], plazo: str,
               visibles: Optional[frozenset] = None) -> Dict[str, Any]:
    # `holdings(…, visibles)` devuelve [] si el fondo está oculto para el
    # usuario: el panel queda vacío también con ?fondo= inyectado a mano.
    if selected is None:
        return {"rows": [], "grupos": [], "summary": {}, "pn": None,
                "total_valor": 0.0, "nombre": ""}
    hs = positions.holdings(selected, visibles)
    if not hs:
        return {"rows": [], "grupos": [], "summary": {}, "pn": None,
                "total_valor": 0.0, "nombre": ""}
    pn = positions.pn_of(selected)
    rows = _enrich(hs, pn, plazo)
    nombre = positions.fondo_label(selected)
    # Cuadro "Activos infra" SOLO para el fondo de infraestructura (Crecimiento
    # — el del KPI regulatorio del legacy): para el resto ni se computa.
    return {
        "rows": rows,
        "grupos": _agrupar_tenencias(rows),
        "summary": _composicion_summary(hs, pn, infra="CRECIMIENTO" in nombre.upper()),
        "pn": pn,
        "total_valor": sum((r.get("valor") or 0.0) for r in rows),
        "nombre": nombre,
        "fondo": selected,
    }


def _fondo_param(fondo: Optional[str]) -> Optional[int]:
    """`?fondo=` puede venir VACÍO (sin carteras / sin selección): con
    Optional[int] FastAPI devolvía 422 por el string vacío. Se parsea a mano
    y cualquier cosa no numérica degrada a None (panel vacío, nunca error)."""
    try:
        return int(fondo) if fondo not in (None, "") else None
    except (TypeError, ValueError):
        return None


@router.get("/posiciones/table", response_class=HTMLResponse)
async def posiciones_table(request: Request, fondo: Optional[str] = None, plazo: str = "24hs") -> HTMLResponse:
    # `fondo` opcional: el poll live (md-update) puede llegar sin selección
    # (sin carteras cargadas) y no debe romper con 422.
    bond_universe.ensure_loaded()
    ctx = await asyncio.get_running_loop().run_in_executor(
        None, _fondo_ctx, _fondo_param(fondo), plazo, auth.visible_fondos_for(request))
    return _render(request, "partials/posiciones_fondo.html", plazo=plazo, **ctx)


@router.get("/posiciones/targets", response_class=HTMLResponse)
async def posiciones_targets(request: Request, fondo: Optional[str] = None,
                             plazo: str = "24hs") -> HTMLResponse:
    """Cuadro Target vs Actual por categoría — SEPARADO del panel live (no lleva
    `md-update` en el trigger) para no pisar la edición de los targets en cada
    tick. Los targets se guardan en localStorage por fondo (cliente); el server
    sólo aporta el % actual de cada categoría (snapshot por selección de fondo).
    Composición barata: suma de Valor por categoría, sin pricing por bono."""
    bond_universe.ensure_loaded()
    f = _fondo_param(fondo)
    cat_actual: List[Dict[str, Any]] = []
    nombre = ""
    if f is not None:
        hs = positions.holdings(f, auth.visible_fondos_for(request))
        if hs:
            summary = _composicion_summary(hs, positions.pn_of(f))
            cat_actual = [{"cat": r["cat"], "actual": r["pct"]}
                          for r in summary.get("Categoría", []) if r.get("pct") is not None]
            nombre = positions.fondo_label(f)
    return _render(request, "partials/posiciones_targets.html",
                   cat_actual=cat_actual, fondo=f, nombre=nombre)


# ── Perfil de vencimientos (flujos futuros del fondo) ──────────────────────
# Barras de cashflows proyectados (renta + amortización) del fondo, bucketeados
# por trimestre los primeros ~2 años y por año después. NO vive en el panel
# live: los flujos dependen de la ficha y del VN tenido, no del tick — se
# calcula al elegir fondo y se cachea por día/cartera. El costo (generate_
# cashflows por bono, ~ms c/u) corre en el executor y sólo la primera vez.
_perfil_cache: Dict[Any, Dict[str, Any]] = {}
_perfil_lock = threading.Lock()


def _bucket_flujo(d: date, hoy: date) -> str:
    """Trimestral hasta fin del año que viene ('4Q2026'), anual después ('2029')
    — granularidad útil cerca, sin 80 barras para un GD46."""
    if d.year <= hoy.year + 1:
        return f"{(d.month - 1) // 3 + 1}Q{d.year}"
    return str(d.year)


def _bucket_orden(label: str):
    try:
        if "Q" in label:
            q, y = label.split("Q")
            return (int(y), int(q))
        return (int(label), 0)
    except ValueError:
        return (9999, 9)


def _perfil_vencimientos(selected: Optional[int],
                         visibles: Optional[frozenset] = None) -> Dict[str, Any]:
    """Flujos futuros del fondo en ARS por bucket + resto sin vencimiento.

    Por tenencia con ficha: generate_cashflows(hoy) → cashflow_cpn_full
    (mismo camino que el TR realizado; `Total` es por 1 VN) × cantidad. Las
    fichas hard-dollar se convierten con el FX implícito vigente (USD→CCL,
    USB→MEP). Sin ficha / sin flujos / sin FX ⇒ el VALOR de la tenencia suma
    al bucket "sin vencimiento" (acciones, CEDEARs, FCI, liquidez).
    """
    vacio = {"bars": [], "otros_pct": None, "otros_ars": 0.0,
             "total_ars": 0.0, "nombre": "", "fondo": selected}
    if selected is None:
        return vacio
    hs = positions.holdings(selected, visibles)
    if not hs:
        return vacio
    hoy = date.today()
    key = (selected, visibles, hoy.toordinal(), positions.status().get("asof"))
    with _perfil_lock:
        cached = _perfil_cache.get(key)
    if cached is not None:
        return cached

    from backend.services import fx as fx_svc
    fxs = fx_svc.get_fx("24hs")

    flujos: Dict[str, List[float]] = {}      # bucket → [renta, amortización] ARS
    otros = 0.0
    for h in hs:
        code, cant, valor = h.get("cod_delta"), h.get("cantidad"), (h.get("valor") or 0.0)
        obj = pricing._bond_obj_copy(code) if code else None
        if obj is None or not hasattr(obj, "generate_cashflows") or not cant:
            otros += valor
            continue
        mon = (getattr(obj, "moneda", "") or "").upper()
        rate = 1.0
        if mon == "USD":
            rate = fxs.ccl or fxs.usb or 0.0
        elif mon == "USB":
            rate = fxs.usb or fxs.ccl or 0.0
        if not rate:                    # ficha en dólares sin FX: no inventar
            otros += valor
            continue
        try:
            import pandas as pd
            obj.generate_cashflows(hoy.strftime("%d/%m/%Y"))
            cf = obj.cashflow_cpn_full
            # Fechas viene como object-de-dates en las fichas reales; el
            # to_datetime lo hace robusto también a un datetime64 futuro
            # (comparar datetime64 vs date revienta en pandas moderno).
            fut = cf[pd.to_datetime(cf["Fechas"]) > pd.Timestamp(hoy)]
        except Exception:  # noqa: BLE001 — ficha rara: cuenta como sin vencimiento
            otros += valor
            continue
        if fut.empty:
            otros += valor
            continue
        # Split interés/capital: Total = (Intereses + Amortización) × Ajuste/100
        # por 1 VN (verificado contra fichas reales). renta = Int×Ajuste/100 y
        # amort = Total − renta ⇒ la suma cierra EXACTA con Total (sin drift).
        con_detalle = "Intereses" in fut.columns and "Ajuste" in fut.columns
        ints = fut["Intereses"] if con_detalle else None
        ajs = fut["Ajuste"] if con_detalle else None
        for i, (fecha, tot) in enumerate(zip(fut["Fechas"], fut["Total"])):
            d = fecha.date() if hasattr(fecha, "date") else fecha
            b = _bucket_flujo(d, hoy)
            tot_ars = float(tot) * float(cant) * rate
            try:
                renta_ars = (float(ints.iloc[i]) * float(ajs.iloc[i]) / 100.0
                             * float(cant) * rate) if con_detalle else 0.0
            except (TypeError, ValueError):
                renta_ars = 0.0
            renta_ars = min(max(renta_ars, 0.0), max(tot_ars, 0.0))
            cell = flujos.setdefault(b, [0.0, 0.0])
            cell[0] += renta_ars
            cell[1] += tot_ars - renta_ars

    total_valor = sum((h.get("valor") or 0.0) for h in hs)
    pn = positions.pn_of(selected)
    denom = pn if (pn and pn > 0) else (total_valor if total_valor > 0 else None)
    max_ars = max((r + a for r, a in flujos.values()), default=0.0)
    bars = []
    for k, (renta, amort) in sorted(flujos.items(), key=lambda kv: _bucket_orden(kv[0])):
        v = renta + amort
        bars.append({
            "label": k, "ars": v, "renta_ars": renta, "amort_ars": amort,
            "pct": (v / denom) if denom else None,
            "alto": (v / max_ars * 100.0) if max_ars > 0 else 0.0,
            # % de la barra que es interés (para el segmento de arriba del stack)
            "renta_share": (renta / v * 100.0) if v > 0 else 0.0,
        })
    out = {"bars": bars,
           "otros_pct": (otros / denom) if denom else None,
           "otros_ars": otros,
           "total_ars": sum(b["ars"] for b in bars),
           "nombre": positions.fondo_label(selected),
           "fondo": selected}
    with _perfil_lock:
        if len(_perfil_cache) > 64:     # fondos × días: nunca crece de verdad
            _perfil_cache.clear()
        _perfil_cache[key] = out
    return out


@router.get("/posiciones/vencimientos", response_class=HTMLResponse)
async def posiciones_vencimientos(request: Request, fondo: Optional[str] = None) -> HTMLResponse:
    """Partial del gráfico de vencimientos — FUERA del panel live (los flujos
    no dependen del tick); se pide al cargar la página y al cambiar de fondo.
    Filtrado por los fondos visibles del usuario como todo el subárbol."""
    bond_universe.ensure_loaded()
    ctx = await asyncio.get_running_loop().run_in_executor(
        None, _perfil_vencimientos, _fondo_param(fondo), auth.visible_fondos_for(request))
    return _render(request, "partials/posiciones_vencimientos.html", **ctx)


# ── Matriz de tenencias (pestaña aparte) ───────────────────────────────────
@router.get("/matriz", response_class=HTMLResponse)
async def matriz_page(request: Request, view: str = "vn", refresh: bool = False) -> HTMLResponse:
    bond_universe.ensure_loaded()
    if refresh:
        await asyncio.get_running_loop().run_in_executor(None, positions.refresh)   # relee Excels (I/O)
    return _render(request, "matriz.html", view=view, status=positions.status(),
                   **_matriz_ctx(auth.visible_fondos_for(request)))


@router.get("/matriz/table", response_class=HTMLResponse)
async def matriz_table(request: Request, view: str = "vn") -> HTMLResponse:
    bond_universe.ensure_loaded()
    return _render(request, "partials/matriz_table.html", view=view,
                   **_matriz_ctx(auth.visible_fondos_for(request)))


def _matriz_ctx(visibles: Optional[frozenset] = None) -> Dict[str, Any]:
    c = positions.ensure_loaded()
    fs = positions.fondos(visibles)
    esps: Dict[str, Dict[int, Dict[str, float]]] = {}
    for h in c["holdings"]:
        # Un fondo oculto no aporta ni columna ni fila: una especie que SÓLO
        # está en fondos ocultos no debe aparecer (delataría la tenencia).
        if visibles is not None and h["cod_fondo"] not in visibles:
            continue
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
