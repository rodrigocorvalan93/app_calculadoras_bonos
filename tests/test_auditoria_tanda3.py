"""Regresiones de la auditoría externa, tanda 3: contexto de broker (F01),
estados de orden (F03), sesiones por versión (F06), reset atómico (F12) y
readiness (F17)."""
from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from backend.config import settings
from backend.services import auth, oms, primary_ws


def _client() -> AsyncClient:
    from backend.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


@pytest.fixture()
def auth_on(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "app_users_path", str(tmp_path / "store.json"))
    auth.refresh()
    auth.ensure_bootstrapped()
    yield
    auth.refresh()


@pytest.fixture()
def oms_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(oms, "_AUDIT_PATH", tmp_path / "audit.jsonl")
    monkeypatch.setattr(oms, "_tail_cache", None)
    monkeypatch.setattr(oms, "_accounts_cache", None)
    oms.kill_switch(False)
    yield
    oms.kill_switch(False)
    oms.set_live(None)


def _payload(**kw):
    p = {"code": "AL30", "symbol": "MERV - XMEV - AL30 - 24hs", "side": "buy", "qty": 100.0,
         "price": 941.0, "account": "C1", "ordtype": "limit"}
    p.update(kw)
    return p


class _FakeWS:
    """Cliente de broker simulado para /conexion y para el envío."""
    authenticated = False
    feed_alive = False

    def __init__(self, url: str = "", ok: bool = True, raise_: bool = False):
        self.base_url = url
        self.ok, self.raise_ = ok, raise_
        self.stopped = self.started = False

    async def login(self, u, p):
        if self.raise_:
            raise RuntimeError("DNS caído (sintético)")
        return self.ok

    async def stop(self):
        self.stopped = True

    async def start(self, symbols=()):
        self.started = True

    def stats(self):
        return {}


# ── F01 · reconexión: login candidato ANTES de tocar el cliente compartido ──
@pytest.mark.asyncio
async def test_f01_login_fallido_no_toca_el_cliente_compartido(monkeypatch) -> None:
    import backend.main as main_mod
    from backend.routes import conexion
    from starlette.responses import HTMLResponse

    orig = primary_ws.get_ws_client()
    monkeypatch.setattr(settings, "primary_base_url", settings.primary_base_url)
    monkeypatch.setattr(settings, "primary_user", settings.primary_user)
    monkeypatch.setattr(settings, "primary_pass", settings.primary_pass)
    monkeypatch.setattr(conexion, "_render", lambda request, tpl, **ctx: HTMLResponse(str(ctx.get("msg", ctx))))
    monkeypatch.setattr(conexion, "_status_ctx", lambda *a, **k: {"msg": a[0] if a else "", "ok": a[1] if len(a) > 1 else True})
    monkeypatch.setattr(main_mod, "_initial_symbols", lambda: ["MERV - XMEV - AL30 - 24hs"])
    url = conexion.KNOWN_HOSTS[0][1]
    viejo = _FakeWS("https://viejo/")
    primary_ws.set_ws_client(viejo)
    try:
        v0 = primary_ws.context_version()
        async with _client() as ac:
            # 1) el broker rechaza → el cliente actual sigue intacto
            monkeypatch.setattr(primary_ws, "PrimaryWS", lambda u: _FakeWS(u, ok=False))
            r = await ac.post("/conexion/login", data={"url": url, "username": "u", "password": "p"})
            assert r.status_code == 200 and "rechazó" in r.text
            assert primary_ws.get_ws_client() is viejo and not viejo.stopped
            assert primary_ws.context_version() == v0
            # 2) excepción de red → ídem
            monkeypatch.setattr(primary_ws, "PrimaryWS", lambda u: _FakeWS(u, raise_=True))
            r = await ac.post("/conexion/login", data={"url": url, "username": "u", "password": "p"})
            assert "No pude conectar" in r.text and primary_ws.get_ws_client() is viejo and not viejo.stopped
            # 3) login OK → recién ahí se para el viejo, se publica el nuevo y sube la versión
            nuevos = []

            def _mk(u):
                nuevos.append(_FakeWS(u, ok=True))
                return nuevos[-1]

            monkeypatch.setattr(primary_ws, "PrimaryWS", _mk)
            r = await ac.post("/conexion/login", data={"url": url, "username": "u", "password": "p"})
            assert "Conectado" in r.text
            assert viejo.stopped and primary_ws.get_ws_client() is nuevos[-1] and nuevos[-1].started
            assert primary_ws.context_version() == v0 + 1 and settings.primary_base_url == url
    finally:
        primary_ws.set_ws_client(orig)


def test_f01_ticket_de_otro_contexto_no_viaja(oms_tmp, monkeypatch) -> None:
    enviados = []

    class _WS:
        async def get_json_checked(self, path, params=None):
            enviados.append(path)
            return {"status": "OK", "order": {"clientId": "1"}}

    monkeypatch.setattr(primary_ws, "get_ws_client", lambda: _WS())
    tok = oms.new_token(_payload())
    assert oms.peek_token(tok)["ctx_version"] == primary_ws.context_version()
    orig = primary_ws._singleton
    primary_ws.set_ws_client(orig)                    # reconexión: sube la versión
    try:
        res = asyncio.run(oms.place(oms.pop_token(tok)))
        assert res["status"] == "RECHAZADA" and "cambió" in res["motivo"] and not enviados
        assert oms.blotter(3)[0]["status"] == "RECHAZADA"
        # un ticket armado en el contexto vigente sigue andando (paper)
        res2 = asyncio.run(oms.place(oms.pop_token(oms.new_token(_payload()))))
        assert res2["status"] == "PAPER"
    finally:
        primary_ws.set_ws_client(orig)


@pytest.mark.asyncio
async def test_f01_cache_de_cuentas_por_contexto(oms_tmp, monkeypatch) -> None:
    monkeypatch.setattr(oms, "configured_comitentes", lambda: [])

    async def a(*args, **kw):
        return {"accounts": [{"id": "CTA_A", "name": "A"}]}

    async def b(*args, **kw):
        return {"accounts": [{"id": "CTA_B", "name": "B"}]}

    monkeypatch.setattr(primary_ws, "get_ws_client", lambda: SimpleNamespace(get_json_checked=a))
    assert (await oms.accounts())[0]["id"] == "CTA_A"
    monkeypatch.setattr(primary_ws, "get_ws_client", lambda: SimpleNamespace(get_json_checked=b))
    assert (await oms.accounts())[0]["id"] == "CTA_A"          # mismo contexto: cache 60 s
    orig = primary_ws._singleton
    primary_ws.set_ws_client(orig)                              # re-login → versión nueva
    try:
        assert (await oms.accounts())[0]["id"] == "CTA_B"
    finally:
        primary_ws.set_ws_client(orig)


# ── F03 · rechazo del broker y resultado desconocido ─────────────────────────
@pytest.mark.asyncio
async def test_f03_rechazo_del_broker_no_es_enviada(oms_tmp, monkeypatch) -> None:
    from backend.services import instruments

    async def _resolve(code, symbol):
        return {"checked": False, "exists": True, "candidates": []}

    class _WS:
        async def get_json_checked(self, path, params=None):
            return {"status": "ERROR", "message": "Saldo insuficiente"}

    monkeypatch.setattr(instruments, "resolve", _resolve)
    monkeypatch.setattr(primary_ws, "get_ws_client", lambda: _WS())
    oms.set_live(True)
    res = await oms.place(_payload())
    assert res["status"] == "RECHAZADA" and "Saldo insuficiente" in res["motivo"]
    assert oms.blotter(3)[0]["status"] == "RECHAZADA (broker)"
    assert not any(a["event"] == "live_respuesta" for a in oms.audit_tail(10))


@pytest.mark.asyncio
async def test_f03_respuesta_perdida_es_desconocida_y_se_reconcilia(oms_tmp, monkeypatch) -> None:
    from backend.services import instruments

    async def _resolve(code, symbol):
        return {"checked": False, "exists": True, "candidates": []}

    class _WS:
        activas = []

        async def get_json_checked(self, path, params=None):
            if path.endswith("newSingleOrder"):
                raise httpx.ReadTimeout("read timeout (sintético)")
            return {"orders": list(self.activas)}

    monkeypatch.setattr(instruments, "resolve", _resolve)
    monkeypatch.setattr(primary_ws, "get_ws_client", lambda: _WS())
    monkeypatch.setattr(oms, "_RECONCILE_DELAYS", (0.01, 0.02))
    oms.set_live(True)
    # a) la orden SÍ entró: aparece entre las activas → estado real
    _WS.activas = [{"instrumentId": {"symbol": "MERV - XMEV - AL30 - 24hs"}, "side": "BUY",
                    "orderQty": 100, "price": 941.0, "status": "NEW", "clientId": "77"}]
    res = await oms.place(_payload())
    assert res["status"] == "DESCONOCIDA" and "PUDO" in res["motivo"]
    await asyncio.gather(*list(oms._followups))
    assert oms.blotter(3)[0]["status"] == "EN MERCADO"
    assert any(a["event"] == "live_desconocida" for a in oms.audit_tail(10))
    # b) no aparece → NO ENTRÓ
    _WS.activas = []
    res = await oms.place(_payload(price=942.0))
    assert res["status"] == "DESCONOCIDA"
    await asyncio.gather(*list(oms._followups))
    assert oms.blotter(3)[0]["status"] == "NO ENTRÓ"
    # c) ConnectError: nunca salió → ERROR limpio, sin reconciliación

    class _WS2:
        async def get_json_checked(self, path, params=None):
            raise httpx.ConnectError("conexión rechazada")

    monkeypatch.setattr(primary_ws, "get_ws_client", lambda: _WS2())
    res = await oms.place(_payload())
    assert res["status"] == "ERROR" and oms.blotter(3)[0]["status"] == "ERROR"


# ── F06 / F12 · sesiones por versión y reset atómico ────────────────────────
async def _login(ac: AsyncClient, user: str, pwd: str):
    return await ac.post("/login", data={"username": user, "password": pwd, "next": "/yas"})


@pytest.mark.asyncio
async def test_f06_cambio_de_clave_cierra_las_otras_sesiones(auth_on) -> None:
    auth.create_user("lucia", "clave-vieja-123", "premium")
    async with _client() as a, _client() as b, _client() as su:
        await _login(a, "lucia", "clave-vieja-123")
        await _login(b, "lucia", "clave-vieja-123")
        assert (await a.get("/market/seq")).status_code == 200
        assert (await b.get("/market/seq")).status_code == 200
        auth.set_password("lucia", "clave-nueva-123")            # reset / cambio de clave
        assert (await a.get("/market/seq")).status_code in (302, 303, 401)   # cookie vieja: afuera
        assert (await b.get("/market/seq")).status_code in (302, 303, 401)
        await _login(a, "lucia", "clave-nueva-123")
        assert (await a.get("/market/seq")).status_code == 200    # login nuevo: adentro
        # "cerrar sesiones" desde /admin: lucia afuera, el superuser sigue
        await _login(su, "su_test", "clave-de-test-2026!")
        r = await su.post("/admin/users/sesiones", data={"username": "lucia"})
        assert r.status_code == 200 and "cerradas" in r.text
        assert (await a.get("/market/seq")).status_code in (302, 303, 401)
        assert (await su.get("/market/seq")).status_code == 200
        # el superuser cierra SUS propias sesiones: la actual sigue viva
        r = await su.post("/admin/users/sesiones", data={"username": "su_test"})
        assert r.status_code == 200 and (await su.get("/market/seq")).status_code == 200


def test_f12_reset_con_token_es_atomico(auth_on) -> None:
    auth.create_user("pedro", "clave-vieja-123", "basico")
    token = auth.make_reset_token("pedro", ttl_seconds=600)
    assert auth.check_reset_token(token) == "pedro"
    barrera = threading.Barrier(2)
    res = {}

    def go(k, pwd):
        barrera.wait()
        try:
            auth.reset_with_token(token, pwd)
            res[k] = "ok"
        except auth.AuthError as exc:
            res[k] = str(exc)

    ts = [threading.Thread(target=go, args=("A", "clave-A-123")), threading.Thread(target=go, args=("B", "clave-B-123"))]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(v == "ok" for v in res.values()) == [False, True], res
    ganador = next(k for k, v in res.items() if v == "ok")
    assert auth.verify_password("pedro", f"clave-{ganador}-123")
    assert auth.check_reset_token(token) is None                 # consumido


# ── F17 · readiness ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_f17_readyz(monkeypatch) -> None:
    from backend.services import bond_universe

    async with _client() as ac:
        r = await ac.get("/readyz")
        assert r.status_code == 200 and r.json()["ready"] is True
        h = (await ac.get("/healthz")).json()
        assert h["status"] == "ok" and h["ready"] is True
        monkeypatch.setattr(bond_universe, "all_codes", lambda: [])
        r = await ac.get("/readyz")
        assert r.status_code == 503 and "vacío" in r.json()["motivo"]
        h = (await ac.get("/healthz")).json()
        assert h["status"] == "ok" and h["ready"] is False
