"""Frescura del feed BYMA — la señal honesta de "los precios que ves son de AHORA".

Caso real que motiva esto: un broker con el WS CONECTADO pero sin mandar market
data. `feed_down` (sesión sin socket) no salta porque el socket está vivo, el
seq del store sigue avanzando por MAE/pollers/macro → el dot decía "en vivo" y
los precios que se veían eran los PERSISTIDOS de la última rueda buena. El
usuario se tuvo que dar cuenta a ojo.

Acá se mide lo único que de verdad importa, en dos capas:
- `feed_alive` del WS: llegó un mensaje de market data hace < STALE_AFTER (90 s).
- Edad del tick más nuevo en una canasta líquida del store (soberanos USD y sus
  patas C/D): `updated_at` NO se bumpea en los restores de la persistencia, así
  que la edad es honesta aunque el server recién arranque con datos viejos.

Sólo alarma EN RUEDA (mismo horario que el watchdog / relojes de la topbar) y
con sesión de broker abierta — de noche o en paper/dev no hay falso positivo.
Todo lecturas de flags y ~45 dict-lookups en memoria: µs por llamada.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

# Sin NINGÚN tick en la canasta líquida por 5 min EN RUEDA = datos viejos.
STALE_DATA_S = 300.0


def data_age_s() -> Optional[float]:
    """Edad (segundos) del tick más nuevo entre los soberanos líquidos (bases
    USD + patas C/D, 24hs). None = ni un snapshot en la canasta."""
    from backend.services import fx as fx_svc, marketdata_store, symbols as syms

    store = marketdata_store.get_store()
    try:
        bases = fx_svc.fx_bases()
    except Exception:  # noqa: BLE001 — universo no cargado (arranque)
        bases = []
    newest = 0.0
    for b in bases:
        for suf in ("", "D", "C"):
            snap = store.get(syms.md_symbol(b + suf, "24hs"))
            ua = (getattr(snap, "updated_at", 0.0) or 0.0) if snap is not None else 0.0
            if ua > newest:
                newest = ua
    if newest <= 0:
        return None
    return max(0.0, time.time() - newest)


def snapshot() -> Dict[str, Any]:
    """Veredicto de salud del feed. Claves compatibles con el /market/health
    histórico (feed_alive/authenticated/connected/stale_seconds/feed_down) más
    la capa de frescura: en_rueda, data_age_s, md_stale, data_stale y `warn`
    (texto listo para mostrar, None = todo bien)."""
    from backend.services import primary_ws
    from backend.services.watchdog import en_rueda

    ws = primary_ws.get_ws_client()
    try:
        st = ws.stats() or {}
    except Exception:  # noqa: BLE001
        st = {}
    auth = bool(getattr(ws, "authenticated", False))
    connected = bool(st.get("connected"))
    alive = bool(getattr(ws, "feed_alive", False))
    rueda = bool(en_rueda())
    age = data_age_s()

    feed_down = bool(auth and not connected)
    # El caso silencioso: socket conectado pero sin Md reciente del broker.
    md_stale = bool(rueda and auth and connected and not alive)
    # Y el doble check por los datos mismos: nada tickeó en la canasta líquida.
    data_stale = bool(rueda and auth and (age is None or age > STALE_DATA_S))

    warn = None
    if not feed_down and (md_stale or data_stale):
        if age is not None and age > 90.0:
            warn = f"sin ticks BYMA hace {int(age // 60)} min — precios posiblemente viejos"
        else:
            warn = "conectado pero sin market data del broker — precios posiblemente viejos"

    return {
        "feed_alive": alive, "authenticated": auth, "connected": connected,
        "stale_seconds": st.get("stale_seconds"),
        "feed_down": feed_down, "en_rueda": rueda,
        "data_age_s": (round(age, 1) if age is not None else None),
        "md_stale": md_stale, "data_stale": data_stale, "warn": warn,
    }
