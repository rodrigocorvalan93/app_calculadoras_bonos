"""Settings via pydantic-settings.

Pulls credentials and tuning knobs from env vars / .env at the repo root.
Defaults are safe for local dev (no broker login required for Phase 1 YAS).

Credenciales del broker (market data) — reutiliza tu secrets.txt:
  Al importar este módulo cargamos `OMSsecrets`, el mismo loader que usa la
  app legacy: vuelca `secrets.txt` (KEY=VALUE) a os.environ SIN pisar las env
  vars reales del sistema. Así el backend FastAPI levanta exactamente las
  mismas credenciales que ya tenés, sin duplicarlas en un `.env`.

  Tu secrets.txt define el usuario/clave del broker como OMS_USER / OMS_PASS.
  Después de instanciar Settings() resolvemos `primary_user`/`primary_pass`
  directo de os.environ (ver bloque al final del módulo), aceptando ambos
  juegos de nombres y sin depender de cómo pydantic resuelva alias entre
  versiones. Prioridad:
    PRIMARY_USER / PRIMARY_PASS (env real)  >  OMS_USER / OMS_PASS (secrets)  >  ""
"""
from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


REPO_ROOT = Path(__file__).resolve().parent.parent

# ── Reutilizar secrets.txt (mismo loader que la app legacy) ───────────────
# `import OMSsecrets` auto-carga secrets.txt -> os.environ en el momento del
# import (no pisa env vars ya definidas). Se hace ANTES de instanciar
# Settings() (al final del módulo) para que las variables ya estén en el
# entorno. Falla en silencio si OMSsecrets o secrets.txt no están (las env
# vars del sistema siguen funcionando igual).
try:
    import OMSsecrets  # noqa: F401  (efecto colateral: auto-load de secrets.txt)
except Exception:  # noqa: BLE001  — nunca romper el arranque por esto
    pass


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Credenciales del broker. Se completan de forma robusta luego de
    # instanciar Settings() (ver bloque al final), aceptando tanto
    # PRIMARY_USER/PRIMARY_PASS como los OMS_USER/OMS_PASS de tu secrets.txt.
    primary_user: str = ""
    primary_pass: str = ""

    # Broker
    primary_base_url: str = "https://api.latinsecurities.matrizoms.com.ar/"

    # Default settlement
    default_plazo: str = "24hs"

    # Phase 1 caches
    metrics_ttl_seconds: int = 5
    metrics_cache_max: int = 4096

    # OMS (cursado de órdenes). SEGURIDAD: oms_live arranca APAGADO — en False
    # toda orden se registra como PAPER (simulada) y NUNCA viaja al broker.
    # Para operar en serio: OMS_LIVE=1 en secrets.txt/env, con límites abajo.
    oms_live: bool = False
    oms_max_notional: float = 1_000_000_000.0     # tope por orden, bonos ARS
    oms_max_notional_usd: float = 5_000_000.0     # tope por orden, hard-dollar (USD/USB)
    oms_price_band_pct: float = 10.0              # banda vs last/close (fat-finger)

    # Comitentes (cuentas) por broker — números SENSIBLES, fuera de git. JSON
    # {broker: {etiqueta: nro}}, ej {"lbo": {"PYMES": "54437"}, "cocos": {"PERSO": "27404"}}.
    # Se carga como secret del entorno (env var OMS_COMITENTES) o en .env/secrets.txt.
    # Vacío ⇒ el panel usa sólo lo que devuelve el broker por REST (genérico).
    oms_comitentes: str = ""

    # Phase 2 warmup daemon. Interval must stay under the curve metrics
    # cache TTL (20 s) so a sweep refreshes every bucket before it expires
    # and the curves table never hits a cold cache mid-session.
    warmup_enabled: bool = True
    warmup_interval_seconds: int = 8


settings = Settings()

# ── Fallback robusto de credenciales del broker ───────────────────────────
# Tu secrets.txt define las credenciales como OMS_USER / OMS_PASS (no
# PRIMARY_USER / PRIMARY_PASS). OMSsecrets ya las volcó a os.environ arriba;
# acá las inyectamos en `settings` directamente, sin depender de cómo pydantic
# resuelva los alias entre versiones. Prioridad:
#   1) PRIMARY_USER / PRIMARY_PASS  (env real explícita, si la seteaste)
#   2) OMS_USER     / OMS_PASS      (secrets.txt / legacy)
if not settings.primary_user:
    settings.primary_user = os.environ.get("PRIMARY_USER") or os.environ.get("OMS_USER") or ""
if not settings.primary_pass:
    settings.primary_pass = os.environ.get("PRIMARY_PASS") or os.environ.get("OMS_PASS") or ""
