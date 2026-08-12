"""Puente HTTPS local del add-in de Excel — TLS sin tocar el uvicorn http.

Office exige https para el runtime de funciones custom: sobre http el
taskpane funciona pero el runtime de las celdas =OMS.* no arranca (queda
"Se está iniciando el runtime de los complementos…" y #N/D). Pasar TODO el
server a TLS rompería los bookmarks http y el flujo LAN actual, así que en
su lugar un listener TLS mínimo (asyncio puro, mismo proceso) acepta en
`tls_port` y pipea cada conexión al uvicorn http local.

Del stream sólo se reescribe el HEAD del PRIMER request de cada conexión:

  · pisa `X-Forwarded-Proto: https` y `X-Forwarded-For: 127.0.0.1`
    (descartando los que vengan del cliente — nadie spoofea el scheme).
    uvicorn confía proxy-headers desde 127.0.0.1 por default, así que la
    app ve `request.url.scheme == "https"` y el manifest del add-in sale
    con base https sin tocar nada más.
  · fuerza `Connection: close` → una respuesta por conexión. Así NUNCA hay
    que parsear el framing de las respuestas ni de requests siguientes
    (el cliente reabre; en loopback el handshake extra es despreciable
    para el tráfico del add-in: 1 seq/s + snapshots + calc puntuales).

El body del request y toda la respuesta se pipean crudos hasta EOF. NO es
un reverse proxy general — es el mínimo para que Office hable TLS con la
app local. Certs: backend/tools/https_local.py (el .bat los genera).
"""
from __future__ import annotations

import asyncio
import logging
import ssl
from pathlib import Path
from typing import Optional

from backend.config import REPO_ROOT, settings
from backend.tools.https_local import CA_CERT, LEAF_CERT, LEAF_KEY

logger = logging.getLogger("backend.tls")

_MAX_HEAD = 64 * 1024          # head más grande → conexión cerrada (nada legal mide eso)
_HEAD_TIMEOUT = 15.0           # segundos para recibir el head completo
_CHUNK = 65536

# Headers que el puente PISA (los del cliente se descartan): forwarded* para
# que nadie inyecte scheme/ip, connection para forzar el modelo 1-request.
_STRIP = (b"x-forwarded-proto:", b"x-forwarded-for:", b"x-forwarded-host:",
          b"forwarded:", b"connection:", b"proxy-connection:", b"keep-alive:")
_INJECT = (b"X-Forwarded-Proto: https\r\n"
           b"X-Forwarded-For: 127.0.0.1\r\n"
           b"Connection: close\r\n")


def cert_dir() -> Path:
    return Path(settings.tls_cert_dir) if settings.tls_cert_dir else REPO_ROOT / "certs"


def ca_cert_path() -> Path:
    """Certificado (público) de la CA local — lo sirve /excel/ca.crt para
    confiar el https del puente en otra compu de la mesa."""
    return cert_dir() / CA_CERT


def _rewrite_head(head: bytes) -> Optional[bytes]:
    """Reescribe el head de un request http/1.x: descarta hop-headers y
    forwarded* del cliente e inyecta los nuestros. None si no parece HTTP."""
    sep = head.find(b"\r\n")
    if sep <= 0:
        return None
    request_line, resto = head[:sep], head[sep + 2:]
    # request-line mínima: METHOD SP TARGET SP HTTP/…
    if b" HTTP/" not in request_line or request_line.count(b" ") < 2:
        return None
    keep = []
    for line in resto.split(b"\r\n"):
        if not line:
            continue
        if line.lstrip().lower().startswith(_STRIP):
            continue
        keep.append(line)
    return request_line + b"\r\n" + b"\r\n".join(keep) + (b"\r\n" if keep else b"") + _INJECT + b"\r\n"


async def _pump(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while True:
            chunk = await reader.read(_CHUNK)
            if not chunk:
                break
            writer.write(chunk)
            await writer.drain()
    except (OSError, asyncio.CancelledError):
        pass
    try:
        writer.write_eof()
    except (OSError, RuntimeError):
        pass


class TlsBridge:
    def __init__(self, certfile: Path, keyfile: Path, host: str, port: int,
                 target_host: str, target_port: int) -> None:
        self.certfile, self.keyfile = certfile, keyfile
        self.host, self.port = host, port
        self.target_host, self.target_port = target_host, target_port
        self._server: Optional[asyncio.base_events.Server] = None

    async def start(self) -> None:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(str(self.certfile), str(self.keyfile))
        self._server = await asyncio.start_server(
            self._handle, self.host, self.port, ssl=ctx, limit=_MAX_HEAD + _CHUNK)
        logger.info("[tls] puente HTTPS del add-in en https://localhost:%s → http://%s:%s "
                    "(manifest: https://localhost:%s/excel/manifest.xml)",
                    self.port, self.target_host, self.target_port, self.port)

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handle(self, cr: asyncio.StreamReader, cw: asyncio.StreamWriter) -> None:
        tw: Optional[asyncio.StreamWriter] = None
        try:
            try:
                head = await asyncio.wait_for(cr.readuntil(b"\r\n\r\n"), _HEAD_TIMEOUT)
            except (asyncio.IncompleteReadError, asyncio.LimitOverrunError,
                    asyncio.TimeoutError, OSError):
                return
            nuevo = _rewrite_head(head)
            if nuevo is None:
                return
            try:
                tr, tw = await asyncio.open_connection(self.target_host, self.target_port)
            except OSError:
                cw.write(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n"
                         b"Content-Length: 0\r\n\r\n")
                await cw.drain()
                return
            tw.write(nuevo)
            await tw.drain()
            # cliente→app (body del request, si hay) corre aparte; la conexión
            # vive hasta que la app termina su respuesta (Connection: close ⇒
            # EOF del lado app marca el final).
            c2t = asyncio.ensure_future(_pump(cr, tw))
            try:
                await _pump(tr, cw)
            finally:
                c2t.cancel()
        except (ConnectionError, ssl.SSLError):
            pass  # handshake fallido / cliente cortó: ruido normal, sin log
        except Exception:  # noqa: BLE001 — nunca tirar el server por una conexión
            logger.debug("[tls] conexión con error", exc_info=True)
        finally:
            for w in (tw, cw):
                if w is not None:
                    try:
                        w.close()
                    except (OSError, RuntimeError):
                        pass


_bridge: Optional[TlsBridge] = None


def active_port() -> Optional[int]:
    """Puerto del puente si está corriendo (para la tarjeta de /admin)."""
    return _bridge.port if _bridge and _bridge._server else None


async def start_from_settings() -> Optional[TlsBridge]:
    """Arranca el puente si está habilitado y los certs existen. Failure-silent:
    sin certs (o puerto tomado) la app sigue en http puro, con un log claro."""
    global _bridge
    if not settings.tls_bridge:
        return None
    cert, key = cert_dir() / LEAF_CERT, cert_dir() / LEAF_KEY
    if not cert.exists() or not key.exists():
        logger.info("[tls] sin certs en %s — el add-in de Excel queda en http y las "
                    "funciones =OMS.* NO arrancan (correr: python -m backend.tools.https_local)",
                    cert_dir())
        return None
    bridge = TlsBridge(cert, key, settings.tls_bridge_host, settings.tls_port,
                       "127.0.0.1", settings.tls_target_port)
    try:
        await bridge.start()
    except OSError as e:
        logger.warning("[tls] no pude escuchar en %s:%s (%s) — sigo sin https",
                       settings.tls_bridge_host, settings.tls_port, e)
        return None
    _bridge = bridge
    return bridge


async def stop() -> None:
    global _bridge
    if _bridge:
        await _bridge.stop()
        _bridge = None
