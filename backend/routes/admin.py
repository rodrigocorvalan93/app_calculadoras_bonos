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
