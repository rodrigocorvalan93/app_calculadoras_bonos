"""Panel de administración (sólo superuser) — CRUD de usuarios y config de las
pestañas visibles por rol.

El acceso a /admin ya lo restringe el middleware al superuser; acá igual se
revalida de forma defensiva. Las mutaciones re-renderizan la página con un
mensaje de resultado (sin htmx: es un panel de baja frecuencia).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from backend.services import auth

router = APIRouter(prefix="/admin", tags=["admin"])


def _guard(request: Request) -> bool:
    u = getattr(request.state, "user", None)
    return bool(u and u.get("role") == "superuser")


def _ctx(request: Request, msg: Optional[str] = None, error: Optional[str] = None) -> HTMLResponse:
    rt = auth.role_tabs()
    tabs = [{"key": k, "label": lbl} for k, lbl, _ in auth.TABS]
    return request.app.state.templates.TemplateResponse(
        request, "admin.html",
        {"users": auth.list_users(), "roles": auth.ROLES, "role_labels": auth.ROLE_LABELS,
         "tabs": tabs, "role_tabs": {r: set(rt.get(r, [])) for r in ("premium", "basico")},
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
        auth.create_user(username, password, role, email)
        return _ctx(request, msg=f"Usuario '{username.strip().lower()}' creado.")
    except auth.AuthError as exc:
        return _ctx(request, error=str(exc))


@router.post("/users/password", response_class=HTMLResponse)
async def reset_password(request: Request, username: str = Form(...), password: str = Form(...)) -> HTMLResponse:
    if not _guard(request):
        return HTMLResponse("<h1>403</h1>", status_code=403)
    try:
        auth.set_password(username, password)
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
