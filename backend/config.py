"""Settings via pydantic-settings.

Pulls credentials and tuning knobs from env vars / .env at the repo root.
Defaults are safe for local dev (no broker login required for Phase 1 YAS).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_secrets_into_env() -> None:
    """Feed the backend from the same ``secrets.txt`` the Streamlit app uses.

    Importing ``OMSsecrets`` auto-loads ``secrets.txt`` → ``os.environ`` (flat
    ``KEY=VALUE``; it never clobbers vars already in the real environment). The
    legacy stores broker creds as ``OMS_USER`` / ``OMS_PASS``; bridge those onto
    the names this backend reads (``PRIMARY_USER`` / ``PRIMARY_PASS``) without
    overwriting anything already set the backend's way. All best-effort — a
    missing or malformed secrets file must never block startup (no creds simply
    means no live market data).
    """
    try:
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        import OMSsecrets  # noqa: F401  — import side effect loads secrets.txt
    except Exception:  # noqa: BLE001 — secrets are optional for local dev
        pass
    for legacy, native in (("OMS_USER", "PRIMARY_USER"), ("OMS_PASS", "PRIMARY_PASS")):
        val = os.getenv(legacy)
        if val and not os.getenv(native):
            os.environ[native] = val


_load_secrets_into_env()


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

    # Phase 2 warmup daemon. Interval must stay under the curve metrics
    # cache TTL (20 s) so a sweep refreshes every bucket before it expires
    # and the curves table never hits a cold cache mid-session.
    warmup_enabled: bool = True
    warmup_interval_seconds: int = 8


settings = Settings()
