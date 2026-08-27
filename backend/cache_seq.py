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
"""
from __future__ import annotations

import functools
import hashlib
import threading
import time
from typing import Any, Callable, Dict, Tuple

from fastapi.responses import HTMLResponse, Response

_MAX_ENTRIES = 256          # paneles×queries reales son decenas; esto es un fusible

# Contadores globales para la tarjeta de salud de /admin. Incrementos sin lock
# a propósito: son diagnósticos (una carrera pierde una cuenta, no importa) y
# el hot path no paga sincronización.
stats: Dict[str, int] = {"hit": 0, "hit_304": 0, "miss": 0, "miss_304": 0}


def _hdrs(etag: str, marker: str) -> Dict[str, str]:
    # `private`: que ningún proxy intermedio lo guarde (hay sesión). `no-cache`
    # = "guardalo pero revalidá SIEMPRE": el browser nunca muestra algo viejo
    # sin preguntar, y el server contesta 304 sin body cuando nada cambió.
    return {"ETag": etag, "Cache-Control": "private, no-cache", "x-seq-cache": marker}


def seq_cached(ttl: float = 2.0) -> Callable:
    """Decorador para endpoints async que devuelven HTML y toman `request`."""
    def deco(fn: Callable) -> Callable:
        cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
        lock = threading.Lock()

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any):
            request = kwargs.get("request")
            if request is None:
                request = next((a for a in args if hasattr(a, "query_params")), None)
            if request is None:                      # sin request no hay key → directo
                return await fn(*args, **kwargs)

            from backend.services import marketdata_store
            seq = marketdata_store.get_store().seq()
            key = (request.url.path, str(request.query_params))
            inm = request.headers.get("if-none-match")
            now = time.monotonic()
            with lock:
                ent = cache.get(key)
            if ent is not None and ent["seq"] == seq and now < ent["until"]:
                if inm == ent["etag"]:
                    stats["hit_304"] += 1
                    return Response(status_code=304, headers=_hdrs(ent["etag"], "hit-304"))
                stats["hit"] += 1
                return HTMLResponse(ent["body"], headers=_hdrs(ent["etag"], "hit"))

            resp = await fn(*args, **kwargs)
            body = getattr(resp, "body", None)
            if getattr(resp, "status_code", 200) == 200 and body:
                etag = '"' + hashlib.md5(body).hexdigest() + '"'
                with lock:
                    if len(cache) >= _MAX_ENTRIES:
                        cache.clear()
                    # until se calcula AL GUARDAR, no con el `now` de la entrada
                    # del wrapper: si el handler tardó (stall de red en un
                    # refresh 2×/día, por ej.), la entrada nacería ya vencida.
                    cache[key] = {"seq": seq, "until": time.monotonic() + ttl,
                                  "body": body, "etag": etag}
                # Comparar TAMBIÉN tras el rebuild: la seq global avanzó por un
                # tick de OTRO símbolo pero este panel quedó idéntico — el
                # cliente ya lo tiene, no viaja de nuevo.
                if inm == etag:
                    stats["miss_304"] += 1
                    return Response(status_code=304, headers=_hdrs(etag, "miss-304"))
                stats["miss"] += 1
                resp.headers["ETag"] = etag
                resp.headers["Cache-Control"] = "private, no-cache"
            return resp

        return wrapper
    return deco
