"""Alertas de precio/TIR — servicio (CRUD + one-shot + mail) y gating superuser.

El store de alertas va a un tmp por test (env ALERTAS_PATH). El valor "actual"
se monkeypatchea a nivel módulo — check_once y la tabla lo toman de ahí, así
no dependemos del feed."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from backend.config import settings
from backend.services import alertas as alertas_svc, auth


@pytest.fixture()
def alertas_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("ALERTAS_PATH", str(tmp_path / "alertas.json"))
    yield


@pytest.fixture()
def auth_on(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "app_users_path", str(tmp_path / "store.json"))
    auth.refresh()
    assert auth.ensure_bootstrapped()["created"]
    yield
    auth.refresh()


def _client() -> AsyncClient:
    from backend.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def _login(ac: AsyncClient, user: str = "rodricor93", pwd: str = "Rc_874562"):
    return await ac.post("/login", data={"username": user, "password": pwd, "next": "/yas"})


# ── Servicio ─────────────────────────────────────────────────────────────────
def test_crud_y_validacion(alertas_tmp):
    # código inexistente / métrica / operador / valor
    assert "desconocido" in alertas_svc.add("ZZZZ99", "precio", ">=", 100.0)
    assert alertas_svc.add("AL30", "volumen", ">=", 100.0) is not None
    assert alertas_svc.add("AL30", "precio", ">", 100.0) is not None
    assert alertas_svc.add("AL30", "precio", ">=", float("nan")) is not None
    # alta válida
    assert alertas_svc.add("al30", "precio", ">=", 1250.5, "yo@x.com") is None
    xs = alertas_svc.list_alertas()
    assert len(xs) == 1 and xs[0]["code"] == "AL30" and xs[0]["activa"]
    assert xs[0]["valor"] == 1250.5 and xs[0]["email"] == "yo@x.com"
    # borrar
    assert alertas_svc.delete(xs[0]["id"])
    assert not alertas_svc.delete("nope")
    assert alertas_svc.list_alertas() == []


def test_check_once_one_shot_y_rearme(alertas_tmp, monkeypatch):
    vals = {("AL30", "precio"): 105.0, ("GD30", "tirea"): 9.8}
    monkeypatch.setattr(alertas_svc, "current_value", lambda c, m: vals.get((c, m)))
    assert alertas_svc.add("AL30", "precio", ">=", 100.0) is None          # cruza (105 ≥ 100)
    assert alertas_svc.add("GD30", "tirea", "<=", 9.0) is None            # no cruza (9,8 > 9)
    assert alertas_svc.check_once() == 1
    por_code = {a["code"]: a for a in alertas_svc.list_alertas()}
    assert not por_code["AL30"]["activa"] and por_code["AL30"]["disparada_valor"] == 105.0
    assert por_code["AL30"]["disparada_at"]
    assert por_code["GD30"]["activa"]
    # one-shot: el mismo cruce no re-dispara
    assert alertas_svc.check_once() == 0
    # re-arme manual → vuelve a vigilar y re-dispara
    assert alertas_svc.rearm(por_code["AL30"]["id"])
    assert alertas_svc.check_once() == 1


def test_check_sin_dato_no_dispara(alertas_tmp, monkeypatch):
    monkeypatch.setattr(alertas_svc, "current_value", lambda c, m: None)
    assert alertas_svc.add("AL30", "precio", ">=", 1.0) is None
    assert alertas_svc.check_once() == 0
    assert alertas_svc.list_alertas()[0]["activa"]


def test_mail_al_disparar(alertas_tmp, monkeypatch):
    from backend.services import mailer
    sent = []
    monkeypatch.setattr(mailer, "is_configured", lambda: True)
    monkeypatch.setattr(mailer, "send", lambda to, s, b: (sent.append((to, s, b)) or (True, "ok")))
    monkeypatch.setattr(alertas_svc, "current_value", lambda c, m: 12.5)
    assert alertas_svc.add("AL30", "tirea", ">=", 12.0, "trader@delta.com") is None
    assert alertas_svc.add("GD30", "tirea", ">=", 12.0) is None            # sin mail → sólo visual
    assert alertas_svc.check_once() == 2
    assert len(sent) == 1
    to, subject, body = sent[0]
    assert to == "trader@delta.com" and "AL30" in subject and "12,50" in subject
    assert "TIREA" in body and "12,50%" in body


# ── HTTP + gating ────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_pagina_y_crud_superuser(alertas_tmp, auth_on, monkeypatch):
    monkeypatch.setattr(alertas_svc, "current_value", lambda c, m: 104.25)
    async with _client() as ac:
        await _login(ac)
        pg = await ac.get("/alertas")
        assert pg.status_code == 200 and "Alertas de precio / TIR" in pg.text
        # crear (valor es-AR con coma) → la tabla vuelve con la alerta y el actual
        r = await ac.post("/alertas/crear", data={"code": "al30", "metric": "precio",
                                                  "op": ">=", "valor": "1.250,50", "email": ""})
        assert r.status_code == 200 and "AL30" in r.text and "vigilando" in r.text
        assert "1.250,50" in r.text and "104,25" in r.text
        # valor ilegible → error es-AR, no crea
        r = await ac.post("/alertas/crear", data={"code": "AL30", "metric": "precio",
                                                  "op": ">=", "valor": "abc"})
        assert "Valor inválido" in r.text
        # borrar
        aid = alertas_svc.list_alertas()[0]["id"]
        r = await ac.post("/alertas/borrar", data={"id": aid})
        assert r.status_code == 200 and "Sin alertas" in r.text


@pytest.mark.asyncio
async def test_alertas_solo_superuser(alertas_tmp, auth_on):
    async with _client() as su:
        await _login(su)
        await su.post("/admin/users", data={"username": "prem", "password": "clave123", "role": "premium"})
        y = await su.get("/yas")
        assert ">Alertas<" in y.text                       # superuser la ve en la nav
    async with _client() as ac:
        await _login(ac, "prem", "clave123")
        assert (await ac.get("/alertas")).status_code == 403
        assert (await ac.get("/alertas/tabla")).status_code == 403
        r = await ac.post("/alertas/crear", data={"code": "AL30", "metric": "precio",
                                                  "op": ">=", "valor": "1"})
        assert r.status_code == 403
        y = await ac.get("/yas")
        assert y.status_code == 200 and ">Alertas<" not in y.text   # ni el link
