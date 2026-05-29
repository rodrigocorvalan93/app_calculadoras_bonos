"""Settings via pydantic-settings.

Pulls credentials and tuning knobs from env vars / .env at the repo root.
Defaults are safe for local dev (no broker login required for Phase 1 YAS).

Credenciales del broker (market data) — reutiliza tu secrets.txt:
  Al importar este módulo cargamos `OMSsecrets`, el mismo loader que usa la
  app legacy: vuelca `secrets.txt` (KEY=VALUE) a os.environ SIN pisar las env
  vars reales del sistema. Así el backend FastAPI levanta exactamente las
  mismas credenciales que ya tenés, sin duplicarlas en un `.env`.

  Además, `primary_user`/`primary_pass` aceptan dos juegos de nombres (ver
  AliasChoices más abajo):
    - PRIMARY_USER / PRIMARY_PASS  (nombres "nuevos" del backend)
    - OMS_USER     / OMS_PASS      (los que ya usás en secrets.txt / legacy)

  Prioridad de resolución: env var real del sistema > secrets.txt > "".
"""
from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


REPO_ROOT = Path(__file__).resolve().parent.parent

# ── Reutilizar secrets.txt (mismo loader que la app legacy) ───────────────
# `import OMSsecrets` auto-carga secrets.txt -> os.environ en el momento del
# import (no pisa env vars ya definidas). Lo hacemos ACÁ, antes de instanciar
# Settings() al final del módulo, para que las variables ya estén en el
# entorno cuando pydantic las lea. Falla en silencio si OMSsecrets o
# secrets.txt no están (las env vars del sistema siguen funcionando igual).
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

    # Credenciales del broker. Aceptan los nombres nuevos (PRIMARY_USER /
    # PRIMARY_PASS) y los del secrets.txt legacy (OMS_USER / OMS_PASS), en ese
    # orden de preferencia. Con case_sensitive=False el match no distingue
    # mayúsculas. Si querés forzar otras credenciales solo para el backend,
    # seteá PRIMARY_USER/PRIMARY_PASS (env real) y ganan sobre el secrets.txt.
    primary_user: str = Field(
        "", validation_alias=AliasChoices("PRIMARY_USER", "OMS_USER")
    )
    primary_pass: str = Field(
        "", validation_alias=AliasChoices("PRIMARY_PASS", "OMS_PASS")
    )

    # Broker
    primary_base_url: str = "https://api.latinsecurities.matrizoms.com.ar/"

    # Default settlement
    default_plazo: str = "24hs"

    # Phase 1 caches
    metrics_ttl_seconds: int = 5
    metrics_cache_max: int = 4096

    # Phase 2 warmup daemon. Interval must stay under the curve metrics
    # cache TTL (20 s) so a sweep refreshes every bucket before it expires
    # and the curves table never hits a cold cache mid-session.
    warmup_enabled: bool = True
    warmup_interval_seconds: int = 8


settings = Settings()
