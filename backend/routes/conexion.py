"""Conexión — landing para elegir broker (endpoint XOMS) y reconectar en caliente.

El mismo feed de BYMA lo intermedian varios brokers (Latin Securities, LBO,
Cocos…): esta página deja elegir el host, poner usuario/clave (default: los de
secrets.txt) y reconectar el WS SIN reiniciar uvicorn. MAE no se toca acá: es
un token directo con MAE (sin brokers en el medio), vive en secrets.txt.

Abierta a TODOS los usuarios logueados (el feed es global: si el broker default
se cae y el superuser no está, cualquiera tiene que poder levantarlo), pero con
dos niveles:
- superuser: URL libre + usuario/clave propios (como siempre);
- resto: usuario/clave propios (vacíos = los de la casa) pero SOLO contra los
  brokers conocidos. La URL libre queda vedada porque el login MANDA la clave
  (la tipeada o la de secrets.txt) al host que se ponga — con URL arbitraria
  cualquier usuario podría cosechar la de la casa apuntándola a un server
  propio.

Seguridad: la clave NUNCA se imprime en el HTML — si el campo viene vacío se
usa la de secrets.txt.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from backend.config import settings
from backend.services import primary_ws

router = APIRouter(tags=["conexion"])

# Hosts conocidos del feed XOMS (el primero es el default de la casa).
KNOWN_HOSTS = [
    ("Latin Securities", "https://api.latinsecurities.matrizoms.com.ar/"),
    ("LBO", "https://api.lbo.xoms.com.ar/"),
    ("Cocos", "https://api.cocos.xoms.com.ar/"),
]


def _render(request: Request, template: str, **ctx) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(request, template, ctx)


def _es_su(request: Request) -> bool:
    return bool(getattr(request.state, "is_superuser", False))


def _norm_url(u: str) -> str:
    return (u or "").strip().rstrip("/").lower()


def _hosts_permitidos() -> set[str]:
    """URLs a las que un no-superuser puede reconectar: los brokers conocidos
    más el endpoint actual (por si la casa está en un host fuera de la lista)."""
    urls = {u for _, u in KNOWN_HOSTS}
    if settings.primary_base_url:
        urls.add(settings.primary_base_url)
    return {_norm_url(u) for u in urls}


def _status_ctx(result: str | None = None, ok: bool | None = None) -> Dict[str, Any]:
    ws = primary_ws.get_ws_client()
    mae_on = False
    try:
        from backend.services import mae as mae_svc
        mae_on = bool(mae_svc.enabled())
    except Exception:  # noqa: BLE001
        pass
    stats = {}
    try:
        stats = ws.stats() or {}
    except Exception:  # noqa: BLE001
        pass
    health = {}
    try:
        from backend.services import feed_health
        health = feed_health.snapshot()
    except Exception:  # noqa: BLE001
        pass
    return {
        "result": result, "ok": ok,
        "authenticated": getattr(ws, "authenticated", False),
        "base_url": getattr(ws, "base_url", settings.primary_base_url),
        "stats": stats, "mae_on": mae_on, "health": health,
    }


@router.get("/conexion", response_class=HTMLResponse)
async def conexion_page(request: Request) -> HTMLResponse:
    es_su = _es_su(request)
    return _render(
        request, "conexion.html",
        hosts=KNOWN_HOSTS,
        es_su=es_su,
        current_url=settings.primary_base_url,
        # el usuario del feed sólo se muestra (prefill) al superuser
        current_user=settings.primary_user if es_su else "",
        has_secret_pass=bool(settings.primary_pass),
        **_status_ctx(),
    )


@router.post("/conexion/login", response_class=HTMLResponse)
async def conexion_login(
    request: Request,
    url: str = Form(""),
    username: str = Form(""),
    password: str = Form(""),
) -> HTMLResponse:
    url = (url or "").strip() or settings.primary_base_url
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    if not _es_su(request):
        # No-superuser: usuario/clave propios OK, pero SOLO contra brokers
        # conocidos. Validar la URL acá es lo que impide que un usuario
        # cualquiera mande la clave (la suya o la de secrets.txt) a un host
        # arbitrario para cosecharla.
        if _norm_url(url) not in _hosts_permitidos():
            return _render(request, "partials/conexion_status.html",
                           **_status_ctx("Ese endpoint no está en la lista de brokers "
                                         "conocidos — elegí uno del selector.", False))
    user = (username or "").strip() or settings.primary_user
    pwd = password or settings.primary_pass          # vacío → la de secrets.txt
    if not user or not pwd:
        return _render(request, "partials/conexion_status.html",
                       **_status_ctx("Faltan usuario o clave (y secrets.txt no los tiene).", False))

    # Reconexión en caliente: parar el WS actual, apuntar al host nuevo,
    # loguear y re-suscribir el universo completo.
    old = primary_ws.get_ws_client()
    try:
        await old.stop()
    except Exception:  # noqa: BLE001
        pass
    ws = primary_ws.reset_ws_client(url)
    try:
        ok = await ws.login(user, pwd)
    except Exception as exc:  # noqa: BLE001 — DNS caído, timeout, SSL…
        return _render(request, "partials/conexion_status.html",
                       **_status_ctx(f"No pude conectar con {url}: {exc}", False))
    if not ok:
        return _render(request, "partials/conexion_status.html",
                       **_status_ctx("El broker rechazó usuario/clave (login fallido). "
                                     "Probá el otro host o revisá las credenciales.", False))

    # Login OK → persistir en memoria (healthz / reconexiones) y arrancar el WS.
    settings.primary_base_url = url
    settings.primary_user = user
    settings.primary_pass = pwd
    try:
        from backend.main import _initial_symbols     # import diferido (sin ciclo)
        # _initial_symbols lee Excel/CSV del universo (decenas de ms, GIL-bound)
        # → threadpool para no frenar el event loop con el WS ya vivo.
        import asyncio
        seed = await asyncio.get_running_loop().run_in_executor(None, _initial_symbols)
        await ws.start(symbols=seed)
        msg = f"Conectado a {url} — {len(seed)} símbolos suscriptos."
    except Exception as exc:  # noqa: BLE001
        msg = f"Login OK pero el WS no arrancó: {exc}"
        return _render(request, "partials/conexion_status.html", **_status_ctx(msg, False))
    return _render(request, "partials/conexion_status.html", **_status_ctx(msg, True))
