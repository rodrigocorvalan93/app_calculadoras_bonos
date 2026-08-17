"""Visibilidad de FONDOS por usuario (superuser la administra desde /admin).

None = ve todos (default de siempre); lista = allowlist de cod_fondo. El
filtro corre server-side en services.positions (param `visibles`) y entra por
auth.visible_fondos_for(request) en Posiciones/Matriz y en los desplegables
de tenencia (YAS/Comparador/Curvas). Acá se cubre: el service (filtrado +
totales recalculados), la persistencia en auth, y el HTTP de punta a punta
(un básico restringido no ve el fondo ajeno ni con ?fondo= a mano).
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from backend.config import settings
from backend.services import auth, positions


# ── Fixtures ────────────────────────────────────────────────────────────────
@pytest.fixture()
def carteras(monkeypatch):
    """Cache de positions inyectado (CI-safe, sin Excel): 2 fondos.
    El fondo 20 tiene GD30 y TX26; el 30 tiene GD30 y AL30."""
    holdings = [
        {"cod_fondo": 20, "cod_delta": "GD30", "especie": "GD30", "cantidad": 100.0,
         "valor": 80000.0, "clase": "Títulos Públicos"},
        {"cod_fondo": 20, "cod_delta": "TX26", "especie": "TX26", "cantidad": 50.0,
         "valor": 20000.0, "clase": "Títulos Públicos"},
        {"cod_fondo": 30, "cod_delta": "GD30", "especie": "GD30", "cantidad": 10.0,
         "valor": 8000.0, "clase": "Títulos Públicos"},
        {"cod_fondo": 30, "cod_delta": "AL30", "especie": "AL30", "cantidad": 5.0,
         "valor": 4000.0, "clase": "Títulos Públicos"},
    ]
    by_code = {}
    for h in holdings:
        agg = by_code.setdefault(h["cod_delta"], {
            "especie": h["especie"], "total_cantidad": 0.0, "total_valor": 0.0, "funds": []})
        agg["total_cantidad"] += h["cantidad"]
        agg["total_valor"] += h["valor"]
        agg["funds"].append({"cod_fondo": h["cod_fondo"], "cantidad": h["cantidad"],
                             "valor": h["valor"]})
    cache = {"loaded": True, "error": None, "holdings": holdings,
             "pn": {20: 1_000_000.0, 30: 500_000.0}, "fondos": {20: "Ahorro", 30: "Renta"},
             "paths": {}, "asof": None, "by_code": by_code}
    monkeypatch.setattr(positions, "_cache", cache)
    yield cache
    # monkeypatch restaura _cache solo


@pytest.fixture()
def auth_on(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "app_users_path", str(tmp_path / "store.json"))
    auth.refresh()
    auth.ensure_bootstrapped()
    yield
    auth.refresh()


def _client() -> AsyncClient:
    from backend.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


async def _login(ac: AsyncClient, user: str, pwd: str):
    return await ac.post("/login", data={"username": user, "password": pwd, "next": "/yas"})


# ── Service: filtrado ───────────────────────────────────────────────────────
def test_fondos_y_holdings_filtran(carteras):
    assert [f["cod"] for f in positions.fondos()] == [20, 30]
    assert [f["cod"] for f in positions.fondos({20})] == [20]
    assert positions.holdings(30) and positions.holdings(30, {20}) == []
    assert len(positions.holdings(20, {20})) == 2


def test_position_for_recalcula_totales(carteras):
    todo = positions.position_for("GD30")
    assert todo["n_fondos"] == 2 and todo["total_valor"] == pytest.approx(88000.0)
    solo20 = positions.position_for("GD30", {20})
    assert solo20["n_fondos"] == 1 and solo20["total_valor"] == pytest.approx(80000.0)
    assert solo20["total_cantidad"] == pytest.approx(100.0)
    assert all(f["cod_fondo"] == 20 for f in solo20["funds"])
    # el papel que SÓLO está en un fondo oculto no existe para el usuario
    assert positions.position_for("AL30", {20}) is None
    assert positions.position_for("AL30") is not None


# ── Auth: persistencia + defaults ───────────────────────────────────────────
def test_auth_visible_fondos_roundtrip(auth_on):
    auth.create_user("jrivas", "clave123", "basico")
    assert auth.visible_fondos("jrivas") is None            # default: todos
    auth.set_visible_fondos("jrivas", [20])
    assert auth.visible_fondos("jrivas") == frozenset({20})
    # el reset de contraseña NO pisa la restricción
    auth.set_password("jrivas", "otraclave9")
    assert auth.visible_fondos("jrivas") == frozenset({20})
    # lista vacía = no ve ninguna cartera (distinto de None)
    auth.set_visible_fondos("jrivas", [])
    assert auth.visible_fondos("jrivas") == frozenset()
    auth.set_visible_fondos("jrivas", None)                 # volver a todos
    assert auth.visible_fondos("jrivas") is None
    # el superuser no se restringe
    su = next(u["username"] for u in auth.list_users() if u["role"] == "superuser")
    with pytest.raises(auth.AuthError):
        auth.set_visible_fondos(su, [20])
    assert auth.visible_fondos(su) is None


# ── HTTP end-to-end ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_restringido_no_ve_fondo_ajeno(auth_on, carteras):
    async with _client() as su:
        await _login(su, "rodricor93", "Rc_874562")
        await su.post("/admin/users", data={"username": "jrivas", "password": "clave123",
                                            "role": "premium"})
        # restringir vía el endpoint del panel (form: sin `todos`, cod=20)
        r = await su.post("/admin/users/fondos", data={"username": "jrivas", "cod": "20"})
        assert r.status_code == 200 and "jrivas" in r.text
        # el superuser sigue viendo TODO en su propia sesión
        r = await su.get("/posiciones")
        assert "Renta" in r.text
    assert auth.visible_fondos("jrivas") == frozenset({20})

    async with _client() as ac:
        await _login(ac, "jrivas", "clave123")
        # página: el selector no ofrece el fondo 30 (nombre "Renta" no aparece)
        r = await ac.get("/posiciones")
        assert r.status_code == 200 and "Ahorro" in r.text and "Renta" not in r.text
        # URL-hack: pedir el fondo oculto a mano → panel vacío, sin tenencias
        r = await ac.get("/posiciones/table?fondo=30")
        assert r.status_code == 200 and "AL30" not in r.text and "Renta" not in r.text
        r = await ac.get("/posiciones/targets?fondo=30")
        assert r.status_code == 200 and "Renta" not in r.text
        # matriz: ni columna del fondo 30 ni la especie que SÓLO él tiene
        r = await ac.get("/matriz/table")
        assert r.status_code == 200 and "Renta" not in r.text and "AL30" not in r.text
        assert "GD30" in r.text                       # lo compartido sigue (fila del 20)


@pytest.mark.asyncio
async def test_yas_tenencia_filtrada(auth_on, carteras):
    """El desplegable de tenencia del YAS recalcula totales con lo visible: el
    restringido ve SU fondo y no la posición agregada del desk."""
    async with _client() as su:
        await _login(su, "rodricor93", "Rc_874562")
        await su.post("/admin/users", data={"username": "jrivas", "password": "clave123",
                                            "role": "premium"})
        await su.post("/admin/users/fondos", data={"username": "jrivas", "cod": "20"})
    async with _client() as ac:
        await _login(ac, "jrivas", "clave123")
        r = await ac.post("/yas/recompute", data={"code": "GD30", "mode": "precio",
                                                  "value": "80"})
        # la tenencia del fondo oculto (30 — "Renta") no aparece en el resultado
        assert r.status_code == 200 and "Renta" not in r.text


@pytest.mark.asyncio
async def test_admin_todos_restaura(auth_on, carteras):
    async with _client() as su:
        await _login(su, "rodricor93", "Rc_874562")
        await su.post("/admin/users", data={"username": "jrivas", "password": "clave123",
                                            "role": "basico"})
        await su.post("/admin/users/fondos", data={"username": "jrivas", "cod": "20"})
        assert auth.visible_fondos("jrivas") == frozenset({20})
        await su.post("/admin/users/fondos", data={"username": "jrivas", "todos": "1"})
        assert auth.visible_fondos("jrivas") is None
        # sin `todos` y sin `cod` → no ve ninguna cartera
        await su.post("/admin/users/fondos", data={"username": "jrivas"})
        assert auth.visible_fondos("jrivas") == frozenset()
