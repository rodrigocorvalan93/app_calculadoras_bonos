"""Async httpx client for the Primary / matrizoms broker.

Phase 1 only ships the login coroutine. WebSocket + REST market data and
the full async port of OMSmktdata land in Phase 2/4. The client is a
singleton — every tab in the same process shares the cookie jar.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

from backend.config import settings

logger = logging.getLogger("backend.primary")


class PrimaryClient:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url
        self._client: Optional[httpx.AsyncClient] = None
        self._lock = asyncio.Lock()
        self._authenticated = False

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def authenticated(self) -> bool:
        return self._authenticated

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            # follow_redirects=True: el login (j_spring_security_check) OK
            # devuelve 302 -> /marketdata.html; sin seguir el redirect,
            # raise_for_status() lo toma como error y se pierde la sesión.
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(10.0, connect=5.0),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
                follow_redirects=True,
            )
        return self._client

    async def login(self, username: str, password: str) -> bool:
        """POST j_spring_security_check. Stores cookies in the shared client."""
        async with self._lock:
            client = await self._ensure_client()
            try:
                resp = await client.post(
                    "j_spring_security_check",
                    data={"j_username": username, "j_password": password},
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("[primary] login failed: %s", exc)
                self._authenticated = False
                return False
            self._authenticated = True
            logger.info("[primary] login OK as %s", username)
            return True

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            self._authenticated = False


_singleton: Optional[PrimaryClient] = None


def get_client() -> PrimaryClient:
    global _singleton
    if _singleton is None:
        _singleton = PrimaryClient(settings.primary_base_url)
    return _singleton
