"""Watchdog del feed — mail si el WS del broker se cae en horario de rueda.

El dot rojo de la topbar sólo sirve si estás mirando la pantalla: esto manda
un mail cuando el feed lleva caído más de `feed_watchdog_min` minutos dentro
de la rueda (11:00–17:00 BA, hábiles), y otro al recuperarse (sólo si avisó
la caída). Un solo aviso por caída — nada de spam por flapping.

"Caído" = misma señal que /market/health: hay sesión del broker
(authenticated) pero el WS no está conectado. De noche o sin login no alarma.
El chequeo corre cada ~60 s en el event loop (lecturas de flags, ~µs); el
mail sale en el threadpool.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, Dict, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger("backend.watchdog")

_TZ = ZoneInfo("America/Argentina/Buenos_Aires")
CHECK_EVERY_SECONDS = 60.0


def _rueda() -> tuple:
    """Horario de rueda BYMA en minutos desde medianoche BA — MISMO setting
    que los relojes de la topbar (MKT_HORARIO_ARG, 'HH:MM-HH:MM')."""
    import re
    from backend.config import settings
    m = re.match(r"^(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})$",
                 (settings.mkt_horario_arg or "").strip())
    if not m:
        return (10 * 60 + 30, 17 * 60)
    return (int(m[1]) * 60 + int(m[2]), int(m[3]) * 60 + int(m[4]))


def _feed_down() -> bool:
    from backend.services.primary_ws import get_ws_client
    ws = get_ws_client()
    try:
        return bool(ws.authenticated and not ws.stats().get("connected"))
    except Exception:  # noqa: BLE001
        return False


def en_rueda(now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(_TZ)
    mins = now.hour * 60 + now.minute
    o, c = _rueda()
    return now.weekday() < 5 and o <= mins < c


class FeedWatchdog:
    """Máquina de estados chica y testeable: down_since / avisado."""

    def __init__(self, umbral_min: Optional[float] = None,
                 is_down: Callable[[], bool] = _feed_down,
                 now_fn: Callable[[], datetime] = lambda: datetime.now(_TZ)) -> None:
        if umbral_min is None:
            from backend.config import settings
            umbral_min = float(settings.feed_watchdog_min)
        self.umbral_s = umbral_min * 60.0
        self._is_down = is_down
        self._now = now_fn
        self.down_since: Optional[datetime] = None
        self.avisado = False

    def _mail(self, subject: str, body: str) -> None:
        from backend.services import mailer
        to = mailer.default_recipient()
        if not mailer.is_configured() or not to:
            logger.warning("[watchdog] %s — sin SMTP/destinatario, no se manda mail", subject)
            return
        ok, detail = mailer.send(to, subject, body)
        if not ok:
            logger.warning("[watchdog] mail falló: %s", detail)

    def check_once(self) -> Optional[str]:
        """Un pase. Devuelve 'caida' / 'recuperado' si mandó aviso, None si no."""
        now = self._now()
        down = self._is_down()
        if down:
            if self.down_since is None:
                self.down_since = now
            elapsed = (now - self.down_since).total_seconds()
            if not self.avisado and elapsed >= self.umbral_s and en_rueda(now):
                self.avisado = True
                mins = int(elapsed // 60)
                logger.warning("[watchdog] feed caído hace %d min — mando aviso", mins)
                self._mail(f"⚠ Feed BYMA caído ({mins} min)",
                           f"El WS del broker está desconectado desde las "
                           f"{self.down_since.strftime('%H:%M')} (BA) — hace {mins} min, "
                           f"en horario de rueda.\n\nLos precios de la app pueden estar "
                           f"congelados. Revisá /conexion o reiniciá la app.\n\n"
                           f"— Calculadora de Bonos (watchdog)")
                return "caida"
        else:
            if self.avisado:
                caida = self.down_since.strftime("%H:%M") if self.down_since else "?"
                self.down_since = None
                self.avisado = False
                logger.info("[watchdog] feed recuperado — mando aviso")
                self._mail("✓ Feed BYMA recuperado",
                           f"El WS del broker volvió a conectar (caída iniciada {caida} BA). "
                           f"Los precios corren de nuevo.\n\n— Calculadora de Bonos (watchdog)")
                return "recuperado"
            self.down_since = None
        return None

    def status(self) -> Dict[str, Any]:
        return {"down_since": self.down_since.isoformat() if self.down_since else None,
                "avisado": self.avisado, "umbral_min": self.umbral_s / 60.0}


_watchdog: Optional[FeedWatchdog] = None


def get_watchdog() -> FeedWatchdog:
    global _watchdog
    if _watchdog is None:
        _watchdog = FeedWatchdog()
    return _watchdog
