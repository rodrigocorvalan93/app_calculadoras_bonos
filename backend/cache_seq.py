"""Cache de render por seq del store — un render sirve a N clientes.

Los paneles live (riel, tape, tablas de Curvas/Mercado, oficial) se
re-renderizan en cada `md-update`: con varios usuarios mirando el MISMO
panel, el server armaba el mismo HTML una vez por cliente por tick. Este
decorador cachea la respuesta ya renderizada keyeada por
(path, query string, seq del store):

  - un tick real avanza la seq → invalida al instante (los autoupdates no
    pierden NADA de frescura: el primer request post-tick renderiza, el
    resto de la ventana lo comparte);
  - el TTL acota la frescura de las fuentes que NO pasan por el store
    (MAE/SIOPEL, series macro) aunque la seq esté quieta fuera de rueda.

Con un usuario el costo es un lookup de dict (~ns); con N usuarios el
trabajo por tick pasa de N renders a 1.

Además el decorador habilita REVALIDACIÓN HTTP (ETag + Cache-Control
no-cache): el browser manda `If-None-Match` en cada poll y, si el HTML no
cambió, la respuesta es un 304 SIN body (~200 bytes en el aire en vez del
HTML completo). Clave para el consumo de datos: la seq es GLOBAL del store
— avanza con el tick de cualquier símbolo — así que un panel se re-renderiza
seguido con contenido idéntico; el hash se compara también después del
rebuild, y ese caso vuelve 304 igual. Cuando el contenido SÍ cambió, viaja
completo al instante (frescura intacta). El swap de htmx recibe el body
cacheado del browser de forma transparente.

Dos cosas más que se miden en rueda:

  - SINGLE-FLIGHT: 5 usuarios con el mismo panel abierto reciben el tick a
    la vez y los 5 requests entraban al rebuild (5 renders de 35 ms en fila).
    Ahora el primero rinde y los demás esperan ese mismo resultado.
  - GZIP PRE-COMPRIMIDO: GZipMiddleware comprimía cada respuesta en el event
    loop, también los hits (296 KB → 2,3 ms por request). Acá se comprime UNA
    vez por render, en el threadpool (zlib suelta el GIL), y el hit sirve los
    bytes ya comprimidos; el middleware deja pasar lo que ya trae
    Content-Encoding. El ETag es del body sin comprimir.
"""
from __future__ import annotations

import asyncio
import functools
import gzip
import hashlib
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

from fastapi.responses import Response

_MAX_ENTRIES = 256          # paneles×queries reales son decenas; esto es un fusible
_GZIP_MIN = 1024            # igual que el middleware: no comprimir respuestas chicas
_GZIP_LEVEL = 5

# Contadores globales para la tarjeta de salud de /admin. Incrementos sin lock
# a propósito: son diagnósticos (una carrera pierde una cuenta, no importa) y
# el hot path no paga sincronización.
stats: Dict[str, int] = {"hit": 0, "hit_304": 0, "miss": 0, "miss_304": 0, "hit_sf": 0}


def _hdrs(etag: str, marker: str) -> Dict[str, str]:
    # `private`: que ningún proxy intermedio lo guarde (hay sesión). `no-cache`
    # = "guardalo pero revalidá SIEMPRE": el browser nunca muestra algo viejo
    # sin preguntar, y el server contesta 304 sin body cuando nada cambió.
    return {"ETag": etag, "Cache-Control": "private, no-cache", "x-seq-cache": marker}


def _serve(ent: Dict[str, Any], request: Any, marker: str) -> Response:
    """Respuesta desde una entrada cacheada: 304 si el cliente ya la tiene,
    si no el body (pre-gzipeado cuando el cliente lo acepta)."""
    inm = request.headers.get("if-none-match")
    if inm == ent["etag"]:
        stats["hit_304" if marker == "hit" else "miss_304"] += 1
        return Response(status_code=304, headers=_hdrs(ent["etag"], marker + "-304"))
    stats[marker if marker in stats else "hit"] += 1
    headers = _hdrs(ent["etag"], marker)
    if marker == "miss":
        headers.pop("x-seq-cache", None)     # contrato de siempre: el render fresco no lleva marca
    headers["content-type"] = ent["ctype"]
    gz = ent.get("gz")
    if gz is not None and "gzip" in (request.headers.get("accept-encoding") or ""):
        headers["content-encoding"] = "gzip"
        headers["vary"] = "Accept-Encoding"
        return Response(content=gz, headers=headers)
    return Response(content=ent["body"], headers=headers)


def seq_cached(ttl: float = 2.0, per_user: bool = False) -> Callable:
    """Decorador para endpoints async que devuelven una Response con body
    (HTML o JSON) y toman `request`.

    `per_user=True`: la key incluye el username de la sesión. OBLIGATORIO para
    cualquier endpoint cuyo HTML dependa del usuario (tenencias filtradas por
    `visible_fondos_for`, por ej.): sin esto el cache es compartido y el
    render de un usuario puede servirse a otro con distinta visibilidad
    (fuga cross-usuario — el caso `mercado_book`). El costo es un render por
    usuario en vez de uno global; el 304 por ETag se conserva igual.
    """
    def deco(fn: Callable) -> Callable:
        cache: Dict[Tuple, Dict[str, Any]] = {}
        lock = threading.Lock()
        inflight: Dict[Tuple, "asyncio.Future[Optional[Dict[str, Any]]]"] = {}

        async def _build(args: tuple, kwargs: dict, key: Tuple, seq: int) -> Tuple[Any, Optional[Dict[str, Any]]]:
            resp = await fn(*args, **kwargs)
            body = getattr(resp, "body", None)
            if getattr(resp, "status_code", 200) != 200 or not body:
                return resp, None
            etag = '"' + hashlib.md5(body).hexdigest() + '"'
            gz = None
            if len(body) >= _GZIP_MIN:
                # zlib suelta el GIL: comprimir en el pool no frena el loop.
                gz = await asyncio.get_running_loop().run_in_executor(
                    None, gzip.compress, body, _GZIP_LEVEL)
            ent = {"seq": seq, "until": time.monotonic() + ttl, "body": body, "etag": etag,
                   "gz": gz, "ctype": resp.headers.get("content-type") or "text/html; charset=utf-8"}
            with lock:
                if len(cache) >= _MAX_ENTRIES:
                    # Evictar el cuarto MÁS VIEJO (dicts = orden de
                    # inserción), no vaciar todo: el fusible saltaba con
                    # keys descartables (`?q=` del buscador de CEDEARs
                    # crea una por texto tipeado) y tiraba de golpe los
                    # renders calientes de TODOS los paneles/usuarios,
                    # que volvían a construirse en frío a la vez.
                    for k in list(cache)[: _MAX_ENTRIES // 4]:
                        cache.pop(k, None)
                # until se calcula AL GUARDAR, no con el `now` de la entrada
                # del wrapper: si el handler tardó (stall de red en un
                # refresh 2×/día, por ej.), la entrada nacería ya vencida.
                cache[key] = ent
            return resp, ent

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any):
            request = kwargs.get("request")
            if request is None:
                request = next((a for a in args if hasattr(a, "query_params")), None)
            if request is None:                      # sin request no hay key → directo
                return await fn(*args, **kwargs)

            from backend.services import marketdata_store
            seq = marketdata_store.get_store().seq()
            key: Tuple = (request.url.path, str(request.query_params))
            if per_user:
                u = getattr(request.state, "user", None) or {}
                key = key + (u.get("username"),)
            now = time.monotonic()
            with lock:
                ent = cache.get(key)
            if ent is not None and ent["seq"] == seq and now < ent["until"]:
                return _serve(ent, request, "hit")

            # Single-flight: si esta key ya se está reconstruyendo (otro
            # cliente recibió el mismo tick), esperar ese render.
            fut = inflight.get(key)
            if fut is not None:
                try:
                    ent = await asyncio.shield(fut)
                except Exception:  # noqa: BLE001 — el que rinde reporta el error; acá se reintenta
                    ent = None
                if ent is not None and ent["seq"] >= seq:
                    return _serve(ent, request, "hit_sf")
            loop = asyncio.get_running_loop()
            fut = loop.create_future()
            inflight[key] = fut
            try:
                resp, ent = await _build(args, kwargs, key, seq)
            except BaseException as exc:
                if not fut.done():
                    fut.set_exception(exc)
                raise
            finally:
                if inflight.get(key) is fut:
                    inflight.pop(key, None)
            if not fut.done():
                fut.set_result(ent)
            if ent is None:
                return resp
            # Comparar TAMBIÉN tras el rebuild: la seq global avanzó por un
            # tick de OTRO símbolo pero este panel quedó idéntico — el
            # cliente ya lo tiene, no viaja de nuevo.
            return _serve(ent, request, "miss")

        return wrapper
    return deco
