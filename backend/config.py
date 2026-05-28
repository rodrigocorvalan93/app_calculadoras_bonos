"""Settings via pydantic-settings.

Pulls credentials and tuning knobs from env vars / .env at the repo root.
Defaults are safe for local dev (no broker login required for Phase 1 YAS).
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    primary_user: str = ""
    primary_pass: str = ""

    # Broker
    primary_base_url: str = "https://api.latinsecurities.matrizoms.com.ar/"

    # Default settlement
    default_plazo: str = "24hs"

    # Phase 1 caches
    metrics_ttl_seconds: int = 5
    metrics_cache_max: int = 4096


settings = Settings()
