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

import gc
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from backend.config import settings
from backend.locale_ar import JINJA_FILTERS
from backend.routes.breakeven import router as breakeven_router
from backend.routes.cafci import router as cafci_router
from backend.routes.comparador import router as comparador_router
from backend.routes.conexion import router as conexion_router
from backend.routes.credito import router as creditos_router
from backend.routes.curves import forwards_router, graficos_router, mercado_router, router as curves_router
from backend.routes.dolares import router as dolares_router
from backend.routes.futuros import router as futuros_router
from backend.routes.mae import router as tasas_router
from backend.routes.ordenes import router as ordenes_router
from backend.routes.total_return import router as total_return_router
from backend.routes.escenario import router as escenario_router
from backend.routes.historico import router as historico_router
from backend.routes.market import router as market_router
from backend.routes.posiciones import router as posiciones_router
from backend.routes.tape import router as tape_router
from backend.routes.yas import router as yas_router
from backend.services import bond_universe, curves as curves_svc, fx as fx_svc, symbols as syms
from backend.services.primary_ws import get_ws_client
from backend.services.warmup import get_daemon as get_warmup_daemon

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
)
logger = logging.getLogger("backend.main")


class _QuietPolls(logging.Filter):
    """Silencia el access-log de los endpoints de polling (1 req/s): /market/seq
    y los partials live. Costo-0: menos I/O de log y consola legible; los
    endpoints 'reales' se siguen logueando igual."""
    _NOISY = ("/market/seq", "/tape", "/dolares/rail", "/news/marquee")

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(p in msg for p in self._NOISY)


logging.getLogger("uvicorn.access").addFilter(_QuietPolls())

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
    # Todas las curvas — soberanas Y corporativas (corp_tamar/badlar/tasafija/
    # uva/dlk/hdmep/hdcable). Antes sólo se sembraban las soberanas, así que los
    # corporativos (p. ej. RVS1O, TAMAR corp) no levantaban precio ni libro.
    for codes in codes_by_curve.values():
        for code in codes or []:
            seed.update(syms.md_symbols([code], plazo="24hs"))
            seed.update(syms.md_symbols([code], plazo="CI"))
    # Implicit-FX legs: the C (cable) and D (MEP) tickers of the liquid
    # sovereigns, needed to derive the CCL / USB reference rates.
    try:
        for pl in ("24hs", "CI"):
            seed.update(fx_svc.fx_leg_symbols(pl))
    except Exception:  # noqa: BLE001
        logger.exception("[main] fx leg seed failed")
    # Spot mayorista ROFEX (símbolo crudo): da el dólar oficial intradía para
    # la pestaña Dólares / el riel. Si el broker no lo sirve, degrada al A3500.
    from backend.services.dolares import SPOT_SYMBOL
    seed.add(SPOT_SYMBOL)
    # Cauciones BYMA (pesos y dólares): MERV - XMEV - PESOS/DOLAR - {n}D, para
    # la pestaña Tasas. Se leen del store igual que los bonos.
    try:
        from backend.services import cauciones as cauc_svc
        seed.update(cauc_svc.symbols("PESOS"))
        seed.update(cauc_svc.symbols("DOLAR"))
    except Exception:  # noqa: BLE001
        logger.exception("[main] caución seed failed")
    # Tickers de las carteras (Posiciones): lo que el fondo TIENE siempre se
    # suscribe — así las acciones fuera del panel curado también levantan Last.
    try:
        from backend.services import positions
        for code in positions.especies_universe():
            seed.add(syms.md_symbol(code, "24hs"))
            seed.add(syms.md_symbol(code, "CI"))
    except Exception:  # noqa: BLE001
        logger.exception("[main] positions seed failed")
    # Acciones + CEDEARs (panel Mercado y barra superior): precio puro, sin TIR.
    try:
        from backend.services import equities
        seed.update(equities.all_symbols())
    except Exception:  # noqa: BLE001
        logger.exception("[main] equities seed failed")
    # Futuros de dólar (DLR/MMMYY + …M): tasas implícitas en la pestaña Futuros.
    try:
        from backend.services import futuros as fut_svc
        seed.update(fut_svc.all_symbols())
    except Exception:  # noqa: BLE001
        logger.exception("[main] futuros seed failed")
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

    # Delta - Especies.xlsx: metadata extra de bonos (lectura única, cache).
    try:
        from backend.services import delta_especies
        de = delta_especies.ensure_loaded()
        logger.info("[main] delta_especies: loaded=%s n=%s", de["loaded"], len(de["by_code"]))
    except Exception:  # noqa: BLE001
        logger.exception("[main] delta_especies load failed")

    # Históricos macro (BCRA): lectura única del json (en el repo).
    try:
        from backend.services import historico
        h = historico.ensure_loaded()
        logger.info("[main] historico: loaded=%s series=%s", h["loaded"], len(h["series"]))
    except Exception:  # noqa: BLE001
        logger.exception("[main] historico load failed")

    # CAFCI: vector de precios (~6k filas; read ~1 s + posible descubrimiento de
    # carpeta). Lo calentamos en un thread aparte para NO demorar el arranque;
    # cuando el usuario abra la pestaña ya está cacheado (abre instantáneo). El
    # lock interno evita doble-carga si llega un request mientras calienta.
    try:
        import threading
        from backend.services import cafci
        threading.Thread(target=cafci.ensure_loaded, name="cafci-warm", daemon=True).start()
    except Exception:  # noqa: BLE001
        logger.exception("[main] cafci warm failed to start")

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

    # Poller SIOPEL (MAE): mantiene caliente el snapshot del dólar oficial en
    # background, sólo si hay MAE_API_KEY. Sin key, la pestaña Dólares usa el
    # A3500 de la serie macro (en memoria); el path de request nunca hace I/O.
    from backend.services import dolares as dolares_svc
    try:
        await dolares_svc.get_poller().start()
    except Exception:  # noqa: BLE001
        logger.exception("[main] SIOPEL poller start failed")

    # Poller MAE Market Data (renta fija / cauciones / repo): snapshot OTC en
    # background, sólo si hay MAE_API_KEY. Alimenta la pestaña Tasas y el
    # cross-venue de Mercado; el path de request sólo lee cache.
    from backend.services import mae as mae_svc
    try:
        await mae_svc.get_poller().start()
    except Exception:  # noqa: BLE001
        logger.exception("[main] MAE poller start failed")

    # Noticias (RSS): poller en thread daemon — el request sólo lee cache.
    try:
        from backend.services import news
        news.start()
    except Exception:  # noqa: BLE001
        logger.exception("[main] news poller start failed")

    # GC freeze (truco Instagram): todo el estado de larga vida (universo de
    # bonos, templates, singletons) ya está alocado. Lo movemos a la generación
    # "permanente" que el GC NO re-escanea, así las colecciones gen-2 disparadas
    # por la basura por-request (miles de dicts al armar una tabla ancha) dejan
    # de pausar ~100 ms. GC sigue activo para los ciclos por-request. El cache de
    # métricas todavía está vacío acá (el warmup corre después del yield), así
    # que no congelamos entradas con TTL. Medido: p99 de Mercado 98 → 26 ms.
    try:
        gc.collect()
        gc.freeze()
    except Exception:  # noqa: BLE001
        logger.exception("[main] gc.freeze failed")

    yield

    logger.info("[main] shutting down")
    try:
        await dolares_svc.get_poller().stop()
    except Exception:  # noqa: BLE001
        logger.exception("[main] SIOPEL poller stop failed")
    try:
        await mae_svc.get_poller().stop()
    except Exception:  # noqa: BLE001
        logger.exception("[main] MAE poller stop failed")
    if warmup is not None:
        try:
            await warmup.stop()
        except Exception:  # noqa: BLE001
            logger.exception("[main] warmup stop failed")
    try:
        await ws.stop()
    except Exception:  # noqa: BLE001
        logger.exception("[main] primary WS stop failed")


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
    app.include_router(conexion_router)
    app.include_router(creditos_router)
    app.include_router(cafci_router)
    app.include_router(breakeven_router)
    app.include_router(curves_router)
    app.include_router(mercado_router)
    app.include_router(forwards_router)
    app.include_router(graficos_router)
    app.include_router(dolares_router)
    app.include_router(futuros_router)
    app.include_router(tasas_router)
    app.include_router(ordenes_router)
    app.include_router(total_return_router)
    app.include_router(escenario_router)
    app.include_router(historico_router)
    app.include_router(posiciones_router)
    app.include_router(market_router)
    app.include_router(tape_router)

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
