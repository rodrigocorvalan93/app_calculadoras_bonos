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
"""
from __future__ import annotations

import functools
import threading
import time
from typing import Any, Callable, Dict, Tuple

from fastapi.responses import HTMLResponse

_MAX_ENTRIES = 256          # paneles×queries reales son decenas; esto es un fusible


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
            now = time.monotonic()
            with lock:
                ent = cache.get(key)
            if ent is not None and ent["seq"] == seq and now < ent["until"]:
                return HTMLResponse(ent["body"], headers={"x-seq-cache": "hit"})

            resp = await fn(*args, **kwargs)
            body = getattr(resp, "body", None)
            if getattr(resp, "status_code", 200) == 200 and body:
                with lock:
                    if len(cache) >= _MAX_ENTRIES:
                        cache.clear()
                    # until se calcula AL GUARDAR, no con el `now` de la entrada
                    # del wrapper: si el handler tardó (stall de red en un
                    # refresh 2×/día, por ej.), la entrada nacería ya vencida.
                    cache[key] = {"seq": seq, "until": time.monotonic() + ttl, "body": body}
            return resp

        return wrapper
    return deco
