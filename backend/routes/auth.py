"""Rutas de auth — login / logout / recuperación de contraseña.

Todas públicas (el middleware las deja pasar sin sesión). Las páginas usan
templates standalone (sin nav). La cookie de sesión la firma SessionMiddleware;
acá sólo escribimos/borramos `request.session['user']`.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from backend.services import auth, mailer

router = APIRouter(tags=["auth"])


def _render(request: Request, template: str, status: int = 200, **ctx) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, template, ctx, status_code=status)


def _safe_next(nxt: Optional[str]) -> str:
    """Sólo redirigimos a paths internos ('/...') para evitar open-redirect."""
    if nxt and nxt.startswith("/") and not nxt.startswith("//"):
        return nxt
    return "/yas"


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/yas") -> HTMLResponse:
    if request.session.get("user") and auth.role_of(request.session["user"]):
        return RedirectResponse(url=_safe_next(next), status_code=303)
    return _render(request, "login.html", next=_safe_next(next), error=None,
                   no_superuser=not auth.has_any_superuser())


@router.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request, username: str = Form(...),
                       password: str = Form(...), next: str = Form("/yas")) -> HTMLResponse:
    if auth.verify_password(username, password):
        request.session["user"] = username.strip().lower()
        return RedirectResponse(url=_safe_next(next), status_code=303)
    return _render(request, "login.html", status=401, next=_safe_next(next),
                   error="Usuario o contraseña incorrectos.",
                   no_superuser=not auth.has_any_superuser())


@router.get("/logout")
async def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@router.get("/forgot", response_class=HTMLResponse)
async def forgot_page(request: Request) -> HTMLResponse:
    return _render(request, "forgot.html", sent=False, error=None,
                   smtp_ok=mailer.is_configured())


@router.post("/forgot", response_class=HTMLResponse)
async def forgot_submit(request: Request, identifier: str = Form(...)) -> HTMLResponse:
    """Acepta usuario o email. No revela si existe (respuesta uniforme). Si hay
    match y SMTP configurado, manda el link de reset en un threadpool."""
    ident = (identifier or "").strip()
    username = ident.lower()
    if not auth.get_user(username):
        username = auth.find_user_by_email(ident) or ""
    if username:
        token = auth.make_reset_token(username, ttl_seconds=3600)
        base = _base_url(request)
        link = f"{base}/reset?token={token}"
        user = auth.get_user(username)
        to = (user or {}).get("email") or ""
        body = ("Recibimos un pedido para restablecer tu contraseña de la Calculadora "
                f"de Bonos.\n\nEntrá a este link (vence en 1 hora):\n{link}\n\n"
                "Si no fuiste vos, ignorá este mail.")
        if to and mailer.is_configured():
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, mailer.send, to, "Restablecer contraseña · Calculadora de Bonos", body)
    # respuesta uniforme (no filtra existencia de usuarios)
    return _render(request, "forgot.html", sent=True, error=None, smtp_ok=mailer.is_configured())


@router.get("/reset", response_class=HTMLResponse)
async def reset_page(request: Request, token: str = "") -> HTMLResponse:
    user = auth.check_reset_token(token)
    if not user:
        return _render(request, "reset.html", token="", valid=False, error=None, done=False)
    return _render(request, "reset.html", token=token, valid=True, error=None, done=False, username=user)


@router.post("/reset", response_class=HTMLResponse)
async def reset_submit(request: Request, token: str = Form(...),
                       password: str = Form(...), password2: str = Form("")) -> HTMLResponse:
    user = auth.check_reset_token(token)
    if not user:
        return _render(request, "reset.html", token="", valid=False, error=None, done=False)
    if password != password2:
        return _render(request, "reset.html", token=token, valid=True, done=False,
                       username=user, error="Las contraseñas no coinciden.")
    try:
        auth.set_password(user, password)
    except auth.AuthError as exc:
        return _render(request, "reset.html", token=token, valid=True, done=False,
                       username=user, error=str(exc))
    return _render(request, "reset.html", token="", valid=False, done=True, error=None)


def _base_url(request: Request) -> str:
    from backend.config import settings
    if settings.app_base_url:
        return settings.app_base_url.rstrip("/")
    return str(request.base_url).rstrip("/")
