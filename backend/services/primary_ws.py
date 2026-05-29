"""Async WebSocket client for Primary / matrizoms.

One singleton lives in the FastAPI process. Workflow:

  1. login via REST (`primary_client.login` → cookies on the httpx
     AsyncClient).
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
import json
import logging
import time
from typing import Any, Dict, Iterable, Optional, Set

import httpx
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from .marketdata_store import MarketDataStore, get_store

logger = logging.getLogger("backend.primary_ws")


KEEPALIVE_SECS = 25
BACKOFF_INITIAL = 2.0
BACKOFF_MAX = 30.0

# Entries Primary will accept. Confirmed: WA / TC are rejected and make
# the whole query return empty. Same list the legacy app uses.
ENTRIES = ["BI", "OF", "LA", "OP", "CL", "HI", "LO", "EV", "TV", "NV"]


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


def _subscribe_payload(symbols: Iterable[str], depth: int = 3) -> str:
    return json.dumps({
        "type": "smd",
        "level": 1,
        "entries": ENTRIES,
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
        self._connected = False
        self._stats: Dict[str, Any] = {
            "connected": False,
            "messages": 0,
            "reconnects": 0,
            "last_message_at": 0.0,
            "last_error": None,
            "subscriptions": 0,
        }

    # ── API ─────────────────────────────────────────────────────────

    async def login(self, username: str, password: str) -> bool:
        """REST login. Cookies are kept in `self._cookies` for the WS handshake."""
        if not username or not password:
            logger.info("[primary_ws] no credentials provided, skipping login")
            return False
        # follow_redirects=True: el login OK de Spring Security responde 302
        # -> /marketdata.html. requests (legacy) seguía el redirect por
        # defecto; httpx no. Sin esto, raise_for_status() trata el 302 como
        # error y descartamos las cookies de sesión válidas.
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
            self._cookies = self._http.cookies
            logger.info("[primary_ws] login OK (%d cookies)", len(list(self._cookies.jar)))
            return True
        except httpx.HTTPError as exc:
            self._stats["last_error"] = f"login: {exc}"
            logger.warning("[primary_ws] login failed: %s", exc)
            return False

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
                    await self._ws.send(_subscribe_payload(self._subscriptions))
                    logger.info(
                        "[primary_ws] subscribed %d new (total %d)",
                        len(new), len(self._subscriptions),
                    )
                except (ConnectionClosed, WebSocketException) as exc:
                    logger.warning("[primary_ws] resubscribe failed: %s", exc)

    def stats(self) -> Dict[str, Any]:
        s = dict(self._stats)
        s["subscriptions"] = len(self._subscriptions)
        return s

    @property
    def authenticated(self) -> bool:
        return self._cookies is not None

    # ── Internals ───────────────────────────────────────────────────

    async def _run_loop(self) -> None:
        backoff = BACKOFF_INITIAL
        while not self._stop_evt.is_set():
            if self._cookies is None:
                # No credentials → nothing to do. Re-check periodically
                # in case `login` was called after start.
                await asyncio.sleep(2.0)
                continue
            try:
                await self._connect_and_read()
                backoff = BACKOFF_INITIAL  # clean exit (stop): reset
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                self._connected = False
                self._stats["connected"] = False
                self._stats["last_error"] = f"{type(exc).__name__}: {exc}"
                logger.warning("[primary_ws] disconnected: %s — reconnect in %.0fs", exc, backoff)
                try:
                    await asyncio.wait_for(self._stop_evt.wait(), timeout=backoff)
                    break  # stop set during the wait
                except asyncio.TimeoutError:
                    pass
                backoff = min(backoff * 2, BACKOFF_MAX)
                self._stats["reconnects"] += 1

    async def _connect_and_read(self) -> None:
        cookie_hdr = _cookie_header(self._cookies)
        headers = {"Cookie": cookie_hdr} if cookie_hdr else None
        async with websockets.connect(
            self.ws_url,
            additional_headers=headers,
            ping_interval=KEEPALIVE_SECS,
            ping_timeout=KEEPALIVE_SECS,
            max_size=4 * 1024 * 1024,
            close_timeout=2.0,
        ) as ws:
            self._ws = ws
            self._connected = True
            self._stats["connected"] = True
            logger.info("[primary_ws] connected to %s", self.ws_url)

            if self._subscriptions:
                await ws.send(_subscribe_payload(self._subscriptions))
                logger.info("[primary_ws] subscribed to %d symbols", len(self._subscriptions))

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
