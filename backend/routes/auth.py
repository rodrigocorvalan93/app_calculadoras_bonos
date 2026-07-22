"""Rutas de auth — login / logout / recuperación de contraseña.

Todas públicas (el middleware las deja pasar sin sesión). Las páginas usan
templates standalone (sin nav). La cookie de sesión la firma SessionMiddleware;
acá sólo escribimos/borramos `request.session['user']`.
"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Dict, List, Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from backend.services import auth, mailer

router = APIRouter(tags=["auth"])

# ── Throttle de fuerza bruta ─────────────────────────────────────────────────
# Login corre PBKDF2 (~50 ms) y es público: sin límite, es a la vez un vector de
# fuerza bruta y de DoS (cada intento ocupa un hilo del executor). Contamos los
# fallos por IP en una ventana; superado el tope, respondemos 429 sin siquiera
# hashear. En memoria (deploy single-process); se limpia al primer login exitoso.
_LOGIN_MAX_FAILS = 10
_LOGIN_WINDOW = 300.0                       # 5 min
_login_fails: Dict[str, List[float]] = defaultdict(list)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "?"


def _login_throttled(key: str) -> bool:
    now = time.time()
    fails = [t for t in _login_fails.get(key, ()) if now - t < _LOGIN_WINDOW]
    if fails:
        _login_fails[key] = fails
    else:
        _login_fails.pop(key, None)
    return len(fails) >= _LOGIN_MAX_FAILS


def _render(request: Request, template: str, status: int = 200, **ctx) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, template, ctx, status_code=status)


def _safe_next(nxt: Optional[str]) -> str:
    """Sólo redirigimos a paths internos para evitar open-redirect. Rechaza
    esquemas y URLs scheme-relative: '//host', y también '/\\host' o control
    chars, que los browsers normalizan a '//host' (el '\\' se convierte en '/')."""
    if (nxt and nxt.startswith("/") and not nxt.startswith("//")
            and "\\" not in nxt and not any(c in nxt for c in "\t\r\n")):
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
    ip = _client_ip(request)
    if _login_throttled(ip):
        return _render(request, "login.html", status=429, next=_safe_next(next),
                       error="Demasiados intentos fallidos. Esperá unos minutos y reintentá.",
                       no_superuser=not auth.has_any_superuser())
    # PBKDF2 (~50 ms, GIL-bound) fuera del event loop: en el hilo del handler
    # bloquearía /market/seq y todos los paneles live de los demás usuarios.
    loop = asyncio.get_running_loop()
    ok = await loop.run_in_executor(None, auth.verify_password, username, password)
    if ok:
        _login_fails.pop(ip, None)                 # sesión limpia: reset del contador
        request.session["user"] = username.strip().lower()
        return RedirectResponse(url=_safe_next(next), status_code=303)
    _login_fails[ip].append(time.time())
    if len(_login_fails) > 256:
        # Sweep global: sin esto, cada IP distinta que falla una vez deja su
        # entrada para siempre (la poda por-key de _login_throttled sólo corre
        # si ESA ip vuelve a intentar) → crecimiento sin tope ante scans.
        now = time.time()
        for k in [k for k, ts in _login_fails.items()
                  if not ts or now - ts[-1] >= _LOGIN_WINDOW]:
            _login_fails.pop(k, None)
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
        # PBKDF2 (200k iteraciones, ~50 ms GIL-bound) + fsync del store: al
        # threadpool, igual que el login — en el event loop congelaba los
        # paneles live de todos mientras se re-hasheaba.
        import asyncio
        await asyncio.get_running_loop().run_in_executor(None, auth.set_password, user, password)
    except auth.AuthError as exc:
        return _render(request, "reset.html", token=token, valid=True, done=False,
                       username=user, error=str(exc))
    return _render(request, "reset.html", token="", valid=False, done=True, error=None)


def _base_url(request: Request) -> str:
    from backend.config import settings
    if settings.app_base_url:
        return settings.app_base_url.rstrip("/")
    return str(request.base_url).rstrip("/")
