"""Panel de administración (sólo superuser) — CRUD de usuarios y config de las
pestañas visibles por rol.

El acceso a /admin ya lo restringe el middleware al superuser; acá igual se
revalida de forma defensiva. Las mutaciones re-renderizan la página con un
mensaje de resultado (sin htmx: es un panel de baja frecuencia).
"""
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from backend.config import settings
from backend.services import auth

router = APIRouter(prefix="/admin", tags=["admin"])


def _guard(request: Request) -> bool:
    u = getattr(request.state, "user", None)
    return bool(u and u.get("role") == "superuser")


def _excel_bases(request: Request) -> dict:
    """Bases para instalar el add-in. Topología de la mesa: CADA UNO corre la
    app en su notebook → el manifest tiene que apuntar a `localhost`, así el
    add-in de cada compu pega contra SU instancia y el mismo archivo sirve en
    todas. OJO: Office sólo tolera http en el TASKPANE — el runtime de las
    funciones =OMS.* exige HTTPS (por http queda "iniciando el runtime…" y
    las celdas en #N/D). Con el puente TLS activo, la base local es la https
    (la única con la que las celdas andan); sin puente se cae a http con
    aviso en la tarjeta. La IP LAN queda para un server centralizado."""
    from backend.routes import excel as excel_routes
    from backend.services import tls_bridge

    tls_port = tls_bridge.active_port()
    ip = excel_routes.lan_ip()
    if tls_port:
        # La IP https sólo sirve si el puente escucha fuera de loopback (flujo
        # server centralizado: TLS_BRIDGE_HOST=0.0.0.0 + CA confiada en cada PC).
        ip_base = f"https://{ip}:{tls_port}" if ip and settings.tls_bridge_host not in (
            "127.0.0.1", "localhost", "::1") else None
        return {"local": f"https://localhost:{tls_port}", "ip": ip_base, "tls": True}
    port = request.url.port
    suf = f":{port}" if port else ""
    scheme = request.url.scheme
    return {"local": f"{scheme}://localhost{suf}",
            "ip": f"{scheme}://{ip}{suf}" if ip else None,
            "tls": scheme == "https"}


def _ctx(request: Request, msg: Optional[str] = None, error: Optional[str] = None) -> HTMLResponse:
    from backend.services import positions

    rt = auth.role_tabs()
    # Las tabs superuser-only (Alertas) no se ofrecen como checkbox: aunque se
    # tildaran, el middleware las corta con 403 — sería un link muerto.
    tabs = [{"key": k, "label": lbl} for k, lbl, _ in auth.TABS
            if k not in auth._SUPERUSER_ONLY_TABS]
    rf = auth.role_features()
    return request.app.state.templates.TemplateResponse(
        request, "admin.html",
        {"users": auth.list_users(), "roles": auth.ROLES, "role_labels": auth.ROLE_LABELS,
         "tabs": tabs, "role_tabs": {r: set(rt.get(r, [])) for r in ("premium", "basico")},
         "features": [{"key": k, "label": lbl} for k, lbl in auth.FEATURES],
         "role_features": {r: set(rf.get(r, [])) for r in ("premium", "basico")},
         # Todos los fondos cargados (vista superuser) — para el editor de
         # visibilidad por usuario. [] si no hay carteras: la tarjeta lo avisa.
         # is_loaded(): sólo si el cache YA está (el warmup lo puebla al boot)
         # — nunca leer Excel acá adentro, que esto corre en el event loop.
         "fondos_all": positions.fondos() if positions.is_loaded() else [],
         "excel_bases": _excel_bases(request),
         "msg": msg, "error": error},
    )


@router.get("", response_class=HTMLResponse)
async def admin_page(request: Request) -> HTMLResponse:
    if not _guard(request):
        return HTMLResponse("<h1>403</h1>", status_code=403)
    return _ctx(request)


@router.post("/users", response_class=HTMLResponse)
async def create_user(request: Request, username: str = Form(...), password: str = Form(...),
                      role: str = Form("basico"), email: str = Form("")) -> HTMLResponse:
    if not _guard(request):
        return HTMLResponse("<h1>403</h1>", status_code=403)
    try:
        # PBKDF2 (~50 ms GIL-bound) + fsync → threadpool, como el login.
        await asyncio.get_running_loop().run_in_executor(
            None, auth.create_user, username, password, role, email)
        return _ctx(request, msg=f"Usuario '{username.strip().lower()}' creado.")
    except auth.AuthError as exc:
        return _ctx(request, error=str(exc))


@router.post("/users/password", response_class=HTMLResponse)
async def reset_password(request: Request, username: str = Form(...), password: str = Form(...)) -> HTMLResponse:
    if not _guard(request):
        return HTMLResponse("<h1>403</h1>", status_code=403)
    try:
        # PBKDF2 (~50 ms GIL-bound) + fsync → threadpool, como el login.
        await asyncio.get_running_loop().run_in_executor(
            None, auth.set_password, username, password)
        return _ctx(request, msg=f"Contraseña de '{username}' actualizada.")
    except auth.AuthError as exc:
        return _ctx(request, error=str(exc))


@router.post("/users/role", response_class=HTMLResponse)
async def update_role(request: Request, username: str = Form(...), role: str = Form(...)) -> HTMLResponse:
    if not _guard(request):
        return HTMLResponse("<h1>403</h1>", status_code=403)
    try:
        auth.update_user(username, role=role)
        return _ctx(request, msg=f"Rol de '{username}' → {role}.")
    except auth.AuthError as exc:
        return _ctx(request, error=str(exc))


@router.post("/users/delete", response_class=HTMLResponse)
async def delete_user(request: Request, username: str = Form(...)) -> HTMLResponse:
    if not _guard(request):
        return HTMLResponse("<h1>403</h1>", status_code=403)
    # no permitir auto-borrado del superuser logueado
    me = request.state.user["username"]
    if username.strip().lower() == me:
        return _ctx(request, error="No podés borrar tu propio usuario logueado.")
    try:
        auth.delete_user(username)
        return _ctx(request, msg=f"Usuario '{username}' borrado.")
    except auth.AuthError as exc:
        return _ctx(request, error=str(exc))


@router.post("/users/excel", response_class=HTMLResponse)
async def set_excel(request: Request, username: str = Form(...), enabled: str = Form("0")) -> HTMLResponse:
    """Habilita/corta el acceso del add-in de Excel para un usuario (token por
    usuario; cortar invalida el token al instante sin borrarlo)."""
    if not _guard(request):
        return HTMLResponse("<h1>403</h1>", status_code=403)
    try:
        on = enabled == "1"
        auth.set_excel_access(username, on)
        verbo = "habilitado" if on else "cortado"
        return _ctx(request, msg=f"Acceso Excel {verbo} para '{username.strip().lower()}'.")
    except auth.AuthError as exc:
        return _ctx(request, error=str(exc))


@router.post("/users/excel/regen", response_class=HTMLResponse)
async def regen_excel(request: Request, username: str = Form(...)) -> HTMLResponse:
    if not _guard(request):
        return HTMLResponse("<h1>403</h1>", status_code=403)
    try:
        auth.regen_excel_token(username)
        return _ctx(request, msg=f"Token de Excel de '{username.strip().lower()}' regenerado "
                                 "(el anterior dejó de valer).")
    except auth.AuthError as exc:
        return _ctx(request, error=str(exc))


@router.post("/users/fondos", response_class=HTMLResponse)
async def set_fondos(request: Request) -> HTMLResponse:
    """Fondos visibles del usuario (tenencias): checkbox `todos` (default) o
    allowlist de `cod` (multi). Lista vacía = no ve ninguna cartera. El filtro
    lo aplican los providers server-side (services.positions) en Posiciones /
    Matriz / YAS / Comparador / Curvas."""
    if not _guard(request):
        return HTMLResponse("<h1>403</h1>", status_code=403)
    form = await request.form()
    username = str(form.get("username") or "")
    try:
        if form.get("todos"):
            auth.set_visible_fondos(username, None)
            return _ctx(request, msg=f"'{username.strip().lower()}' ve todos los fondos.")
        cods = [int(c) for c in form.getlist("cod")]
        auth.set_visible_fondos(username, cods)
        n = len(cods)
        det = f"{n} fondo{'s' if n != 1 else ''}" if n else "NINGÚN fondo"
        return _ctx(request, msg=f"'{username.strip().lower()}' ahora ve {det}.")
    except (auth.AuthError, ValueError) as exc:
        return _ctx(request, error=str(exc))


@router.post("/tabs", response_class=HTMLResponse)
async def set_tabs(request: Request) -> HTMLResponse:
    """Guarda las pestañas visibles por rol. El form manda checkboxes
    `tab_<role>_<key>`; leemos todos y reconstruimos cada set."""
    if not _guard(request):
        return HTMLResponse("<h1>403</h1>", status_code=403)
    form = await request.form()
    try:
        for role in ("premium", "basico"):
            prefix = f"tab_{role}_"
            keys = [k[len(prefix):] for k in form.keys() if k.startswith(prefix)]
            auth.set_role_tabs(role, keys)
        return _ctx(request, msg="Permisos de pestañas actualizados.")
    except auth.AuthError as exc:
        return _ctx(request, error=str(exc))


@router.post("/features", response_class=HTMLResponse)
async def set_features(request: Request) -> HTMLResponse:
    """Features (paneles opcionales) por rol — checkboxes `feat_<role>_<key>`,
    mismo esquema que /admin/tabs. El superuser las tiene todas siempre."""
    if not _guard(request):
        return HTMLResponse("<h1>403</h1>", status_code=403)
    form = await request.form()
    try:
        for role in ("premium", "basico"):
            prefix = f"feat_{role}_"
            keys = [k[len(prefix):] for k in form.keys() if k.startswith(prefix)]
            auth.set_role_features(role, keys)
        return _ctx(request, msg="Features por rol actualizadas.")
    except auth.AuthError as exc:
        return _ctx(request, error=str(exc))


# ── Salud de datos + errores recientes (tarjeta on-demand, superuser) ────────
def _sec(fn) -> dict:
    """Sección best-effort: la tarjeta de salud NUNCA tira — un servicio roto
    muestra su error como dato. Valores compuestos se resumen (tipo[len])."""
    try:
        d = fn() or {}
        if not isinstance(d, dict):
            return {"valor": d}
        out = {}
        for k, v in d.items():
            if isinstance(v, (str, int, float, bool)) or v is None:
                out[str(k)] = v
            else:
                try:
                    out[str(k)] = f"{type(v).__name__}[{len(v)}]"
                except TypeError:
                    out[str(k)] = type(v).__name__
        return out
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:140]}


@router.get("/salud", response_class=HTMLResponse)
async def admin_salud(request: Request) -> HTMLResponse:
    """Salud de datos en una tarjeta: feed WS, store, seq-cache (ahorro 304),
    pollers MAE/CAFCI, macro BCRA, warmup, OMS — más el ring de errores.
    On-demand (carga al abrir /admin + refresh cada 60 s con la página
    abierta): cero costo en el hot path. Todo el gather corre en el pool."""
    if not _guard(request):
        return HTMLResponse("<h1>403</h1>", status_code=403)

    def _gather():
        import os
        from datetime import datetime as _dt

        from backend import cache_seq
        from backend.services import (bond_universe, cafci_api, errores, historico,
                                      historico_writer, mae as mae_svc,
                                      marketdata_store, oms)
        from backend.services.primary_ws import get_ws_client
        from backend.services.warmup import get_daemon

        ws = get_ws_client()
        st = marketdata_store.get_store()

        def _store():
            sy = st.symbols()
            q = 0
            for s_ in sy:
                snap = st.get(s_)
                if snap and (snap.last is not None or snap.bid is not None
                             or snap.offer is not None):
                    q += 1
            return {"seq": st.seq(), "símbolos": len(sy), "cotizando": q}

        def _bcra():
            h = historico.status()
            out = {"ok": h.get("loaded"), "series": h.get("n")}
            try:
                mt = os.path.getmtime(h.get("path") or "")
                out["backup"] = _dt.fromtimestamp(mt).strftime("%d/%m %H:%M")
            except (OSError, TypeError):
                pass
            return out

        def _cache():
            cs = dict(cache_seq.stats)
            tot = sum(cs.values())
            cs["ahorro 304"] = f"{(cs['hit_304'] + cs['miss_304']) / tot * 100:.0f}%" if tot else "—"
            return cs

        def _oms():
            kb = 0
            try:
                if os.path.isfile(oms._AUDIT_PATH):
                    kb = round(os.path.getsize(oms._AUDIT_PATH) / 1024)
            except OSError:
                pass
            return {"live": oms.is_live(), "kill": oms.kill_switch(), "audit_KB": kb}

        secs = [
            ("Feed broker (WS)", _sec(lambda: {"auth": ws.authenticated,
                                               "vivo": ws.feed_alive, **(ws.stats() or {})})),
            ("Store de mercado", _sec(_store)),
            ("Seq-cache (render compartido)", _sec(_cache)),
            ("MAE (OTC)", _sec(mae_svc.status)),
            ("CAFCI API", _sec(cafci_api.status)),
            ("Macro BCRA", _sec(_bcra)),
            ("Base histórica px/tasas", _sec(historico_writer.estado)),
            ("Universo + warmup", _sec(lambda: {"bonos": len(bond_universe.all_codes()),
                                                **(get_daemon().stats() or {})})),
            ("OMS", _sec(_oms)),
        ]
        return secs, errores.ultimos(40)

    secs, errs = await asyncio.get_running_loop().run_in_executor(None, _gather)
    return request.app.state.templates.TemplateResponse(
        request, "partials/admin_salud.html", {"secs": secs, "errs": errs})


# ── Auditoría del OMS: visor filtrable + export CSV (superuser) ──────────────
_AUD_COLS = ("ts", "event", "live", "user", "code", "side", "qty", "price",
             "account", "motivo")


def _audit_filtrado(q: str, evento: str, n: int) -> list:
    import json as _json

    from backend.services import oms
    recs = oms.audit_tail(max(50, min(int(n or 300), 5000)))
    ql = (q or "").strip().lower()
    ev = (evento or "").strip().lower()
    out = []
    for r in recs:
        if not isinstance(r, dict):
            continue
        if ev and not str(r.get("event", "")).lower().startswith(ev):
            continue
        if ql and ql not in _json.dumps(r, ensure_ascii=False, default=str).lower():
            continue
        out.append(r)
    return out


@router.get("/auditoria", response_class=HTMLResponse)
async def admin_auditoria(request: Request, q: str = "", evento: str = "",
                          n: int = 300) -> HTMLResponse:
    """Visor del audit trail (oms_audit.jsonl): últimas n entradas, filtro por
    texto y por tipo de evento. Lee SOLO la cola del archivo (audit_tail) y en
    el pool — abrir la tarjeta no toca el event loop ni el hot path."""
    if not _guard(request):
        return HTMLResponse("<h1>403</h1>", status_code=403)
    recs = await asyncio.get_running_loop().run_in_executor(
        None, _audit_filtrado, q, evento, n)
    filas = []
    for r in recs:
        extra = {k: v for k, v in r.items() if k not in _AUD_COLS and k != "token"}
        filas.append({**{c: r.get(c) for c in _AUD_COLS},
                      "extra": " · ".join(f"{k}={v}" for k, v in list(extra.items())[:6])[:240]})
    return request.app.state.templates.TemplateResponse(
        request, "partials/admin_auditoria.html",
        {"filas": filas, "q": q, "evento": evento, "n": n})


@router.get("/auditoria.csv")
async def admin_auditoria_csv(request: Request, q: str = "", evento: str = "",
                              n: int = 2000):
    """Mismo filtro del visor, en CSV (separador ';' + BOM → Excel es-AR lo
    abre directo). Para compliance/backup puntual."""
    from fastapi.responses import Response as _Resp
    if not _guard(request):
        return _Resp("403", status_code=403)

    def _csv() -> str:
        import csv
        import io
        import json as _json
        recs = _audit_filtrado(q, evento, n)
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(list(_AUD_COLS) + ["extra"])
        for r in recs:
            extra = {k: v for k, v in r.items() if k not in _AUD_COLS}
            w.writerow([r.get(c, "") for c in _AUD_COLS]
                       + [_json.dumps(extra, ensure_ascii=False, default=str) if extra else ""])
        return buf.getvalue()

    text = await asyncio.get_running_loop().run_in_executor(None, _csv)
    from datetime import date as _date
    return _Resp("\ufeff" + text,   # BOM: Excel es-AR detecta UTF-8 media_type="text/csv; charset=utf-8",
                 headers={"Content-Disposition":
                          f'attachment; filename="oms_audit_{_date.today():%Y%m%d}.csv"'})
