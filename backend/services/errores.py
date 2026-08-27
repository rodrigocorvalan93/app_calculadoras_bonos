"""Ring buffer de WARNINGs/errores del proceso — tarjeta "Errores recientes"
de /admin. El 80% del valor de un Sentry a costo cero: cuando a un usuario
"no le anda algo", el superuser ve la excepción sin pedir logs.

Costo: sólo se paga al EMITIR un warning/error (ya de por sí raros) — cero
en el hot path. El buffer vive en memoria (se pierde al reiniciar: para
historia larga está el log del servicio)."""
from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import datetime
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

_TZ_BA = ZoneInfo("America/Argentina/Buenos_Aires")
_BUF: deque = deque(maxlen=120)
_lock = threading.Lock()
_installed = False


class _RingHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:  # noqa: D102
        try:
            msg = self.format(record)
        except Exception:  # noqa: BLE001 — el handler jamás tira
            msg = record.getMessage()
        with _lock:
            _BUF.append({
                "ts": datetime.fromtimestamp(record.created, _TZ_BA).strftime("%d/%m %H:%M:%S"),
                "level": record.levelname,
                "logger": record.name,
                # con exc_info el format() incluye el traceback: guardamos la cola
                # (ahí está la línea del error) acotada para no inflar memoria
                "msg": msg if len(msg) <= 900 else "…" + msg[-900:],
            })


def install() -> None:
    """Engancha el handler al root logger (idempotente). WARNING para arriba."""
    global _installed
    if _installed:
        return
    h = _RingHandler(level=logging.WARNING)
    h.setFormatter(logging.Formatter("%(message)s"))
    logging.getLogger().addHandler(h)
    _installed = True


def ultimos(n: int = 120) -> List[Dict[str, Any]]:
    """Los últimos n registros, más nuevo primero."""
    with _lock:
        items = list(_BUF)
    return items[-max(1, int(n)):][::-1]
