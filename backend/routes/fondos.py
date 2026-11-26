"""Fondos — tablero de performance vs benchmark y atribución (SÓLO superuser).

El gating fuerte está en el middleware de `main` (`/fondos` entero en
`_SUPERUSER_ONLY`) y la pestaña no aparece en la nav de los otros roles: son
los patrimonios y flujos de los fondos de la casa.

- GET  /fondos                 la página (controles + tablero + panel del fondo)
- GET  /fondos/tablero         tabla de todos los fondos: retornos por período
                               del fondo / exceso vs referencia / la referencia
- GET  /fondos/detalle         panel de un fondo: ventana, riesgo, gráficos,
                               meses, clases, flujos y atribución
- GET  /fondos/atribucion      qué activos y categorías explican el retorno de
                               la ventana (se abre a pedido desde el panel)
- POST /fondos/seguir          ★ agrega / quita un fondo de «mis fondos»
- POST /fondos/releer          relee los archivos ya (lo normal es solo)
- GET  /fondos/serie.csv       serie diaria del fondo y su referencia (es-AR)

Nada lee disco en el request: `services.fondos` carga en un thread y acá sólo
hay numpy sobre matrices en memoria (µs–ms). El HTML del tablero se memoiza
por (versión de la carga, parámetros, seguidos).
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, Response

from backend.locale_ar import fmt_date, fmt_hum, fmt_num
from backend.services import fondos as fsvc
from backend.services import fondos_attr as fattr
from backend.services import fondos_calc as fc

logger = logging.getLogger("backend.fondos.routes")

router = APIRouter(prefix="/fondos", tags=["fondos"])

VISTAS = (("f", "Retorno"), ("x", "vs referencia"), ("b", "Referencia"))
RANGOS = (("mtd", "MTD"), ("d30", "30d"), ("d90", "90d"), ("ytd", "YTD"),
          ("d365", "1 año"), ("d730", "2 años"), ("max", "Máx"))
_RANGO_KEYS = tuple(k for k, _ in RANGOS)
_MONEDA_SIMBOLO = {"ARS": "$", "USD": "US$", "USB": "US$"}
_MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")

_memo: Dict[Tuple, str] = {}
_MEMO_MAX = 64


def _render(request: Request, template: str, **ctx: Any) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, template, ctx)


def _user(request: Request) -> str:
    u = getattr(request.state, "user", None) or {}
    return str(u.get("username") or "_local")


# ── formato ──────────────────────────────────────────────────────────────────
def pct(v: Optional[float], dec: int = 2, signo: bool = False) -> str:
    """Fracción → '12,34%' (con signo opcional); None → '—'."""
    if v is None or not np.isfinite(v):
        return "—"
    s = fmt_num(v * 100.0, dec) + "%"
    return ("+" + s) if signo and v > 0 else s


def pp(v: Optional[float], dec: int = 2) -> str:
    """Diferencia de retornos (fracción) → '+1,23 pp'."""
    if v is None or not np.isfinite(v):
        return "—"
    return ("+" if v > 0 else "") + fmt_num(v * 100.0, dec) + " pp"


def cls(v: Optional[float], eps: float = 5e-5) -> str:
    if v is None or not np.isfinite(v):
        return ""
    return "var-up" if v > eps else ("var-down" if v < -eps else "")


def plata(v: Optional[float], moneda: str = "ARS") -> str:
    if v is None or not np.isfinite(v):
        return "—"
    return f"{_MONEDA_SIMBOLO.get(moneda, '$')} {fmt_hum(v)}"


def mes_lbl(aaaamm: str) -> str:
    try:
        return f"{_MESES[int(aaaamm[5:7]) - 1]}-{aaaamm[2:4]}"
    except (ValueError, IndexError):
        return aaaamm


def _filas_fmt(filas: List[Dict[str, Any]], ver: str, seg: List[int]) -> List[Dict[str, Any]]:
    """Celdas del tablero pre-formateadas (≈60 fondos × 9 períodos)."""
    seguidos = set(seg)
    out = []
    for r in filas:
        celdas = []
        for p in fc.PERIODO_KEYS:
            c = r["per"][p]
            f, b, x = c["f"], c["b"], c["x"]
            if ver == "x":
                txt, k = pp(x), cls(x)
            elif ver == "b":
                txt, k = pct(b), ""
            else:
                txt, k = pct(f), ""
            marca = ""
            if ver == "f" and x is not None:
                marca = "up" if x > 5e-5 else ("down" if x < -5e-5 else "")
            tip = ""
            if f is not None or b is not None:
                tip = f"Fondo {pct(f)} · referencia {pct(b)} · exceso {pp(x)}"
            celdas.append({"txt": txt, "cls": k, "marca": marca, "tip": tip})
        out.append({
            "cafci": r["cafci"], "corto": r["corto"], "nombre": r["nombre"], "clase": r["clase"],
            "tipo": r["tipo"], "tipo_lbl": fsvc.TIPOS.get(r["tipo"], r["tipo"] or "—"),
            "moneda": r["moneda"], "familia": r["familia"], "grupo": r["grupo"] or "—",
            "seg": r["cafci"] in seguidos,
            "pn": plata(r["pn"], r["moneda"]), "pn_n": r["pn"] or 0.0,
            "fecha": fmt_date(r["fecha"]) if r["fecha"] else "—", "atrasado": r["atrasado"],
            "vol": pct(r["vol"], 1), "te": pct(r["te"], 1), "max_dd": pct(r["max_dd"], 1),
            "bm": r["bm"] or "Sin benchmark", "sin_bm": r["bm"] is None, "celdas": celdas,
        })
    return out


def _estado_ctx() -> Dict[str, Any]:
    e = fsvc.estado()
    if e.get("hasta"):
        e["hasta_fmt"] = fmt_date(e["hasta"])
    return e


def _vs_validos(d: fsvc.Datos) -> List[Tuple[str, str]]:
    return [("bm", "Benchmark del fondo")] + fsvc.referencias(d)


def _vs_ok(d: Optional[fsvc.Datos], vs: str) -> str:
    vs = (vs or "bm").strip()
    if d is None or vs == "bm":
        return "bm"
    if vs in d.indices:
        return vs
    if vs.startswith("f:"):
        try:
            c = int(vs.split(":")[1])
        except (IndexError, ValueError):
            return "bm"
        return vs if c in d.fondos else "bm"
    return "bm"


# ── página ───────────────────────────────────────────────────────────────────
@router.get("", response_class=HTMLResponse)
async def fondos_page(request: Request, f: Optional[int] = None) -> HTMLResponse:
    d = fsvc.asegurar()
    fattr.asegurar()          # la historia de carteras de la atribución se arma sola, en un proceso aparte
    return _render(request, "fondos.html", estado=_estado_ctx(), vistas=VISTAS,
                   vs_opts=_vs_validos(d) if d else [("bm", "Benchmark del fondo")],
                   sel=f, periodos=fc.PERIODOS)


def _tablero_html(request: Request, d: fsvc.Datos, vs: str, ver: str, seg: List[int]) -> str:
    key = ("tab", d.version, vs, ver, tuple(seg))
    hit = _memo.get(key)
    if hit is not None:
        return hit
    filas = _filas_fmt(fsvc.tablero(d, vs), ver, seg)
    html = request.app.state.templates.get_template("partials/fondos_tablero.html").render(
        request=request, filas=filas, periodos=fc.PERIODOS, ver=ver, vs=vs, estado=_estado_ctx(),
        n_seg=sum(1 for r in filas if r["seg"]))
    if len(_memo) >= _MEMO_MAX:
        _memo.clear()
    _memo[key] = html
    return html


@router.get("/tablero", response_class=HTMLResponse)
async def fondos_tablero(request: Request, vs: str = "bm", ver: str = "f") -> HTMLResponse:
    d = fsvc.asegurar()
    if d is None:
        return _render(request, "partials/fondos_cargando.html", estado=_estado_ctx(), destino="tablero")
    vs = _vs_ok(d, vs)
    ver = ver if ver in ("f", "x", "b") else "f"
    seg = fsvc.seguidos(_user(request))
    html = await asyncio.get_running_loop().run_in_executor(None, _tablero_html, request, d, vs, ver, seg)
    return HTMLResponse(html)


# ── detalle de un fondo ──────────────────────────────────────────────────────
def _json(obj: Any) -> str:
    """JSON para embeber en <script type="application/json"> (sin `<`: un
    nombre de fondo no puede cerrar el tag)."""
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).replace("<", "\\u003c")


def _charts(det: Dict[str, Any], moneda: str) -> Dict[str, str]:
    """JSON de los gráficos (uPlot en charts.js initFondos): rendimiento base
    100, exceso acumulado, caída desde el máximo y patrimonio + flujos."""
    s = det["serie"]
    series = [{"label": s["nombre"], "y": s["f"], "color": "acc"}]
    if s["b"] is not None:
        series.append({"label": s["ref"], "y": s["b"], "color": "mut", "dash": True})
    out = {"perf": _json({"x": s["x"], "series": series, "ref": 100, "dec": 2, "nombre": "fondo-vs-ref"})}
    if s["x_exc"] is not None:
        out["exc"] = _json({"x": s["x"], "series": [{"label": "Exceso acumulado (%)", "y": s["x_exc"],
                                                    "color": "acc", "area": True}],
                            "ref": 0, "dec": 2, "suf": "%", "nombre": "exceso"})
    out["dd"] = _json({"x": s["x"], "series": [{"label": "Caída desde el máximo (%)", "y": s["dd"],
                                               "color": "red", "area": True}],
                       "ref": 0, "dec": 2, "suf": "%", "nombre": "caida"})
    fl = det["flujos"]
    if fl.get("pn"):
        ser = [{"label": f"Patrimonio ({_MONEDA_SIMBOLO.get(moneda, '$')})", "y": fl["pn"], "color": "acc", "hum": True}]
        if fl.get("neto"):
            ser.append({"label": "Suscripciones netas", "y": fl["neto"], "color": "signo", "bars": True,
                        "scale": "y2", "hum": True})
        out["pn"] = _json({"x": fl["x"], "series": ser, "dec": 0, "hum": True, "nombre": "patrimonio"})
    return out


def _detalle_ctx(d: fsvc.Datos, f: int, clase: Optional[str], vs: str, rango: str,
                 desde: Optional[str], hasta: Optional[str], user: str) -> Optional[Dict[str, Any]]:
    det = fsvc.detalle(d, f, clase or None, vs, rango, desde or None, hasta or None)
    if det is None:
        return None
    fo: fsvc.Fondo = det["fondo"]
    fila = det["fila"]
    periodos = [{"k": k, "lbl": lbl, "largo": largo, "f": pct(fila["per"][k]["f"]), "b": pct(fila["per"][k]["b"]),
                 "x": pp(fila["per"][k]["x"]), "cls": cls(fila["per"][k]["x"])}
                for k, lbl, largo in fc.PERIODOS]
    v = det["ventana"]
    rg = det["riesgo"]
    es_mm = fo.tipo == "PF"
    ventana = {"desde": fmt_date(v["desde"]), "hasta": fmt_date(v["hasta"]), "dias": v["dias"], "ruedas": v["ruedas"],
               "f": pct(v["f"]), "b": pct(v["b"]), "x": pp(v["x"]), "x_cls": cls(v["x"]),
               "f_anual": pct(v["f_tna"] if es_mm else v["f_tea"]), "b_anual": pct(v["b_tna"] if es_mm else v["b_tea"]),
               "anual_lbl": "TNA" if es_mm else "TEA",
               "fee": pct(v.get("fee"), 2) if v.get("fee") is not None else None,
               "f_bruto": pct(v.get("f_bruto")) if v.get("f_bruto") is not None else None,
               "x_bruto": pp(v.get("x_bruto")), "x_bruto_cls": cls(v.get("x_bruto"))}
    riesgo = [
        ("Volatilidad anual", pct(rg["vol"], 1), "Desvío de los retornos diarios × √252."),
        ("Tracking error", pct(rg["te"], 1), "Desvío del exceso diario contra la referencia, anualizado."),
        ("Information ratio", fmt_num(rg["ir"], 2) if rg["ir"] is not None else "—", "Exceso anualizado ÷ tracking error."),
        ("Beta", fmt_num(rg["beta"], 2) if rg["beta"] is not None else "—", "Sensibilidad de los retornos diarios a la referencia."),
        ("Correlación", fmt_num(rg["corr"], 2) if rg["corr"] is not None else "—", "Correlación de los retornos diarios con la referencia."),
        ("Ruedas arriba", pct(rg["hit"], 0), "Porcentaje de ruedas en que el fondo rindió más que la referencia."),
        ("Máxima caída", pct(rg["max_dd"], 1), "Mayor caída desde un máximo dentro de la ventana."),
        ("Mejor / peor rueda", f"{pct(rg['mejor'])} / {pct(rg['peor'])}", "Mayor y menor retorno diario de la ventana."),
    ]
    # barra del exceso mensual: 3 puntos porcentuales llenan la celda
    meses = [{"mes": mes_lbl(m["mes"]), "f": pct(m["f"]), "b": pct(m["b"]), "x": pp(m["x"]), "cls": cls(m["x"]),
              "w": min(100, int(abs(m["x"]) / 0.03 * 100)) if m["x"] is not None else 0}
             for m in det["meses"]]
    clases = [{"clase": c["clase"], "fee": pct(c["fee"], 2) if c.get("fee") is not None else "—",
               "vcp": fmt_num(c["vcp"], 6), "fecha": fmt_date(c["fecha"]),
               "pn": plata(c["pn"], fo.moneda), "viva": c["viva"], "principal": c["principal"], "elegida": c["elegida"],
               "per": [pct(c["per"].get(k)) for k in ("d1", "mtd", "d30", "ytd", "d365")]}
              for c in det["clases"]]
    fl = det["flujos"]
    pn_var = (fl["pn_fin"] - fl["pn_ini"]) if fl["pn_ini"] is not None and fl["pn_fin"] is not None else None
    neto = fl.get("total_neto")
    flujos = {"fuente": fl["fuente"], "pn_ini": plata(fl["pn_ini"], fo.moneda), "pn_fin": plata(fl["pn_fin"], fo.moneda),
              "pn_var": plata(pn_var, fo.moneda), "pn_var_cls": cls(pn_var),
              "neto": plata(neto, fo.moneda), "neto_cls": cls(neto),
              "susc": plata(fl.get("total_susc"), fo.moneda), "resc": plata(fl.get("total_resc"), fo.moneda),
              "mercado": plata(pn_var - neto if pn_var is not None and neto is not None else None, fo.moneda),
              "mercado_cls": cls(pn_var - neto if pn_var is not None and neto is not None else None)}
    pesos = det["pesos"] or {}
    pesos_txt = " + ".join(
        [f"{fmt_num(w * 100, 0)}% {fsvc._IDX_POR_CLAVE[k][1]}" for k, w in pesos.items() if k in fsvc._IDX_POR_CLAVE]
        + ([f"{fmt_num(pesos['spread'] * 10000, 0)} bps"] if pesos.get("spread") else []))
    otros = sorted(((x.cafci, x.corto) for x in d.fondos.values() if x.cafci != fo.cafci), key=lambda t: t[1])
    return {"fo": fo, "fila": fila, "clase": det["clase"], "vs": det["vs"], "ref": det["ref"],
            "tipo_lbl": fsvc.TIPOS.get(fo.tipo, fo.tipo or "—"), "seg": fo.cafci in set(fsvc.seguidos(user)),
            "pn": plata(fila["pn"], fo.moneda), "vcp": fmt_num(fila["vcp"], 6), "fecha": fmt_date(fila["fecha"]),
            "periodos": periodos, "ventana": ventana, "riesgo": riesgo, "meses": meses, "clases": clases,
            "flujos": flujos, "charts": _charts(det, fo.moneda), "pesos_txt": pesos_txt,
            "rango": rango if rango in _RANGO_KEYS else "ytd", "desde": desde or "", "hasta": hasta or "",
            "rangos": RANGOS, "vs_opts": _vs_validos(d), "otros": otros, "n_ruedas": rg["n"]}


def _fecha_ok(s: Optional[str]) -> Optional[str]:
    s = (s or "").strip()[:10]
    if not s:
        return None
    try:
        return str(np.datetime64(s, "D"))
    except ValueError:
        return None


@router.get("/detalle", response_class=HTMLResponse)
async def fondos_detalle(request: Request, f: int, clase: str = "", vs: str = "bm", rango: str = "ytd",
                         desde: str = "", hasta: str = "") -> HTMLResponse:
    d = fsvc.asegurar()
    if d is None:
        return _render(request, "partials/fondos_cargando.html", estado=_estado_ctx(), destino="detalle", f=f)
    vs = _vs_ok(d, vs)
    user = _user(request)
    de, ha = _fecha_ok(desde), _fecha_ok(hasta)
    key = ("det", d.version, f, clase.strip(), vs, rango, de, ha, f in set(fsvc.seguidos(user)))
    hit = _memo.get(key)
    if hit is not None:
        return HTMLResponse(hit)

    def _armar() -> str:
        ctx = _detalle_ctx(d, f, clase.strip(), vs, rango, de, ha, user)
        return request.app.state.templates.get_template("partials/fondos_detalle.html").render(
            request=request, det=ctx, f=f)

    html = await asyncio.get_running_loop().run_in_executor(None, _armar)
    if len(_memo) >= _MEMO_MAX:
        _memo.clear()
    _memo[key] = html
    return HTMLResponse(html)


# ── acciones ─────────────────────────────────────────────────────────────────
@router.post("/seguir", response_class=HTMLResponse)
async def fondos_seguir(request: Request, f: int = Form(...)) -> Response:
    d = fsvc.asegurar()
    if d is not None and f not in d.fondos:
        return HTMLResponse('<div class="alert alert-error">Fondo desconocido.</div>', status_code=400)
    try:
        await asyncio.get_running_loop().run_in_executor(None, fsvc.seguir, _user(request), f)
    except OSError as exc:
        return HTMLResponse(f'<div class="alert alert-error">No pude guardar: {exc}</div>', status_code=500)
    return Response(status_code=204, headers={"HX-Trigger": "fondos-refresh"})


# ── atribución ───────────────────────────────────────────────────────────────
_PALETA = ("p0", "p1", "p2", "p3", "p4", "p5")


def _attr_filas(filas: List[Dict[str, Any]], tope: float) -> List[Dict[str, Any]]:
    out = []
    for g in filas:
        out.append({"nombre": g["nombre"], "desc": g.get("desc") or "", "grupo": g.get("grupo") or "",
                    "w_prom": pct(g["w_prom"], 1), "w_hoy": pct(g["w_hoy"], 1) if abs(g["w_hoy"]) > 1e-9 else "—",
                    "ret": pct(g["ret"]) if g["ret"] is not None else "—",
                    "c": pp(g["c"]), "cls": cls(g["c"], 5e-6), "w": min(100, int(abs(g["c"]) / tope * 100)) if tope else 0,
                    "e": pp(g["e"]) if g["e"] is not None else "—", "e_cls": cls(g["e"], 5e-6)})
    return out


def _attr_ctx(res: Dict[str, Any], fo: fsvc.Fondo) -> Dict[str, Any]:
    """Atribución pre-formateada es-AR + JSON de los dos gráficos."""
    tope = max((abs(g["c"]) for g in res["grupos"]), default=0.0)
    tope_a = max((abs(g["c"]) for g in res["suben"] + res["bajan"]), default=0.0)
    s = res["serie"]
    dim_lbl = dict(fattr.DIMS)[res["dim"]]
    charts = {
        "expl": _json({"x": s["x"], "dec": 2, "suf": "%", "ref": 0, "nombre": "cuotaparte-vs-cartera", "series": [
            {"label": f"Cuotaparte {fo.corto} (%)", "y": s["fondo"], "color": "acc"},
            {"label": "Explicado por la cartera (%)", "y": s["cartera"], "color": "mut", "dash": True}]}),
        "grupos": _json({"x": s["x"], "dec": 2, "suf": " pp", "ref": 0, "nombre": "contribucion-por-grupo", "series": [
            {"label": g["nombre"], "y": g["y"], "color": _PALETA[i % len(_PALETA)]}
            for i, g in enumerate(s["grupos"])]}),
    }
    notas = []
    if res["recortada"]:
        notas.append(f"La ventana pedida arranca el {fmt_date(res['pedido_desde'])}, pero las carteras de este fondo en el "
                     f"caché empiezan el {fmt_date(res['cobertura']['desde'])}: la atribución va desde el "
                     f"{fmt_date(res['desde'])} y todos los números de este cuadro son de ese tramo.")
    if res["cobros"]:
        notas.append(f"{res['cobros']} cobro(s) de cupón / amortización sumados al retorno del activo (cronograma de la ficha).")
    if res["vencidos"]:
        notas.append(f"{res['vencidos']} vencimiento(s) devengados hasta su fecha (tasa del plazo fijo, descuento a la par o pago final).")
    if res["sin_precio"]:
        notas.append(f"{res['sin_precio']} salida(s) de cartera sin precio de venta (peso promedio {pct(res['sin_precio_peso'], 1)}): "
                     "el resultado del último día de esas tenencias queda en «sin explicar».")
    saltos = [{"activo": x["activo"], "fecha": fmt_date(x["fecha"]), "r": pct(x["r"], 1, True), "w": pct(x["w"], 1)}
              for x in res["saltos"]]
    return {
        "dim": res["dim"], "dim_lbl": dim_lbl, "dims": fattr.DIMS,
        "desde": fmt_date(res["desde"]), "hasta": fmt_date(res["hasta"]), "dias": res["dias"], "ruedas": res["ruedas"],
        "total": pct(res["total"]), "cartera": pct(res["cartera"]), "cartera_pp": pp(res["cartera"]),
        "residual": pp(res["residual"]), "residual_cls": cls(res["residual"]),
        "fee": pct(res["fee"], 2) if res["fee"] is not None else None,
        "fee_est": pp(res["fee_est"]) if res["fee_est"] is not None else None,
        "otros": pp(res["otros"]) if res["otros"] is not None else None, "otros_cls": cls(res["otros"]),
        "ref": res["ref"], "bench": pct(res["bench"]) if res["bench"] is not None else None,
        "exceso": pp(res["exceso"]), "exceso_cls": cls(res["exceso"]),
        "exceso_cartera": pp(res["exceso_cartera"]), "exceso_cartera_cls": cls(res["exceso_cartera"]),
        "exceso_resto": pp(res["exceso"] - res["exceso_cartera"]) if res["exceso"] is not None and res["exceso_cartera"] is not None else "—",
        "peso_abierto": pct(res["peso_abierto"], 1) if res["peso_abierto"] is not None else "—",
        "grupos": _attr_filas(res["grupos"], tope), "suben": _attr_filas(res["suben"], tope_a),
        "bajan": _attr_filas(res["bajan"], tope_a), "n_activos": res["n_activos"],
        "charts": charts, "notas": notas, "saltos": saltos,
        "cobertura": {"desde": fmt_date(res["cobertura"]["desde"]), "hasta": fmt_date(res["cobertura"]["hasta"]),
                      "dias": res["cobertura"]["dias"]},
    }


@router.get("/atribucion", response_class=HTMLResponse)
async def fondos_atribucion(request: Request, f: int, clase: str = "", vs: str = "bm", rango: str = "ytd",
                            desde: str = "", hasta: str = "", dim: str = "clasif") -> HTMLResponse:
    """Atribución del rendimiento de la ventana. La historia de carteras se
    arma sola en un proceso aparte (la primera vez tarda un par de minutos:
    el partial se vuelve a pedir solo) y la de cada fondo se lee del caché
    local en el executor la primera vez que se abre."""
    d = fsvc.asegurar()
    dim = dim if dim in fattr.DIM_KEYS else "clasif"
    de, ha = _fecha_ok(desde), _fecha_ok(hasta)
    rango = rango if rango in _RANGO_KEYS else "ytd"
    qs = {"f": f, "clase": clase.strip(), "vs": vs, "rango": rango, "desde": de or "", "hasta": ha or ""}
    if d is None or f not in d.fondos:
        return _render(request, "partials/fondos_attr.html", a=None, qs=qs, dim=dim, estado={"cargando": d is None},
                       motivo=None if d is None else "No encontré ese fondo.")
    vs = _vs_ok(d, vs)
    qs["vs"] = vs
    est = fattr.asegurar()
    key = ("attr", d.version, est["version"], f, qs["clase"], vs, rango, de, ha, dim)
    hit = _memo.get(key)
    if hit is not None:
        return HTMLResponse(hit)
    fo = d.fondos[f]

    def _armar() -> str:
        motivo = None
        ctx = None
        fa = fattr.fondo(d, f) if fo.cod is not None else None
        if fo.cod is None:
            motivo = ("Este fondo no tiene código de ESCO en Delta_Fondos: no lo puedo cruzar con las carteras diarias.")
        elif fa is not None:
            col = d.col(f, qs["clase"] or None)
            i_fin = fc.ultimo_valido(d.vcp[:, col])
            i0, i1 = fsvc.rango_indices(d, i_fin, rango, de, ha)
            res = fattr.atribucion(fa, d, f, qs["clase"] or None, vs, i0, i1, dim) if i1 > i0 >= 0 else None
            if res is None:
                motivo = (f"No hay dos carteras de este fondo dentro de la ventana (en el caché: {len(fa.dias)} días, del "
                          f"{fmt_date(str(fa.dias[0]))} al {fmt_date(str(fa.dias[-1]))}).")
            else:
                ctx = _attr_ctx(res, fo)
        elif not est["cargando"] and est["listo"]:
            motivo = est["error"] or "No hay carteras diarias de este fondo en la ventana que guarda el caché."
        return request.app.state.templates.get_template("partials/fondos_attr.html").render(
            request=request, a=ctx, qs=qs, dim=dim, estado=est, motivo=motivo, fo=fo)

    html = await asyncio.get_running_loop().run_in_executor(None, _armar)
    if not est["cargando"] and est["listo"]:
        if len(_memo) >= _MEMO_MAX:
            _memo.clear()
        _memo[key] = html
    return HTMLResponse(html)


@router.post("/releer", response_class=HTMLResponse)
async def fondos_releer(request: Request) -> Response:
    await asyncio.get_running_loop().run_in_executor(None, fsvc.cargar_ahora)
    _memo.clear()
    return Response(status_code=204, headers={"HX-Trigger": "fondos-refresh"})


@router.get("/serie.csv")
async def fondos_serie_csv(request: Request, f: int, clase: str = "", vs: str = "bm",
                           desde: str = "", hasta: str = "") -> Response:
    """Serie diaria del fondo (cuotaparte, patrimonio de la clase, retorno) y
    de su referencia (índice y retorno), CSV es-AR."""
    d = fsvc.asegurar()
    if d is None or f not in d.fondos:
        return Response("Sin datos", status_code=404, media_type="text/plain")
    vs = _vs_ok(d, vs)

    def _armar() -> bytes:
        col = d.col(f, clase.strip() or None)
        y = d.vcp[:, col]
        i_fin = fc.ultimo_valido(y)
        i0, i1 = fsvc.rango_indices(d, i_fin, "max", _fecha_ok(desde), _fecha_ok(hasta))
        k0 = fc.ultimo_valido_desde(y, max(i0, 0))
        i0 = k0 if 0 <= k0 <= i1 else max(i0, 0)
        ref, ref_nombre = fsvc.serie_referencia(d, f, vs)
        ry = fc.variaciones(y)
        rb = fc.variaciones(ref) if ref is not None else None
        buf = io.StringIO()
        titulo_ref = (ref_nombre if ref is not None else "Referencia").replace(";", ",").replace("\n", " ")
        buf.write("Fecha;Cuotaparte;Patrimonio clase;Retorno diario %;"
                  f"{titulo_ref};Retorno referencia %;Exceso pp\r\n")

        def n(v: float, dec: int) -> str:
            return "" if not np.isfinite(v) else f"{v:.{dec}f}".replace(".", ",")

        for i in range(i0, i1 + 1):
            b = ref[i] if ref is not None else np.nan
            rbi = rb[i] if rb is not None else np.nan
            buf.write(f"{fmt_date(str(d.fechas[i]))};{n(y[i], 6)};{n(d.pn[i, col], 2)};{n(ry[i] * 100, 4)};"
                      f"{n(b, 6)};{n(rbi * 100, 4)};{n((ry[i] - rbi) * 100, 4)}\r\n")
        return ("﻿" + buf.getvalue()).encode("utf-8")

    cuerpo = await asyncio.get_running_loop().run_in_executor(None, _armar)
    nombre = "".join(ch if ch.isalnum() else "_" for ch in d.fondos[f].corto)[:40] or "fondo"
    return Response(cuerpo, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="fondo_{nombre}.csv"'})
