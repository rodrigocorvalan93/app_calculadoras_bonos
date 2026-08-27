"""Profesionalización: visor de auditoría + salud de datos en /admin, y la
confirmación reforzada de órdenes en modo LIVE (retipear el nominal).

Todo corre con el muro PRENDIDO (superuser logueado): son superficies
superuser-only y el flujo de órdenes registra QUIÉN hizo cada cosa."""
from __future__ import annotations

import re

import pytest
from httpx import ASGITransport, AsyncClient

from backend.config import settings
from backend.services import auth, oms

SU, PW = "rodricor93", "Rc_874562"


@pytest.fixture()
def entorno(tmp_path, monkeypatch):
    """Muro prendido + store de usuarios fresco + audit en tmp + validate
    permisivo (acá se prueba el FLUJO, no el pre-trade, que tiene sus tests)."""
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "app_users_path", str(tmp_path / "store.json"))
    auth.refresh()
    assert auth.ensure_bootstrapped()["created"]
    monkeypatch.setattr(oms, "_AUDIT_PATH", tmp_path / "audit.jsonl")
    monkeypatch.setattr(oms, "validate", lambda *a, **k: None)
    yield tmp_path
    auth.refresh()


def _client() -> AsyncClient:
    from backend.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def _su(ac: AsyncClient) -> None:
    r = await ac.post("/login", data={"username": SU, "password": PW, "next": "/yas"})
    assert r.status_code in (302, 303)


def _token_de(html: str) -> str:
    m = re.search(r'name="token" value="([0-9a-f]+)"', html)
    assert m, "no vino el token de confirmación"
    return m.group(1)


@pytest.mark.asyncio
async def test_flujo_paper_registra_usuario(entorno) -> None:
    async with _client() as ac:
        await _su(ac)
        r = await ac.post("/ordenes/ticket", data={
            "code": "GD30", "side": "buy", "ordtype": "limit", "qty": "1000",
            "price": "65,00", "account": "999", "plazo": "24hs"})
        assert r.status_code == 200
        r2 = await ac.post("/ordenes/confirmar", data={"token": _token_de(r.text)})
        assert r2.status_code == 200
    evs = {rec["event"]: rec for rec in oms.audit_tail(10)}
    assert "ticket" in evs and "paper_enviada" in evs
    assert evs["ticket"].get("user") == SU            # quién armó
    assert evs["paper_enviada"].get("user") == SU


@pytest.mark.asyncio
async def test_confirmacion_live_exige_retipear_el_nominal(entorno, monkeypatch) -> None:
    monkeypatch.setitem(oms._live_override, "v", True)
    async with _client() as ac:
        await _su(ac)
        r = await ac.post("/ordenes/ticket", data={
            "code": "GD30", "side": "buy", "ordtype": "limit", "qty": "1000000",
            "price": "65,00", "account": "999", "plazo": "24hs"})
        tok = _token_de(r.text)
        # la card LIVE trae el campo de retipeo
        assert 'name="confirm_live"' in r.text
        # mal tipeado → error y el token NO se quema (no hay que rearmar)
        r2 = await ac.post("/ordenes/confirmar",
                           data={"token": tok, "confirm_live": "999"})
        assert "reescrib" in r2.text.lower()
        assert oms.peek_token(tok) is not None
        # bien tipeado (formato es-AR tolerado) → pasa el gate y consume el token
        r3 = await ac.post("/ordenes/confirmar",
                           data={"token": tok, "confirm_live": "1.000.000"})
        assert r3.status_code == 200 and "reescrib" not in r3.text.lower()
        assert oms.peek_token(tok) is None
    # el intento LIVE quedó auditado (enviando; sin broker en tests → error después)
    evs = [rec["event"] for rec in oms.audit_tail(20)]
    assert "live_enviando" in evs


@pytest.mark.asyncio
async def test_admin_salud_y_visor_auditoria(entorno) -> None:
    oms.audit("ticket", {"code": "GD30", "side": "buy", "qty": 1, "user": "rodri"})
    oms.audit("paper_enviada", {"code": "AL30", "side": "sell", "qty": 2, "user": "jose"})
    async with _client() as ac:
        await _su(ac)
        s = await ac.get("/admin/salud")
        assert s.status_code == 200
        assert "Feed broker" in s.text and "Seq-cache" in s.text and "OMS" in s.text
        a = await ac.get("/admin/auditoria", params={"q": "al30"})
        assert a.status_code == 200 and "AL30" in a.text and "GD30" not in a.text
        c = await ac.get("/admin/auditoria.csv", params={"evento": "paper"})
        assert c.status_code == 200
        assert "AL30" in c.text and "GD30" not in c.text
        assert c.headers["content-disposition"].startswith("attachment")
        # sin login ni rol → afuera
        async with _client() as anon:
            assert (await anon.get("/admin/salud")).status_code in (302, 403)
