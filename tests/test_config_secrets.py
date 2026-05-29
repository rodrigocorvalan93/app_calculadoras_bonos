"""The backend reads broker creds from the legacy secrets.txt.

OMSsecrets loads secrets.txt → os.environ as OMS_USER / OMS_PASS; config.py
bridges those onto the names the backend reads (PRIMARY_USER / PRIMARY_PASS)
without clobbering anything already set the backend's way.
"""
from __future__ import annotations

import os

from backend.config import _load_secrets_into_env


def _reset(monkeypatch) -> None:
    for k in ("PRIMARY_USER", "PRIMARY_PASS", "OMS_USER", "OMS_PASS"):
        monkeypatch.delenv(k, raising=False)
    # the bridge writes os.environ directly (not via monkeypatch), so clear it
    os.environ.pop("PRIMARY_USER", None)
    os.environ.pop("PRIMARY_PASS", None)


def test_bridges_legacy_oms_names(monkeypatch) -> None:
    _reset(monkeypatch)
    monkeypatch.setenv("OMS_USER", "alice")
    monkeypatch.setenv("OMS_PASS", "s3cr3t")
    try:
        _load_secrets_into_env()
        assert os.environ["PRIMARY_USER"] == "alice"
        assert os.environ["PRIMARY_PASS"] == "s3cr3t"
    finally:
        os.environ.pop("PRIMARY_USER", None)
        os.environ.pop("PRIMARY_PASS", None)


def test_real_primary_env_wins_over_secrets(monkeypatch) -> None:
    _reset(monkeypatch)
    monkeypatch.setenv("PRIMARY_USER", "real-user")   # already set the backend's way
    monkeypatch.setenv("OMS_USER", "from-secrets")
    _load_secrets_into_env()
    assert os.environ["PRIMARY_USER"] == "real-user"  # not clobbered
