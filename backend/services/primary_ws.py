"""Async WebSocket client for Primary / matrizoms.

One singleton lives in the FastAPI process. Workflow:

  1. login via REST (`PrimaryWS.login` → cookies on the httpx
     AsyncClient; el mismo cliente cursa luego el REST autenticado del OMS).
  2. open a WS to `wss://<host>/` using those cookies as a `Cookie:`
     header on the handshake.
  3. send the `smd` subscribe payload Primary expects.
  4. loop on incoming `Md` messages, decode them and merge each one
     into `MarketDataStore`.
  5. ping every `KEEPALIVE_SECS` so the server doesn't drop us.
  6. reconnect with exponential backoff (2/4/8/16/30s max) on any
     network error and resubscribe.

Designed to fail silently if `PRIMARY_USER`/`PRIMARY_PASS` aren't set or
the broker is unreachable — the rest of the app still works without
live market data.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import logging
import ssl
import time
from typing import Any, Dict, Iterable, List, Optional, Set

import httpx
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from .marketdata_store import MarketDataStore, get_store

logger = logging.getLogger("backend.primary_ws")


KEEPALIVE_SECS = 25
BACKOFF_INITIAL = 2.0
BACKOFF_MAX = 30.0

# matrizoms ignora un 'smd' con demasiados productos (probado: 1 símbolo ->
# llega book; ~238 de una -> 0 mensajes). Suscribimos en lotes de este tamaño;
# las suscripciones se ACUMULAN entre mensajes 'smd' sucesivos sobre la misma
# conexión, así que varios lotes chicos == un universo grande suscripto.
SUBSCRIBE_CHUNK = 20

# Entries Primary will accept. Confirmed: WA / TC are rejected and make
# the whole query return empty. Same list the legacy app uses, MÁS "IV"
# (Index Value): es el ÚNICO entry que publican los índices (I.MERVAL) —
# sin pedirlo, el índice quedaba suscripto pero nunca mandaba nada y el
# Merval no aparecía en el tape. Para bonos/acciones IV viene vacío (no-op).
ENTRIES = ["BI", "OF", "LA", "OP", "CL", "HI", "LO", "EV", "TV", "NV", "IV"]

# OI (interés abierto) sólo lo publican los futuros: se pide únicamente en los
# lotes DLR/…. Si matrizoms rechazara el entry, la recuperación de errores
# resuscribe esos símbolos con ENTRIES estándar y el feed sigue (sin OI) en
# vez de perder los futuros enteros.
ENTRIES_FUT = ENTRIES + ["OI"]


def _is_futuro(symbol: str) -> bool:
    """Futuro DLR nativo (excluye el spot, que no tiene interés abierto)."""
    return symbol.startswith("DLR/") and symbol != "DLR/SPOT"


def _ws_header_kwarg() -> str:
    """Nombre del kwarg de headers en `websockets.connect`.

    websockets >= 14 (nuevo cliente asyncio) usa `additional_headers`; las
    versiones previas (cliente legacy) usan `extra_headers`. Detectamos cuál
    acepta la versión instalada para soportar ambas y no atar el backend a una
    versión puntual de la librería.
    """
    try:
        params = inspect.signature(websockets.connect).parameters
        if "additional_headers" in params:
            return "additional_headers"
        if "extra_headers" in params:
            return "extra_headers"
    except (ValueError, TypeError):
        pass
    # Fallback por número de versión si la firma no es introspectable.
    ver = getattr(websockets, "__version__", "") or ""
    try:
        major = int(ver.split(".")[0])
    except (ValueError, IndexError):
        major = 0
    return "additional_headers" if major >= 14 else "extra_headers"


_WS_HEADER_KW = _ws_header_kwarg()


def _ssl_context_for(url: str) -> Optional[ssl.SSLContext]:
    """Contexto TLS con el bundle de certifi para las conexiones wss://.

    Sin esto, `websockets.connect` usa los CA default del intérprete — que en
    el Python de python.org para macOS están VACÍOS (no lee el Keychain del
    sistema): cada conexión moría con CERTIFICATE_VERIFY_FAILED y el feed
    quedaba en un loop conectar/caer, mientras el login REST sí funcionaba
    (httpx trae certifi propio). Usamos el mismo bundle que httpx — certifi es
    dependencia dura de httpx, siempre está. En Windows/Linux es equivalente
    al default, así que no cambia nada donde ya andaba."""
    if not url.startswith("wss://"):
        return None
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001 — sin certifi, el default de siempre
        return None


def _ws_url_from_base(base_url: str) -> str:
    if base_url.startswith("https://"):
        return "wss://" + base_url[len("https://"):]
    if base_url.startswith("http://"):
        return "ws://" + base_url[len("http://"):]
    return base_url


def _cookie_header(cookies: httpx.Cookies) -> str:
    parts = []
    for cookie in cookies.jar:
        parts.append(f"{cookie.name}={cookie.value}")
    return "; ".join(parts)


def _subscribe_payload(symbols: Iterable[str], depth: int = 5,
                       entries: Optional[List[str]] = None) -> str:
    return json.dumps({
        "type": "smd",
        "level": 1,
        "entries": list(entries) if entries else ENTRIES,
        "products": [{"symbol": s, "marketId": "ROFX"} for s in sorted(symbols)],
        "depth": depth,
    })


class PrimaryWS:
    """One-process singleton WS client to Primary."""

    def __init__(
        self,
        base_url: str,
        store: Optional[MarketDataStore] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.ws_url = _ws_url_from_base(self.base_url)
        self.store = store or get_store()
        self._subscriptions: Set[str] = set()
        self._sub_lock = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None
        self._stop_evt = asyncio.Event()
        self._ws: Optional[websockets.ClientConnection] = None
        self._http: Optional[httpx.AsyncClient] = None
        self._cookies: Optional[httpx.Cookies] = None
        # Credenciales guardadas para re-login en reconexión (cookie vencida).
        self._username = ""
        self._password = ""
        self._connected = False
        self._stats: Dict[str, Any] = {
            "connected": False,
            "messages": 0,
            "reconnects": 0,
            "last_message_at": 0.0,
            "last_error": None,
            "subscriptions": 0,
            # Visibilidad de respuestas que NO son MarketData (Md): el server
            # puede contestar al 'smd' con un error / confirmación de otro type
            # (ej. símbolo inválido, demasiados productos). Antes los tirábamos
            # en silencio y quedábamos "connected con 0 mensajes".
            "non_md_messages": 0,
            "last_non_md": None,
        }
        # Símbolos rechazados por el broker (no reintentar) y los que ya
        # reintentamos de a uno (evita loops de re-subscripción).
        self._rejected: Set[str] = set()
        self._retried_individually: Set[str] = set()
        # Futuros que ya reintentamos sin el entry OI (un rechazo con OI puede
        # ser por el entry, no por el símbolo — no descartar sin probar).
        self._retried_no_oi: Set[str] = set()

    # ── API ─────────────────────────────────────────────────────────

    async def login(self, username: str, password: str) -> bool:
        """REST login. Cookies are kept in `self._cookies` for the WS handshake."""
        if not username or not password:
            logger.info("[primary_ws] no credentials provided, skipping login")
            return False
        self._username, self._password = username, password   # para re-login en reconexión
        # follow_redirects=True: el login OK de Spring Security responde 302
        # -> /marketdata.html. requests (legacy) seguía el redirect por
        # defecto; httpx no. Sin esto, raise_for_status() trata el 302 como
        # error y descartamos las cookies de sesión válidas.
        #
        # Cerramos un cliente previo antes de reemplazarlo (re-login): si no, cada
        # re-login filtra un AsyncClient con su pool de conexiones abierto.
        if self._http is not None:
            try:
                await self._http.aclose()
            except Exception:  # noqa: BLE001
                pass
        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(10.0, connect=5.0),
            follow_redirects=True,
        )
        try:
            r = await self._http.post(
                "j_spring_security_check",
                data={"j_username": username, "j_password": password},
            )
            r.raise_for_status()
            # Spring Security responde 200 TAMBIÉN cuando el login FALLA: redirige
            # a /login?error, que raise_for_status ve como 200 OK. Sin validar el
            # destino, credenciales malas devolvían True y el WS reintentaba para
            # siempre con una sesión anónima. Si la URL final es la de login/error,
            # el login no prosperó.
            final = str(r.url).lower()
            if any(k in final for k in ("login", "error", "authentication")):
                self._stats["last_error"] = "login: credenciales rechazadas (redirect a login)"
                self._cookies = None
                logger.warning("[primary_ws] login RECHAZADO (redirect a %s)", r.url)
                return False
            self._cookies = self._http.cookies
            logger.info("[primary_ws] login OK (%d cookies)", len(list(self._cookies.jar)))
            return True
        except httpx.HTTPError as exc:
            self._stats["last_error"] = f"login: {exc}"
            logger.warning("[primary_ws] login failed: %s", exc)
            return False

    async def get_json(self, path: str, params: Optional[Dict[str, Any]] = None) -> Optional[Any]:
        """GET REST autenticado (usa el httpx client con las cookies del login).
        Para endpoints estáticos como rest/instruments/detail. None si falla."""
        if self._http is None:
            return None
        try:
            r = await self._http.get(path, params=params or {})
            r.raise_for_status()
            return r.json()
        except Exception:  # noqa: BLE001
            return None

    async def get_json_checked(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """GET REST autenticado que PROPAGA el error con texto accionable (sin
        sesión, sesión vencida → redirect a login.html, endpoint inexistente…).

        Lo usa el OMS: las órdenes deben cursar por ESTE cliente (el que el
        login deja con cookies de sesión), no por uno sin autenticar. A
        diferencia de `get_json` (None-on-fail, para lecturas best-effort como
        instruments/detail), acá el error sube para que el blotter muestre el
        motivo crudo del broker."""
        if self._http is None:
            raise RuntimeError(f"{path} → sin sesión del broker (sin login). Conectá en /conexion.")
        r = await self._http.get(path, params=params or {})
        if r.status_code != 200:
            raise RuntimeError(f"{path} → HTTP {r.status_code}: {r.text[:200]}")
        if not r.text.strip():
            raise RuntimeError(f"{path} → respuesta vacía (¿sesión vencida? Reconectá en /conexion).")
        try:
            return r.json()
        except ValueError as e:
            raise RuntimeError(f"{path} → no devolvió JSON: {r.text[:200]}") from e

    async def start(self, symbols: Iterable[str] = ()) -> None:
        """Spawn the reader loop. Idempotent."""
        if self._task and not self._task.done():
            return
        self._subscriptions.update(symbols)
        self._stop_evt.clear()
        self._task = asyncio.create_task(self._run_loop(), name="primary_ws")
        logger.info("[primary_ws] reader task started")

    async def stop(self) -> None:
        self._stop_evt.set()
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:  # noqa: BLE001
                pass
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
        if self._http is not None:
            await self._http.aclose()
            self._http = None
        logger.info("[primary_ws] stopped")

    async def subscribe(self, symbols: Iterable[str]) -> None:
        """Add symbols to the active subscription. Resubscribes the full set."""
        new = set(symbols) - self._subscriptions
        if not new:
            return
        async with self._sub_lock:
            self._subscriptions.update(new)
            self._stats["subscriptions"] = len(self._subscriptions)
            if self._ws is not None and self._connected:
                try:
                    # Solo los nuevos (las suscripciones se acumulan), en lotes.
                    await self._send_in_chunks(self._ws, new)
                    logger.info(
                        "[primary_ws] subscribed %d new (total %d)",
                        len(new), len(self._subscriptions),
                    )
                except (ConnectionClosed, WebSocketException) as exc:
                    logger.warning("[primary_ws] resubscribe failed: %s", exc)

    async def _send_in_chunks(self, ws, symbols: Iterable[str]) -> None:
        """Envía la suscripción 'smd' en lotes de SUBSCRIBE_CHUNK.

        matrizoms ignora un subscribe con demasiados productos; mandar de a
        pocos (acumulan entre mensajes) sí funciona. Un pequeño sleep entre
        lotes evita saturar el socket. Los futuros DLR van en lotes propios
        con el entry OI extra (interés abierto).
        """
        syms = sorted(s for s in symbols if s not in self._rejected)
        futs = [s for s in syms if _is_futuro(s)]
        rest = [s for s in syms if not _is_futuro(s)]
        n_lotes = 0
        for group, entries in ((rest, None), (futs, ENTRIES_FUT)):
            for i in range(0, len(group), SUBSCRIBE_CHUNK):
                await ws.send(_subscribe_payload(group[i:i + SUBSCRIBE_CHUNK], entries=entries))
                n_lotes += 1
                await asyncio.sleep(0.05)
        if syms:
            logger.info("[primary_ws] subscribe en %d lotes de <=%d (%d símbolos, %d futuros)",
                        n_lotes, SUBSCRIBE_CHUNK, len(syms), len(futs))

    @staticmethod
    def _payload_from_error(message: Any) -> Dict[str, Any]:
        """Payload 'smd' que el server eco-devuelve dentro de la respuesta
        ERROR (campo 'message', es JSON string)."""
        if not isinstance(message, str):
            return {}
        try:
            payload = json.loads(message)
        except (ValueError, TypeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _symbols_from_error(message: Any) -> List[str]:
        """Extrae los símbolos del payload 'smd' eco-devuelto en el ERROR."""
        out: List[str] = []
        for p in PrimaryWS._payload_from_error(message).get("products", []) or []:
            sym = p.get("symbol") if isinstance(p, dict) else None
            if sym:
                out.append(sym)
        return out

    def _recover_from_error(self, message: Any) -> None:
        payload = self._payload_from_error(message)
        syms = [p.get("symbol") for p in payload.get("products", []) or []
                if isinstance(p, dict) and p.get("symbol")]
        if not syms:
            return
        entries = [e for e in payload.get("entries", []) or [] if isinstance(e, str)]
        if len(syms) == 1:
            bad = syms[0]
            if "OI" in entries and bad not in self._retried_no_oi:
                # el rechazo puede ser por el ENTRY OI y no por el símbolo:
                # un intento con los entries estándar antes de descartar.
                self._retried_no_oi.add(bad)
                logger.info("[primary_ws] %s rechazado con OI; reintento sin OI", bad)
                self._spawn_resub([bad], None)
                return
            # rechazo de un único símbolo -> es inválido, lo descartamos.
            if bad not in self._rejected:
                self._rejected.add(bad)
                logger.warning("[primary_ws] símbolo inválido descartado: %s", bad)
            return
        # lote rechazado: reintentar de a uno (con los MISMOS entries del lote,
        # así los futuros conservan el OI) los que aún no probamos solos.
        pending = [s for s in syms
                   if s not in self._rejected and s not in self._retried_individually]
        if not pending:
            return
        self._retried_individually.update(pending)
        logger.info("[primary_ws] lote rechazado (%d símbolos); reintentando %d de a uno",
                    len(syms), len(pending))
        self._spawn_resub(pending, entries or None)

    def _spawn_resub(self, symbols: List[str], entries: Optional[List[str]]) -> None:
        try:
            # Guardar la referencia: asyncio sólo tiene weak-refs a las tasks
            # y un fire-and-forget puede ser recolectado por el GC a mitad de
            # la re-suscripción — justo el path de recuperación que cubre.
            t = asyncio.create_task(self._resubscribe_individually(symbols, entries))
            self._resub_task = t
            t.add_done_callback(lambda _t: setattr(self, "_resub_task", None))
        except RuntimeError:
            pass  # sin loop corriendo

    async def _resubscribe_individually(self, symbols: List[str],
                                        entries: Optional[List[str]] = None) -> None:
        ws = self._ws
        if ws is None:
            return
        for s in symbols:
            if s in self._rejected:
                continue
            try:
                await ws.send(_subscribe_payload([s], entries=entries))
                await asyncio.sleep(0.02)
            except (ConnectionClosed, WebSocketException):
                return

    # Sin un Md en este tiempo consideramos el feed "stale" (mercado quieto o
    # conexión muerta). 90 s cubre holgado un mercado ilíquido intradía.
    STALE_AFTER = 90.0

    def stats(self) -> Dict[str, Any]:
        s = dict(self._stats)
        s["subscriptions"] = len(self._subscriptions)
        s["rejected"] = len(self._rejected)
        last = self._stats.get("last_message_at") or 0.0
        s["stale_seconds"] = round(time.time() - last, 1) if last else None
        s["feed_alive"] = self.feed_alive
        return s

    @property
    def authenticated(self) -> bool:
        """Tenemos cookies de sesión para el REST del OMS. NO implica que el feed
        de market data esté vivo — para eso, `feed_alive`."""
        return self._cookies is not None

    @property
    def feed_alive(self) -> bool:
        """El WS está conectado Y llegó un Md hace poco. Es la señal honesta de
        "los precios que ves son de ahora": `/healthz` y el dot del frontend deben
        usar esto, no `authenticated` (que sigue True con la sesión abierta aunque
        el feed lleve horas muerto)."""
        if not self._connected:
            return False
        last = self._stats.get("last_message_at") or 0.0
        return last > 0 and (time.time() - last) < self.STALE_AFTER

    # ── Internals ───────────────────────────────────────────────────

    async def _run_loop(self) -> None:
        backoff = BACKOFF_INITIAL
        while not self._stop_evt.is_set():
            if self._cookies is None:
                # No credentials → nothing to do. Re-check periodically
                # in case `login` was called after start.
                await asyncio.sleep(2.0)
                continue
            connected_at = time.monotonic()
            clean_close = False
            try:
                await self._connect_and_read()
                clean_close = True                  # retorno normal (server cerró)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                self._stats["last_error"] = f"{type(exc).__name__}: {exc}"
                logger.warning("[primary_ws] disconnected: %s", exc)
            self._connected = False
            self._stats["connected"] = False
            if self._stop_evt.is_set():
                break

            # BUG histórico: un retorno normal de _connect_and_read (close limpio
            # del server: 1000/1001, sesión invalidada, LB idle) reseteaba el
            # backoff y daba otra vuelta SIN esperar → loop apretado martillando al
            # broker, y sin contar el reconnect. Ahora el close limpio se trata como
            # cualquier desconexión: backoff + reconnect, igual que un error.
            uptime = time.monotonic() - connected_at
            if clean_close:
                self._stats["last_error"] = "server cerró la conexión (close limpio)"
                logger.info("[primary_ws] server closed cleanly after %.0fs — reconnect", uptime)
            # Una sesión larga y sana que recién ahora cae → el próximo intento
            # arranca rápido (backoff bajo). Una que cae enseguida → fallo
            # persistente: dejamos que el backoff escale.
            if uptime >= 30.0:
                backoff = BACKOFF_INITIAL
            else:
                # Caída rápida con credenciales: la sesión pudo vencer. Re-login
                # para refrescar las cookies; si no, reconectaríamos para siempre
                # con la MISMA cookie vencida y el feed quedaría muerto sin señal.
                if self._username and self._password:
                    try:
                        if await self.login(self._username, self._password):
                            logger.info("[primary_ws] re-login OK tras caída rápida")
                        else:
                            logger.warning("[primary_ws] re-login falló; reintento con cookies actuales")
                    except Exception:  # noqa: BLE001
                        logger.exception("[primary_ws] re-login raised")
            self._stats["reconnects"] += 1
            try:
                await asyncio.wait_for(self._stop_evt.wait(), timeout=backoff)
                break  # stop set during the wait
            except asyncio.TimeoutError:
                pass
            backoff = min(backoff * 2, BACKOFF_MAX)

    async def _connect_and_read(self) -> None:
        cookie_hdr = _cookie_header(self._cookies)
        headers = {"Cookie": cookie_hdr} if cookie_hdr else None
        # El nombre del kwarg de headers cambió entre versiones de websockets
        # (extra_headers < v14, additional_headers >= v14). Usamos el que
        # corresponda a la versión instalada (ver _WS_HEADER_KW).
        connect_kwargs = {
            "ping_interval": KEEPALIVE_SECS,
            "ping_timeout": KEEPALIVE_SECS,
            "max_size": 4 * 1024 * 1024,
            "close_timeout": 2.0,
        }
        if headers:
            connect_kwargs[_WS_HEADER_KW] = headers
        ssl_ctx = _ssl_context_for(self.ws_url)
        if ssl_ctx is not None:
            connect_kwargs["ssl"] = ssl_ctx
        async with websockets.connect(self.ws_url, **connect_kwargs) as ws:
            self._ws = ws
            self._connected = True
            self._stats["connected"] = True
            logger.info("[primary_ws] connected to %s", self.ws_url)

            if self._subscriptions:
                await self._send_in_chunks(ws, self._subscriptions)

            try:
                async for raw in ws:
                    if self._stop_evt.is_set():
                        return
                    self._handle_message(raw)
            finally:
                self._connected = False
                self._stats["connected"] = False
                self._ws = None

    def _handle_message(self, raw: str | bytes) -> None:
        try:
            obj = json.loads(raw)
        except (ValueError, TypeError):
            return
        if not isinstance(obj, dict):
            return
        if obj.get("type") not in ("Md", "md"):
            snippet = raw if isinstance(raw, str) else raw.decode("utf-8", "replace")
            self._stats["non_md_messages"] = self._stats.get("non_md_messages", 0) + 1
            self._stats["last_non_md"] = snippet[:600]
            # matrizoms rechaza el 'smd' ENTERO si un símbolo del lote es
            # inválido. Reintentamos el lote de a uno para conservar los
            # válidos y descartar solo el/los inválido(s).
            if obj.get("status") == "ERROR":
                self._recover_from_error(obj.get("message"))
            else:
                logger.warning("[primary_ws] mensaje no-Md (type=%r): %s",
                               obj.get("type"), snippet[:300])
            return
        symbol = (obj.get("instrumentId") or {}).get("symbol")
        market_data = obj.get("marketData") or {}
        if not symbol or not isinstance(market_data, dict):
            return
        self.store.update_from_md(symbol, market_data)
        self._stats["messages"] += 1
        self._stats["last_message_at"] = time.time()


_singleton: Optional[PrimaryWS] = None


def get_ws_client(base_url: str | None = None) -> PrimaryWS:
    """Process-wide singleton."""
    global _singleton
    if _singleton is None:
        from backend.config import settings  # noqa: WPS433

        _singleton = PrimaryWS(base_url or settings.primary_base_url)
    return _singleton


def reset_ws_client(base_url: str) -> PrimaryWS:
    """Reemplaza el singleton por uno nuevo apuntando a `base_url` (reconexión
    en caliente desde /conexion). El caller debe stop()ear el viejo ANTES."""
    global _singleton
    _singleton = PrimaryWS(base_url)
    return _singleton
