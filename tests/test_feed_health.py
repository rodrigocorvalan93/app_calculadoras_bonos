"""feed_health — detectar el broker que autentica pero no manda market data.

Caso real: con un broker el WS quedaba CONECTADO pero mudo; el seq avanzaba por
MAE/pollers y los precios que se veían eran los persistidos de la última rueda.
`feed_down` (sesión sin socket) no saltaba y hubo que darse cuenta a ojo."""
from __future__ import annotations


import pytest

from backend.services import feed_health


class _FakeWS:
    def __init__(self, *, auth=True, connected=True, alive=True):
        self.authenticated = auth
        self._connected = connected
        self.feed_alive = alive

    def stats(self):
        return {"connected": self._connected, "stale_seconds": 999.0}


def _patch_ws(monkeypatch, **kw):
    from backend.services import primary_ws

    ws = _FakeWS(**kw)
    monkeypatch.setattr(primary_ws, "get_ws_client", lambda: ws)
    return ws


def test_data_age_refleja_el_tick_mas_nuevo(monkeypatch) -> None:
    from backend.services import bond_universe, fx as fx_svc, marketdata_store as mds
    from backend.services import symbols as syms

    bond_universe.ensure_loaded()
    bases = fx_svc.fx_bases()
    if not bases:
        pytest.skip("sin bases USD en especies.py")
    mds.get_store().update_from_md(syms.md_symbol(bases[0], "24hs"), {"LA": {"price": 70.0}})
    age = feed_health.data_age_s()
    assert age is not None and age < 5.0


def test_socket_vivo_pero_sin_md_alarma_en_rueda(monkeypatch) -> None:
    """El caso silencioso: authenticated + connected pero feed_alive False →
    `warn` seteado (md_stale), aunque feed_down siga False."""
    from backend.services import watchdog

    _patch_ws(monkeypatch, auth=True, connected=True, alive=False)
    monkeypatch.setattr(watchdog, "en_rueda", lambda now=None: True)
    h = feed_health.snapshot()
    assert h["feed_down"] is False
    assert h["md_stale"] is True
    assert h["warn"] is not None and "viejos" in h["warn"]


def test_fuera_de_rueda_no_alarma(monkeypatch) -> None:
    from backend.services import watchdog

    _patch_ws(monkeypatch, auth=True, connected=True, alive=False)
    monkeypatch.setattr(watchdog, "en_rueda", lambda now=None: False)
    h = feed_health.snapshot()
    assert h["warn"] is None and h["md_stale"] is False and h["data_stale"] is False


def test_sin_login_no_alarma(monkeypatch) -> None:
    """Paper/dev: sin sesión de broker no hay nada que reclamarle al feed."""
    from backend.services import watchdog

    _patch_ws(monkeypatch, auth=False, connected=False, alive=False)
    monkeypatch.setattr(watchdog, "en_rueda", lambda now=None: True)
    h = feed_health.snapshot()
    assert h["feed_down"] is False and h["warn"] is None


def test_ws_desconectado_es_feed_down(monkeypatch) -> None:
    from backend.services import watchdog

    _patch_ws(monkeypatch, auth=True, connected=False, alive=False)
    monkeypatch.setattr(watchdog, "en_rueda", lambda now=None: True)
    h = feed_health.snapshot()
    assert h["feed_down"] is True
    assert h["warn"] is None            # el warn es para el caso NO-caído


def test_watchdog_ahora_mira_feed_alive(monkeypatch) -> None:
    """El mail del watchdog también salta con el socket vivo pero mudo."""
    from backend.services import primary_ws, watchdog

    ws = _FakeWS(auth=True, connected=True, alive=False)
    monkeypatch.setattr(primary_ws, "get_ws_client", lambda: ws)
    assert watchdog._feed_down() is True
    ws.feed_alive = True
    assert watchdog._feed_down() is False


@pytest.mark.asyncio
async def test_market_health_endpoint_expone_warn(monkeypatch) -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.services import watchdog

    _patch_ws(monkeypatch, auth=True, connected=True, alive=False)
    monkeypatch.setattr(watchdog, "en_rueda", lambda now=None: True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/market/health")
    h = r.json()
    assert r.status_code == 200
    for k in ("feed_down", "warn", "md_stale", "data_stale", "en_rueda", "data_age_s"):
        assert k in h
    assert h["md_stale"] is True and h["warn"]


@pytest.mark.asyncio
async def test_market_health_lleva_la_version_de_los_estaticos(monkeypatch) -> None:
    """Pestaña abierta a través de un deploy (JS viejo contra server nuevo →
    "se cae todo el tiempo" en la PC de un compañero, 09/10): /market/health
    manda la versión de los estáticos y la página la lleva en
    <body data-asset-v>; app.js compara y ofrece recargar (nunca sola)."""
    import re

    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    _patch_ws(monkeypatch, auth=True, connected=True, alive=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        h = (await ac.get("/market/health")).json()
        page = await ac.get("/inicio")
    v = app.state.asset_v
    assert isinstance(v, int) and v > 0 and h["asset_v"] == v
    assert page.status_code == 200
    m = re.search(r'<body[^>]*\sdata-asset-v="(\d+)"', page.text)
    assert m and int(m.group(1)) == v
    # el JS compara contra esa versión y arma el aviso (sin recargar solo)
    js = (page.text and open("backend/static/js/app.js", encoding="utf-8").read())
    assert "dataset.assetV" in js and "checkVersion(h)" in js and "location.reload()" in js
    assert js.count("location.reload()") == 1


@pytest.mark.asyncio
async def test_excel_snapshot_lleva_health_solo_con_warn(monkeypatch) -> None:
    import json

    from backend.routes import excel as excel_route

    # con warn → viaja la sección health
    monkeypatch.setattr(feed_health, "snapshot",
                        lambda: {"warn": "sin ticks BYMA hace 12 min — precios posiblemente viejos"})
    excel_route._cache.clear()
    data = json.loads(excel_route._snapshot_bytes(""))
    assert data["health"]["warn"].startswith("sin ticks")
    # sin warn → no viaja (payload compacto)
    monkeypatch.setattr(feed_health, "snapshot", lambda: {"warn": None})
    excel_route._cache.clear()
    data = json.loads(excel_route._snapshot_bytes(""))
    assert "health" not in data
