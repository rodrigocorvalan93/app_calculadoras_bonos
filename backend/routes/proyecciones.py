"""Proyecciones — pestaña para editar la inflación mensual y el A3500 proyectados (13/11).

Ver `services.proyecciones` (archivo compartido, recálculo sólo de la parte
proyectada, instalación en `rentafija.inputs`, vigilante multi-PC). Acá:

- GET  /proyecciones            la pestaña: tablas editables (meses observados
                                en gris con el dato real), escenario vigente,
                                gráfico y resumen, historial.
- POST /proyecciones/preview    vista previa del BORRADOR sin aplicar: series
                                recalculadas (ms), resumen y gráfico contra la
                                vigente. Cualquier usuario con la pestaña.
- POST /proyecciones/csv        CSV es-AR de una serie del borrador (cer / uva /
                                a3500 / inflamom), sin aplicar.
- GET  /proyecciones/futuros    la senda A3500 que implican los futuros DLR
                                (precio por contrato, fin de mes) para llenar
                                la tabla de un click.
- POST /proyecciones/aplicar    feature `proyecciones` (main._FEATURE_PATHS):
       /proyecciones/deshacer   guarda + log + instala; las otras PCs lo toman
       /proyecciones/restablecer por el vigilante. Responde HX-Redirect a la
                                pestaña (la página es barata) o el error.

Todo cálculo (pandas) va al executor; el render de la página es Jinja sobre
listas chicas (≤ 360 filas por tabla).
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from backend.locale_ar import hoy_ba, parse_ar_num
from backend.services import proyecciones as proy

logger = logging.getLogger("backend.proyecciones.routes")

router = APIRouter(tags=["proyecciones"])

_OBS_MESES = 6          # meses observados que se muestran (en gris) arriba de la proyección
_HIST_N = 15


def _render(request: Request, template: str, **ctx: Any) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, template, ctx)


def _user(request: Request) -> str:
    u = getattr(request.state, "user", None) or {}
    return str(u.get("username") or "_local")


def _puede_editar(request: Request) -> bool:
    feats = getattr(request.state, "features", None) or frozenset()
    return "proyecciones" in feats


# ── form → escenario ─────────────────────────────────────────────────────────
def _fecha_iso(s: str) -> Optional[str]:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10]).isoformat()
    except ValueError:
        pass
    try:                                              # DD/MM/AAAA
        d, m, y = s.split("/")
        return date(int(y), int(m), int(d)).isoformat()
    except (ValueError, TypeError):
        return None


def parse_form(form: Any) -> Tuple[Dict[str, Any], str, List[str]]:
    """(escenario crudo, nota, problemas): `i_<AAAA-MM>` = inflación mensual
    (es-AR), `df_<n>` / `dv_<n>` = fecha + nivel A3500. Una celda vacía se
    omite (no es un cero); una ilegible es un problema que se lista."""
    infl: Dict[str, Any] = {}
    fechas: Dict[str, str] = {}
    valores: Dict[str, str] = {}
    problemas: List[str] = []
    nota = ""
    for k, v in form.multi_items():
        v = (v or "").strip() if isinstance(v, str) else ""
        if k.startswith("i_"):
            if not v:
                continue
            f = parse_ar_num(v)
            if f is None:
                problemas.append(f"inflación {proy.mes_label(k[2:])}: '{v}' no es un número")
            else:
                infl[k[2:]] = f
        elif k.startswith("df_"):
            fechas[k[3:]] = v
        elif k.startswith("dv_"):
            valores[k[3:]] = v
        elif k == "nota":
            nota = v
    deva: Dict[str, Any] = {}
    for n, f in fechas.items():
        v = valores.get(n, "")
        if not f and not v:
            continue
        iso = _fecha_iso(f)
        if iso is None:
            problemas.append(f"A3500: fecha '{f}' inválida (AAAA-MM-DD o DD/MM/AAAA)")
            continue
        if not v:
            continue
        fv = parse_ar_num(v)
        if fv is None:
            problemas.append(f"A3500 {iso}: '{v}' no es un número")
            continue
        deva[iso] = fv
    return {"inflacion": infl, "a3500": deva}, nota, problemas


# ── contexto de la pestaña ───────────────────────────────────────────────────
def _mes_sig(mes: str) -> str:
    y, m = int(mes[:4]), int(mes[5:7])
    return f"{y + (m // 12)}-{(m % 12) + 1:02d}"


def _fin_de_mes(d: date) -> date:
    return (d.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)


def _filas_inflacion(esc: Dict[str, Any], obs_df: Any) -> List[Dict[str, Any]]:
    """Meses observados (últimos `_OBS_MESES`, con el dato real, no editables)
    seguidos de los proyectados (editables). Un mes proyectado anterior o igual
    al último observado se marca `pisado`: la app usa el dato real."""
    filas: List[Dict[str, Any]] = []
    ultimo_obs = None
    if obs_df is not None and len(obs_df):
        pares = [(proy._a_date(ix), float(v)) for ix, v in zip(obs_df.index, obs_df["inflacionmom"].to_numpy())]
        pares = [p for p in pares if p[0] is not None][-_OBS_MESES:]
        for d, v in pares:
            mes = f"{d.year}-{d.month:02d}"
            filas.append({"mes": mes, "label": proy.mes_label(mes), "valor": v, "obs": True})
        ultimo_obs = f"{pares[-1][0].year}-{pares[-1][0].month:02d}" if pares else None
    for mes, v in sorted((esc.get("inflacion") or {}).items()):
        filas.append({"mes": mes, "label": proy.mes_label(mes), "valor": v, "obs": False,
                      "pisado": bool(ultimo_obs and mes <= ultimo_obs)})
    return filas


def _filas_a3500(esc: Dict[str, Any], ultimo_pub: Optional[date] = None) -> List[Dict[str, Any]]:
    """Una fecha anterior o igual al último A3500 publicado se marca `pisado`:
    la serie diaria arranca en el publicado y ese punto no se usa."""
    ult = ultimo_pub.isoformat() if ultimo_pub else None
    return [{"fecha": f, "valor": v, "label": date.fromisoformat(f).strftime("%d/%m/%Y"),
             "pisado": bool(ult and f <= ult)}
            for f, v in sorted((esc.get("a3500") or {}).items())]


def _unix(iso: Optional[str]) -> Optional[int]:
    from datetime import datetime, timezone
    if not iso:
        return None
    try:
        return int(datetime.fromisoformat(iso[:10]).replace(tzinfo=timezone.utc).timestamp())
    except ValueError:
        return None


def _chart_json(series: Dict[str, Any], label: str, ref: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """Un JSON por gráfico (cer / a3500 / inflamom) para charts.js
    `initProyecciones`: x epoch, y, corte, y la serie de REFERENCIA (vigente)
    cuando se previsualiza un borrador."""
    pl = proy.chart_payload(series, label)
    out: Dict[str, str] = {}
    for key, etiqueta in (("cer", "CER"), ("a3500", "A3500"), ("inflamom", "Inflación mensual (%)")):
        s = pl[key]
        d: Dict[str, Any] = {"serie": key, "label": etiqueta, "corte": _unix(s["corte"]),
                             "x": [_unix(p[0]) for p in s["pts"]], "y": [p[1] for p in s["pts"]],
                             "barras": key == "inflamom"}
        if ref is not None:
            r = ref[key]
            d["ref_x"], d["ref_y"] = [_unix(p[0]) for p in r["pts"]], [p[1] for p in r["pts"]]
        out[key] = json.dumps(d, separators=(",", ":"))
    return out


def _preview_ctx(series: Dict[str, Any], esc: Dict[str, Any], modo: str,
                 vigente_series: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ref = proy.chart_payload(vigente_series, "vigente") if vigente_series is not None else None
    return {"modo": modo, "resumen": proy.resumen(series, esc), "charts": _chart_json(series, modo, ref),
            "esc_resumen": proy.resumen_escenario(esc)}


def _ctx_pagina(request: Request) -> Dict[str, Any]:
    esc = proy.vigente()
    series = proy.calcular_vigente()
    obs = proy.observadas()
    return {
        "esc": esc, "meta": esc.get("meta") or {}, "puede_editar": _puede_editar(request),
        "filas_infl": _filas_inflacion(esc, obs["inflamom"]),
        "filas_a3500": _filas_a3500(esc, obs["ultimos"].get("a3500")),
        "ultimos": obs["ultimos"], "hoy": hoy_ba(), "historial": proy.historial(_HIST_N),
        "preview": _preview_ctx(series, esc, "vigente"),
        "ruta": proy.ruta().name, "mes_nuevo": _mes_sig(max(esc["inflacion"])) if esc.get("inflacion") else None,
        "fecha_nueva": (_fin_de_mes(date.fromisoformat(max(esc["a3500"])) + timedelta(days=1))).isoformat()
                       if esc.get("a3500") else _fin_de_mes(hoy_ba()).isoformat(),
    }


@router.get("/proyecciones", response_class=HTMLResponse)
async def proyecciones_page(request: Request, ok: str = "") -> HTMLResponse:
    ctx = await asyncio.get_running_loop().run_in_executor(None, _ctx_pagina, request)
    ctx["ok"] = ok
    return _render(request, "proyecciones.html", **ctx)


@router.post("/proyecciones/preview", response_class=HTMLResponse)
async def proyecciones_preview(request: Request) -> HTMLResponse:
    form = await request.form()
    raw, _nota, problemas = parse_form(form)
    if problemas:
        return _render(request, "partials/proyecciones_preview.html", error="; ".join(problemas))
    try:
        esc = proy.normalizar(raw)
    except ValueError as exc:
        return _render(request, "partials/proyecciones_preview.html", error=str(exc))

    def _calc() -> Dict[str, Any]:
        series = proy.calcular(esc)
        return _preview_ctx(series, esc, "borrador", proy.calcular_vigente())

    ctx = await asyncio.get_running_loop().run_in_executor(None, _calc)
    return _render(request, "partials/proyecciones_preview.html", **ctx)


@router.post("/proyecciones/csv")
async def proyecciones_csv(request: Request) -> Response:
    form = await request.form()
    serie = str(form.get("serie") or "cer")
    if serie not in proy.SERIES_CSV:
        return Response("serie desconocida", status_code=400)
    raw, _nota, problemas = parse_form(form)
    if problemas:
        return Response("; ".join(problemas), status_code=400)
    try:
        esc = proy.normalizar(raw)
    except ValueError as exc:
        return Response(str(exc), status_code=400)

    def _build() -> Tuple[bytes, str]:
        return proy.csv_de(proy.calcular(esc), serie)

    cuerpo, nombre = await asyncio.get_running_loop().run_in_executor(None, _build)
    return Response(content=cuerpo, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"',
                             "Content-Encoding": "identity", "Cache-Control": "no-store"})


@router.get("/proyecciones/futuros")
async def proyecciones_futuros() -> JSONResponse:
    """Senda A3500 implícita en los futuros DLR (mayorista): el precio de cada
    contrato (último, si no cierre previo) en su fin de mes — lo que hasta hoy
    se copiaba a mano de ROFEX al dict de indices.py."""
    from backend.services import futuros

    def _rows() -> List[Dict[str, Any]]:
        out = []
        for r in futuros.rows("may"):
            px = r.get("last") if r.get("last") else r.get("close")
            if not px or not r.get("vto") or (r.get("dias") or 0) <= 0:
                continue
            out.append({"fecha": r["vto"], "valor": round(float(px), 2), "contrato": r.get("label") or r.get("code"),
                        "fuente": "último" if r.get("last") else "cierre"})
        return out

    rows = await asyncio.get_running_loop().run_in_executor(None, _rows)
    return JSONResponse({"n": len(rows), "rows": rows})


# ── acciones (feature `proyecciones`, gate en main._FEATURE_PATHS) ──────────
def _alerta(request: Request, texto: str, ok: bool = False) -> HTMLResponse:
    return _render(request, "partials/proyecciones_msg.html", texto=texto, ok=ok)


async def _accion(request: Request, fn: Any, *args: Any) -> HTMLResponse:
    try:
        r = await asyncio.get_running_loop().run_in_executor(None, fn, *args)
    except ValueError as exc:
        return _alerta(request, str(exc))
    except Exception:  # noqa: BLE001
        logger.exception("[proyecciones] acción falló")
        return _alerta(request, "No se pudo aplicar: error interno (ver el log del server).")
    meta = (r.get("esc") or {}).get("meta") or {}
    resp = _alerta(request, f"Listo: {proy.resumen_escenario(r['esc'])} ({meta.get('accion')} por {meta.get('autor') or '?'}).", ok=True)
    resp.headers["HX-Redirect"] = "/proyecciones?ok=1"
    return resp


@router.post("/proyecciones/aplicar", response_class=HTMLResponse)
async def proyecciones_aplicar(request: Request) -> HTMLResponse:
    form = await request.form()
    raw, nota, problemas = parse_form(form)
    if problemas:
        return _alerta(request, "No se aplicó: " + "; ".join(problemas))
    if not raw["inflacion"] and not raw["a3500"]:
        return _alerta(request, "No se aplicó: las dos tablas están vacías.")
    return await _accion(request, proy.aplicar, raw, _user(request), nota)


@router.post("/proyecciones/deshacer", response_class=HTMLResponse)
async def proyecciones_deshacer(request: Request) -> HTMLResponse:
    return await _accion(request, proy.deshacer, _user(request))


@router.post("/proyecciones/restablecer", response_class=HTMLResponse)
async def proyecciones_restablecer(request: Request) -> HTMLResponse:
    return await _accion(request, proy.restablecer, _user(request))
