"""FastAPI entry point.

Run with:
    uvicorn backend.main:app --reload

Lifespan:
- imports `especies` (which lazily fires `indices.main()` on first attribute
  access from `rentafija.inputs`)
- optionally logs into the broker if PRIMARY_USER / PRIMARY_PASS are set
- closes the httpx client on shutdown
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from backend.config import settings
from backend.locale_ar import JINJA_FILTERS
from backend.routes.comparador import router as comparador_router
from backend.routes.curves import mercado_router, router as curves_router
from backend.routes.market import router as market_router
from backend.routes.posiciones import router as posiciones_router
from backend.routes.yas import router as yas_router
from backend.services import bond_universe, curves as curves_svc, fx as fx_svc, symbols as syms
from backend.services.primary_client import get_client
from backend.services.primary_ws import get_ws_client
from backend.services.warmup import get_daemon as get_warmup_daemon

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
)
logger = logging.getLogger("backend.main")

BACKEND_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BACKEND_DIR / "templates"
STATIC_DIR = BACKEND_DIR / "static"


def _initial_symbols() -> list[str]:
    """Curves we want subscribed on the WS at boot."""
    try:
        codes_by_curve = curves_svc.build_curve_codes()
    except Exception:  # noqa: BLE001
        return []
    seed: set[str] = set()
    for key in (
        "lecap", "cer", "tamar", "cerproy",
        "dolarlinked", "globales", "bonares", "bopreales",
        "dualfija", "dualtamar", "dualcer",
    ):
        for code in codes_by_curve.get(key, []) or []:
            seed.update(syms.md_symbols([code], plazo="24hs"))
            seed.update(syms.md_symbols([code], plazo="CI"))
    # Implicit-FX legs: the C (cable) and D (MEP) tickers of the liquid
    # sovereigns, needed to derive the CCL / USB reference rates.
    try:
        for pl in ("24hs", "CI"):
            seed.update(fx_svc.fx_leg_symbols(pl))
    except Exception:  # noqa: BLE001
        logger.exception("[main] fx leg seed failed")
    return sorted(seed)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("[main] starting up")
    try:
        bond_universe.ensure_loaded()
    except Exception:  # noqa: BLE001
        logger.exception("[main] bond universe load failed (calculator will return errors)")

    # Posiciones Delta: lectura ÚNICA de los Excel al arranque (cache en
    # memoria). Failure-silent: si faltan los archivos, la pestaña lo avisa.
    try:
        from backend.services import positions
        st = positions.ensure_loaded()
        logger.info("[main] positions: loaded=%s holdings=%s", st["loaded"], len(st["holdings"]))
    except Exception:  # noqa: BLE001
        logger.exception("[main] positions load failed")

    ws = get_ws_client()
    if settings.primary_user and settings.primary_pass:
        try:
            ok = await ws.login(settings.primary_user, settings.primary_pass)
        except Exception:  # noqa: BLE001
            logger.exception("[main] broker login raised; continuing without live data")
            ok = False
        if ok:
            seed = _initial_symbols()
            await ws.start(symbols=seed)
            logger.info("[main] primary WS started, %d symbols subscribed", len(seed))
        else:
            logger.warning("[main] broker login returned False; WS not started")
    else:
        logger.info("[main] PRIMARY_USER/PRIMARY_PASS not set; skipping broker login")

    # Warmup daemon: primes the calc engine (kills the cold lazy-load) and
    # keeps the curve metrics cache hot. Runs regardless of the broker —
    # the prime step benefits YAS even with no live data.
    warmup = None
    if settings.warmup_enabled:
        warmup = get_warmup_daemon()
        await warmup.start()

    yield

    logger.info("[main] shutting down")
    if warmup is not None:
        try:
            await warmup.stop()
        except Exception:  # noqa: BLE001
            logger.exception("[main] warmup stop failed")
    try:
        await ws.stop()
    except Exception:  # noqa: BLE001
        logger.exception("[main] primary WS stop failed")
    try:
        await get_client().close()
    except Exception:  # noqa: BLE001
        logger.exception("[main] primary client close failed")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Calculadora de Bonos — FastAPI rewrite",
        lifespan=lifespan,
    )

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    for name, fn in JINJA_FILTERS.items():
        templates.env.filters[name] = fn
    # Cache-busting de estáticos: versión = mtime del CSS, así el browser
    # re-baja style.css/app.js cuando cambian (evita ver estilos viejos).
    try:
        _asset_v = int((STATIC_DIR / "css" / "style.css").stat().st_mtime)
    except OSError:
        _asset_v = 1
    templates.env.globals["asset_v"] = _asset_v
    app.state.templates = templates

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(yas_router)
    app.include_router(comparador_router)
    app.include_router(curves_router)
    app.include_router(mercado_router)
    app.include_router(posiciones_router)
    app.include_router(market_router)

    @app.get("/")
    async def index() -> RedirectResponse:
        return RedirectResponse(url="/yas", status_code=302)

    @app.get("/healthz")
    async def healthz(request: Request) -> dict:
        ws = get_ws_client()
        return {
            "status": "ok",
            "bonds_loaded": len(bond_universe.all_codes()),
            "broker_authenticated": ws.authenticated,
            "ws": ws.stats(),
            "warmup": get_warmup_daemon().stats(),
        }

    return app


app = create_app()
