"""Poller del add-in de Excel (auditoría F11/F13): el JS real en un VM de Node
(tests/excel_poller_harness.cjs) + el flag de salud de /excel/v1/seq."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(shutil.which("node") is None, reason="node no disponible")
def test_poller_js_en_node() -> None:
    r = subprocess.run([shutil.which("node"), str(ROOT / "tests" / "excel_poller_harness.cjs")],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode in (0, 1), r.stderr
    out = json.loads(r.stdout)
    assert out["seq_quieto"]["ok"], out["seq_quieto"]        # refresca aunque el seq no avance
    assert out["fetch_colgado"]["ok"], out["fetch_colgado"]  # un solo request en vuelo
    assert out["errores"]["ok"], out["errores"]              # backoff ante errores seguidos
    assert out["flags"]["ok"], out["flags"]                  # stale / down desde /seq
    assert out["cuerpo_colgado"]["ok"], out["cuerpo_colgado"]        # R09: timeout hasta el cuerpo
    assert out["oneshot_colgado"]["ok"], out["oneshot_colgado"]      # R09: el rescate también
    assert out["ok"]


@pytest.mark.asyncio
async def test_seq_lleva_flag_de_salud(monkeypatch) -> None:
    from httpx import ASGITransport, AsyncClient
    from backend.main import app
    from backend.routes import excel as ex
    from backend.services import feed_health

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        monkeypatch.setattr(feed_health, "snapshot", lambda: {"feed_down": False, "warn": None})
        ex._health_flag_cache["at"] = 0.0
        t = (await ac.get("/excel/v1/seq")).text
        assert t.strip().isdigit()
        monkeypatch.setattr(feed_health, "snapshot", lambda: {"feed_down": False, "warn": "sin ticks"})
        ex._health_flag_cache["at"] = 0.0
        t = (await ac.get("/excel/v1/seq")).text
        assert t.endswith(" stale") and int(t.split()[0]) >= 0      # parseInt-compatible
        monkeypatch.setattr(feed_health, "snapshot", lambda: {"feed_down": True, "warn": None})
        ex._health_flag_cache["at"] = 0.0
        assert (await ac.get("/excel/v1/seq")).text.endswith(" down")
