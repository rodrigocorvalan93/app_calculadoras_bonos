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
import os
import re
import ssl
import time
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional, Set
from urllib.parse import urlsplit

import httpx
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from .marketdata_store import MarketDataStore, get_store

logger = logging.getLogger("backend.primary_ws")


KEEPALIVE_SECS = 25
BACKOFF_INITIAL = 2.0
BACKOFF_MAX = 30.0
# Gracia para el handshake / la reconexión: sin socket hace menos de esto, con
# sesión y el lector vivo, es "conectando" (ver PrimaryWS.connecting), no un
# feed caído. Cubre un connect + subscribe normal (1-3 s) y un reconnect con
# backoff corto; un corte real supera esto enseguida.
CONNECT_GRACE_S = 10.0

# Símbolos que el broker rechazó como inválidos, persistidos POR HOST en un
# JSON local (fuera de OneDrive) para no volver a pedirlos en cada arranque:
# matrizoms rechaza el 'smd' ENTERO si un símbolo del lote es inválido, así
# que cada arranque pagaba ~130 lotes rechazados + ~500 reintentos de a uno
# (30-40 s de tormenta de mensajes en los que los válidos del mismo lote
# tampoco tenían feed, y que solía terminar en un keepalive timeout). Con el
# cache, el primer subscribe ya sale sin ellos. Un símbolo puede volver a ser
# válido (nueva emisión que el broker lista días después): cada entrada vence
# a los REJECTED_TTL_DAYS y se vuelve a probar (al arrancar y, con el proceso
# arriba, en reprobar_pendientes). PRIMARY_REJECTED_CACHE = ruta del archivo;
# "0" lo apaga (la suite de tests corre con 0). Los plazos de caución NO entran
# acá: su validez es por día (ver _es_diario).
REJECTED_TTL_DAYS = 7
_REJECTED_SAVE_DELAY = 3.0          # segundos: coalesce de la tormenta en UNA escritura

# Tormenta de rechazos: si el broker rechaza MÁS de la mitad del universo (y
# más de _TORMENTA_MIN símbolos) el problema no son los símbolos sino la sesión
# o los permisos de market data de ESA cuenta — y cachearlos 7 días deja la app
# con "precios viejos" toda la semana (09/10/2026: una cuenta en LBO quedó con
# 2717 de 2903 símbolos en el cache; cada reconexión suscribía 186). Con
# tormenta: se corta la recuperación de a uno, NO se persiste el cache del
# host, /conexion lo avisa y el botón "Reprobar" (olvidar_rechazados) o el
# cambio de día vuelven a probar todo. Un cache que ya viene así se descarta al
# conectar (_cache_es_tormenta).
_TORMENTA_FRAC = 0.5
_TORMENTA_MIN = 300


def _rejected_cache_path() -> Optional[str]:
    v = os.getenv("PRIMARY_REJECTED_CACHE")
    if v is not None:
        v = v.strip()
        if v.lower() in ("", "0", "off", "no"):
            return None
        return os.path.expanduser(v)
    # misma carpeta local por máquina que el journal del histórico
    base = os.getenv("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "bonos", "primary_rechazados.json")


def _leer_json(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}

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


# Plazos de caución ('MERV - XMEV - PESOS - 4D'): la validez es POR DÍA — el 4D
# existe sólo cuando hoy+4 es hábil (lunes, jueves y el viernes previo a un
# feriado del lunes), el 1D nunca un viernes, el 7D no cuando cae en feriado.
# Un rechazo del broker NO dice "símbolo inválido" sino "hoy no hay rueda de
# ese plazo", así que NO se persiste ni se descarta por REJECTED_TTL_DAYS: el
# 09/10/2026 (viernes, lunes feriado) el 4D — el overnight del día, el que
# concentra el volumen — no llegaba porque el rechazo del martes lo había
# dejado en el cache, y la tira de Tasas mostraba 1D–7D "hoy no hay" con sólo
# 14D/21D vivos: exactamente los plazos que no fueron inválidos ningún día de
# esa semana. Van en 'smd' DE A UNO (un rechazo no voltea el lote de los
# demás), con un cooldown de REPROBAR_DIARIO_S entre reintentos, y al cambiar
# el día se piden todos de nuevo (reprobar_pendientes, cada REPROBAR_CHECK_S,
# dentro de _REPROBAR_HORAS BA; fuera de la ventana se prueban al conectar).
_RE_CAUCION = re.compile(r"^MERV - XMEV - (?:PESOS|DOLAR) - \d+D$")
REPROBAR_DIARIO_S = 1800.0        # cooldown entre reintentos de un plazo rechazado hoy
REPROBAR_CHECK_S = 60.0           # cadencia del chequeo (µs cuando no hay nada que reprobar)
_REPROBAR_HORAS = (7, 18)         # ventana BA [desde, hasta) en la que se reprueba


def _es_diario(symbol: str) -> bool:
    """Símbolo cuya validez depende del día (plazos de caución)."""
    return bool(_RE_CAUCION.match(symbol))


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


class BrokerHTTPError(RuntimeError):
    """El broker respondió con un HTTP ≠ 200. `status_code` deja decidir al
    OMS: un 5xx después de mandar una orden NO prueba que no la procesó."""

    def __init__(self, path: str, status_code: int, text: str = "") -> None:
        super().__init__(f"{path} → HTTP {status_code}: {text}")
        self.path = path
        self.status_code = int(status_code)


class BrokerRespuestaInvalida(RuntimeError):
    """HTTP 200 con cuerpo vacío o no-JSON: el request llegó, la respuesta no
    se puede interpretar (sesión vencida, proxy, corte al serializar)."""


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
        # Desde cuándo NO hay socket (monotonic; None = conectado). Con sesión y
        # el lector recién arrancado, los primeros CONNECT_GRACE_S son
        # "conectando", no "feed caído": /conexion mostraba el rojo "⚠ Feed
        # caído" pegado al "✅ Conectado" porque start() vuelve antes del
        # handshake, y el desk volvía a apretar Reconectar (tirando un WS sano).
        self._disconnected_since: Optional[float] = time.monotonic()
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
        # Cache persistido de rechazados: por host, con la fecha del rechazo
        # (TTL). Se carga acá para que el PRIMER subscribe ya salga sin ellos.
        self._host = (urlsplit(self.base_url).netloc or self.base_url).lower()
        self._rejected_fecha: Dict[str, str] = {}
        self._rej_dirty = False
        self._rej_handle: Optional[asyncio.TimerHandle] = None
        # Plazos de caución rechazados HOY: {símbolo: monotonic del rechazo}
        # (cooldown, ver _es_diario). Nunca van al cache persistido.
        self._rechazo_diario: Dict[str, float] = {}
        self._diario_avisado: Set[str] = set()          # un log por plazo y por día
        self._reprobar_todo = False                      # cambió el día: pedir todos los plazos
        self._reprobar_universo = False                  # tormenta + cambio de día: pedir TODO de nuevo
        self._tormenta = False                           # ver _TORMENTA_FRAC
        self._reprobar_task: Optional[asyncio.Task] = None
        from backend.locale_ar import hoy_ba
        self._dia_diario = hoy_ba()
        self._cargar_rechazados()

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
        motivo crudo del broker. Los fallos que ocurren DESPUÉS de que el
        request llegó al broker (HTTP 5xx, cuerpo vacío o no-JSON) salen con
        tipos propios: para una orden nueva son resultado DESCONOCIDO, no un
        rechazo limpio."""
        if self._http is None:
            raise RuntimeError(f"{path} → sin sesión del broker (sin login). Conectá en /conexion.")
        r = await self._http.get(path, params=params or {})
        if r.status_code != 200:
            raise BrokerHTTPError(path, r.status_code, r.text[:200])
        if not r.text.strip():
            raise BrokerRespuestaInvalida(f"{path} → respuesta vacía (¿sesión vencida? Reconectá en /conexion).")
        try:
            return r.json()
        except ValueError as e:
            raise BrokerRespuestaInvalida(f"{path} → no devolvió JSON: {r.text[:200]}") from e

    async def start(self, symbols: Iterable[str] = ()) -> None:
        """Spawn the reader loop. Idempotent."""
        if self._task and not self._task.done():
            return
        self._subscriptions.update(symbols)
        self._stop_evt.clear()
        self._task = asyncio.create_task(self._run_loop(), name="primary_ws")
        self._reprobar_task = asyncio.create_task(self._reprobar_loop(), name="primary_ws_reprobar")
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
        if self._reprobar_task:
            try:
                await asyncio.wait_for(self._reprobar_task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._reprobar_task.cancel()
            self._reprobar_task = None
        if self._http is not None:
            await self._http.aclose()
            self._http = None
        await self._flush_rechazados()
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
        now = time.monotonic()
        # Plazos de caución: de a uno y sin los rechazados hoy en cooldown
        # (ver _es_diario / reprobar_pendientes).
        diarios = [s for s in syms if _es_diario(s)
                   and now - self._rechazo_diario.get(s, -1e18) >= REPROBAR_DIARIO_S]
        futs = [s for s in syms if _is_futuro(s)]
        rest = [s for s in syms if not _is_futuro(s) and not _es_diario(s)]
        n_lotes = 0
        for group, entries in ((rest, None), (futs, ENTRIES_FUT)):
            for i in range(0, len(group), SUBSCRIBE_CHUNK):
                await ws.send(_subscribe_payload(group[i:i + SUBSCRIBE_CHUNK], entries=entries))
                n_lotes += 1
                await asyncio.sleep(0.05)
        for s in diarios:
            await ws.send(_subscribe_payload([s]))
            await asyncio.sleep(0.02)
        if syms:
            logger.info("[primary_ws] subscribe en %d lotes de <=%d (%d símbolos, %d futuros, "
                        "%d plazos de caución de a uno)",
                        n_lotes, SUBSCRIBE_CHUNK, len(rest) + len(futs) + len(diarios), len(futs), len(diarios))

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
            if _es_diario(bad):
                # Plazo de caución sin rueda HOY: no es un símbolo inválido.
                # Cooldown y se reprueba (reprobar_pendientes); jamás al cache.
                self._rechazo_diario[bad] = time.monotonic()
                if bad not in self._diario_avisado:
                    self._diario_avisado.add(bad)
                    logger.info("[primary_ws] %s rechazado: plazo sin rueda hoy (se reprueba cada %d min)",
                                bad, int(REPROBAR_DIARIO_S // 60))
                return
            # rechazo de un único símbolo -> es inválido, lo descartamos (y
            # queda en el cache local para los próximos arranques).
            if bad not in self._rejected:
                self._rejected.add(bad)
                self._rejected_fecha[bad] = date.today().isoformat()
                self._programar_guardado()
                logger.warning("[primary_ws] símbolo inválido descartado: %s", bad)
                self._chequear_tormenta()
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
            if s in self._rejected or self._tormenta:       # tormenta: no hay nada que salvar de a uno
                continue
            try:
                await ws.send(_subscribe_payload([s], entries=entries))
                await asyncio.sleep(0.02)
            except (ConnectionClosed, WebSocketException):
                return

    def _reset_reintentos(self) -> None:
        """Nueva conexión = un pase nuevo de recuperación por lote: olvida qué
        símbolos ya se reintentaron de a uno (y sin OI) en la conexión
        anterior. Los rechazados firmes (`_rejected`) siguen afuera."""
        self._retried_individually.clear()
        self._retried_no_oi.clear()

    # ── Tormenta de rechazos (sesión / permisos, no símbolos) ───────

    def _es_tormenta(self, n: int) -> bool:
        return n > _TORMENTA_MIN and n > _TORMENTA_FRAC * max(len(self._subscriptions), 1)

    def _chequear_tormenta(self) -> None:
        if self._tormenta or not self._es_tormenta(len(self._rejected)):
            return
        self._tormenta = True
        self._stats["tormenta"] = True
        logger.warning("[primary_ws] %s rechazó %d de %d símbolos — no parece un problema de símbolos "
                       "sino de la sesión / los permisos de market data de la cuenta (%s). No guardo el "
                       "cache de rechazados; «Reprobar» en /conexion o el cambio de día prueban todo de nuevo",
                       self._host, len(self._rejected), len(self._subscriptions),
                       self._stats.get("last_error_desc") or "el broker no mandó descripción")

    def _cache_es_tormenta(self) -> bool:
        """El cache cargado ya viene con una tormenta de otra sesión (la mitad
        del universo o más): no vale como lista de símbolos inválidos."""
        return not self._tormenta and self._es_tormenta(len(self._rejected))

    def _olvidar_en_memoria(self) -> int:
        n = len(self._rejected) + len(self._rechazo_diario)
        self._rejected.clear()
        self._rejected_fecha.clear()
        self._retried_individually.clear()
        self._retried_no_oi.clear()
        self._rechazo_diario.clear()
        self._diario_avisado.clear()
        self._tormenta = False
        self._stats["tormenta"] = False
        self._rej_dirty = True
        return n

    async def olvidar_rechazados(self) -> int:
        """Olvida TODOS los rechazos (memoria + cache del host en disco) y, si
        está conectado, vuelve a suscribir el universo entero — el botón
        «Reprobar símbolos rechazados» de /conexion. Devuelve cuántos olvidó."""
        n = self._olvidar_en_memoria()
        await self._flush_rechazados()                   # deja el host vacío en el JSON
        if self._ws is not None and self._connected:
            try:
                await self._send_in_chunks(self._ws, self._subscriptions)
            except (ConnectionClosed, WebSocketException) as exc:
                logger.warning("[primary_ws] resubscribe tras olvidar rechazados falló: %s", exc)
        logger.info("[primary_ws] olvidé %d símbolos rechazados de %s y volví a pedir el universo", n, self._host)
        return n

    async def reprobar_pendientes(self, now_fn=None) -> List[str]:
        """Vuelve a pedir, de a uno, lo que el broker rechazó pero puede volver
        a existir: los plazos de caución rechazados hoy pasado el cooldown
        (`REPROBAR_DIARIO_S`), TODOS los plazos cuando cambió el día (BA) y los
        rechazados persistentes cuya entrada venció (`REJECTED_TTL_DAYS`) con el
        proceso arriba — antes sólo se reprobaban al reiniciar la app. Sólo
        conectado y dentro de `_REPROBAR_HORAS`; fuera de la ventana se prueban
        al conectar. Lo llama `_reprobar_loop` cada `REPROBAR_CHECK_S`
        (µs si no hay nada); devuelve lo que mandó."""
        from datetime import datetime
        from backend.locale_ar import TZ_BA
        ahora = now_fn() if now_fn else datetime.now(TZ_BA)
        hoy = ahora.date()
        if hoy != self._dia_diario:
            self._dia_diario = hoy
            self._rechazo_diario.clear()
            self._diario_avisado.clear()
            self._reprobar_todo = True
            if self._tormenta:                            # un día nuevo: la cuenta pudo arreglarse
                self._olvidar_en_memoria()
                self._reprobar_universo = True
        limite = (hoy - timedelta(days=REJECTED_TTL_DAYS)).isoformat()
        vencidos = [s for s, f in self._rejected_fecha.items() if f < limite]
        for s in vencidos:
            self._rejected.discard(s)
            self._rejected_fecha.pop(s, None)
            self._retried_individually.discard(s)
        if vencidos:
            self._programar_guardado()
        if self._ws is None or not self._connected:
            return []
        if not (_REPROBAR_HORAS[0] <= ahora.hour < _REPROBAR_HORAS[1]):
            return []
        if self._reprobar_universo:
            self._reprobar_universo = self._reprobar_todo = False
            logger.info("[primary_ws] día nuevo tras una tormenta de rechazos: pido el universo entero de nuevo")
            await self._send_in_chunks(self._ws, self._subscriptions)
            return sorted(self._subscriptions)
        t = time.monotonic()
        due = []
        for s in sorted(self._subscriptions):
            if _es_diario(s):
                if self._reprobar_todo or (s in self._rechazo_diario
                                           and t - self._rechazo_diario[s] >= REPROBAR_DIARIO_S):
                    due.append(s)
            elif s in vencidos:
                due.append(s)
        self._reprobar_todo = False
        if not due:
            return []
        for s in due:
            self._rechazo_diario.pop(s, None)
        logger.info("[primary_ws] repruebo %d símbolos rechazados: %s", len(due),
                    ", ".join(due[:6]) + ("…" if len(due) > 6 else ""))
        await self._resubscribe_individually(due, None)
        return due

    async def _reprobar_loop(self) -> None:
        while not self._stop_evt.is_set():
            try:
                await asyncio.wait_for(self._stop_evt.wait(), timeout=REPROBAR_CHECK_S)
                break
            except asyncio.TimeoutError:
                pass
            try:
                await self.reprobar_pendientes()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("[primary_ws] reprobar_pendientes falló")

    # ── Cache persistido de símbolos rechazados ─────────────────────

    def _cargar_rechazados(self) -> None:
        path = _rejected_cache_path()
        if not path:
            return
        por_host = _leer_json(path).get(self._host)
        if not isinstance(por_host, dict) or not por_host:
            return
        limite = (date.today() - timedelta(days=REJECTED_TTL_DAYS)).isoformat()
        # Los plazos de caución de un cache viejo se ignoran (validez por día).
        vigentes = {s: f for s, f in por_host.items()
                    if isinstance(s, str) and isinstance(f, str) and f >= limite and not _es_diario(s)}
        if not vigentes:
            return
        self._rejected.update(vigentes)
        self._rejected_fecha.update(vigentes)
        logger.info("[primary_ws] %d símbolos rechazados por %s cargados del cache local "
                    "(se vuelven a probar a los %d días)", len(vigentes), self._host, REJECTED_TTL_DAYS)

    def _programar_guardado(self) -> None:
        """UNA escritura por tormenta: se reprograma con cada rechazo y corre
        _REJECTED_SAVE_DELAY después del último, en el executor (nada de I/O
        de archivo en el event loop). Sin loop (tests sync) escribe directo."""
        self._rej_dirty = True
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._guardar_rechazados(dict(self._rejected_fecha))
            return
        if self._rej_handle is not None:
            self._rej_handle.cancel()
        self._rej_handle = loop.call_later(_REJECTED_SAVE_DELAY, self._guardar_en_executor, loop)

    def _guardar_en_executor(self, loop: asyncio.AbstractEventLoop) -> None:
        self._rej_handle = None
        snap = dict(self._rejected_fecha)          # copia en el hilo del loop
        try:
            loop.run_in_executor(None, self._guardar_rechazados, snap)
        except RuntimeError:
            pass  # loop cerrándose: lo escribe el flush de stop()

    async def _flush_rechazados(self) -> None:
        if self._rej_handle is not None:
            self._rej_handle.cancel()
            self._rej_handle = None
        if self._rej_dirty:
            snap = dict(self._rejected_fecha)
            await asyncio.get_running_loop().run_in_executor(None, self._guardar_rechazados, snap)

    def _guardar_rechazados(self, snap: Dict[str, str]) -> None:
        """Escribe {host: {símbolo: fecha}} conservando los otros hosts del
        archivo (una máquina que alterna brokers). Atómico (tmp + replace)."""
        path = _rejected_cache_path()
        self._rej_dirty = False
        if not path:
            return
        try:
            data = _leer_json(path) if os.path.exists(path) else {}
            # Con tormenta el snapshot no es una lista de símbolos inválidos:
            # el host queda vacío (y lo que hubiera de antes también se va).
            data[self._host] = {} if self._tormenta else dict(sorted(snap.items()))
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            tmp = f"{path}.tmp-{os.getpid()}"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=0)
            os.replace(tmp, path)
        except OSError as exc:
            logger.warning("[primary_ws] no pude guardar el cache de rechazados (%s): %s", path, exc)

    # Sin un Md en este tiempo consideramos el feed "stale" (mercado quieto o
    # conexión muerta). 90 s cubre holgado un mercado ilíquido intradía.
    STALE_AFTER = 90.0

    def stats(self) -> Dict[str, Any]:
        s = dict(self._stats)
        s["subscriptions"] = len(self._subscriptions)
        s["rejected"] = len(self._rejected)
        s["rechazados_hoy"] = sorted(self._rechazo_diario)      # plazos de caución sin rueda hoy
        s["tormenta"] = self._tormenta
        s["disconnected_s"] = (None if self._connected
                               else round(time.monotonic() - (self._disconnected_since or time.monotonic()), 1))
        s["connecting"] = self.connecting
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
    def connecting(self) -> bool:
        """Sesión abierta, lector corriendo y sin socket hace menos de
        CONNECT_GRACE_S: el handshake / la reconexión está en curso. NO es
        "feed caído" (feed_health) — eso es un corte sostenido."""
        if self._connected or self._cookies is None or self._task is None or self._task.done():
            return False
        since = self._disconnected_since
        return since is not None and (time.monotonic() - since) < CONNECT_GRACE_S

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
            self._disconnected_since = None
            self._stats["connected"] = True
            logger.info("[primary_ws] connected to %s", self.ws_url)

            if self._subscriptions:
                # Cada conexión vuelve a mandar TODO el universo en lotes: un
                # lote que matrizoms rechaza (un símbolo que dejó de existir
                # desde la última vez) tiene que poder reintentarse de a uno
                # otra vez. `_retried_individually` no se limpiaba nunca → en
                # la reconexión el mismo lote rechazado volvía con `pending`
                # vacío y los 20 símbolos quedaban MUDOS hasta reiniciar, sin
                # una línea de log (09/10: así se callaban 3D/4D/14D/21D y los
                # bonos vecinos del lote de las cauciones).
                self._reset_reintentos()
                if self._cache_es_tormenta():
                    logger.warning("[primary_ws] el cache local trae %d de %d símbolos rechazados por %s — "
                                   "demasiados para ser inválidos: los olvido y pruebo todo de nuevo",
                                   len(self._rejected), len(self._subscriptions), self._host)
                    self._olvidar_en_memoria()
                    self._programar_guardado()
                await self._send_in_chunks(ws, self._subscriptions)

            try:
                async for raw in ws:
                    if self._stop_evt.is_set():
                        return
                    self._handle_message(raw)
            finally:
                self._connected = False
                if self._disconnected_since is None:
                    self._disconnected_since = time.monotonic()
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
                desc = obj.get("description") or obj.get("error")
                if isinstance(desc, str) and desc.strip():
                    self._stats["last_error_desc"] = desc.strip()[:200]   # motivo del broker (/conexion)
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
# Versión del CONTEXTO de broker (host + sesión): sube en cada swap del
# singleton. Los tickets de órdenes la guardan al armarse y el envío la
# re-chequea; los caches de comitentes / instrumentos la llevan en la key. Así
# un ticket armado contra el broker A no viaja al broker B después de una
# reconexión, y una lista de cuentas del contexto viejo no sobrevive al cambio.
_context_version = 0


def context_version() -> int:
    return _context_version


def get_ws_client(base_url: str | None = None) -> PrimaryWS:
    """Process-wide singleton."""
    global _singleton
    if _singleton is None:
        from backend.config import settings  # noqa: WPS433

        _singleton = PrimaryWS(base_url or settings.primary_base_url)
    return _singleton


def set_ws_client(client: PrimaryWS) -> PrimaryWS:
    """Publica `client` como singleton y sube la versión de contexto. El caller
    debe haber logueado el candidato ANTES (y stop()eado el viejo)."""
    global _singleton, _context_version
    _singleton = client
    _context_version += 1
    return _singleton


def reset_ws_client(base_url: str) -> PrimaryWS:
    """Reemplaza el singleton por uno nuevo apuntando a `base_url` (reconexión
    en caliente). Preferir el flujo de /conexion: candidato logueado primero y
    recién ahí `set_ws_client` — esto queda para compatibilidad/tests."""
    return set_ws_client(PrimaryWS(base_url))
