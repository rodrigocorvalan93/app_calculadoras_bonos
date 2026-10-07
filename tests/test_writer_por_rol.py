"""Writer por rol (07/10): una instancia escribe la base compartida sólo si HOY
la usó un usuario con la feature `base_writer` — superuser siempre, premium
por default, básico nunca. `HISTORICO_BASE_WRITER` sigue siendo el máster y la
captura headless (tools/cierre.py) decide por él."""
from __future__ import annotations

import json
import time

import pytest

from backend.config import settings
from backend.services import auth, bond_universe, cierres, historico_writer as hw
from tests.test_cierre_reconstruccion import env  # noqa: F401 — fixture (carpeta de bases tmp)
from tests.test_historico_writer import _client, auth_on  # noqa: F401

# ruff: noqa: F811 — los fixtures importados se piden por nombre como parámetro (patrón pytest)

_SU = {"username": "su_test", "password": "clave-de-test-2026!", "next": "/yas"}


@pytest.fixture(autouse=True)
def _sin_presencia(monkeypatch):
    auth._VISTOS.clear()
    monkeypatch.setattr(hw, "_WRITER_HEADLESS", False)
    yield
    auth._VISTOS.clear()


def test_feature_base_writer_default_premium_si_basico_no(auth_on) -> None:
    assert "base_writer" in dict(auth.FEATURES)
    assert auth.can_feature("superuser", "base_writer")
    assert auth.can_feature("premium", "base_writer")
    assert not auth.can_feature("basico", "base_writer")
    # el superuser la destilda para premium y queda destildada aun releyendo el store
    auth.set_role_features("premium", [])
    assert not auth.can_feature("premium", "base_writer")
    auth.refresh()
    assert not auth.can_feature("premium", "base_writer")


def test_store_viejo_recibe_el_default_una_sola_vez(tmp_path, monkeypatch) -> None:
    p = tmp_path / "store.json"
    p.write_text(json.dumps({"users": {}, "role_tabs": {}, "role_features": {"premium": ["cafci_fondos"]}}),
                 encoding="utf-8")
    monkeypatch.setattr(settings, "app_users_path", str(p))
    auth.refresh()
    assert auth.features_for("premium") == frozenset({"cafci_fondos", "base_writer"})
    assert auth.features_for("basico") == frozenset()
    auth.set_role_features("premium", ["cafci_fondos"])          # el superuser la saca…
    auth.refresh()
    assert auth.features_for("premium") == frozenset({"cafci_fondos"})     # …y no vuelve sola
    assert "base_writer" in json.loads(p.read_text(encoding="utf-8"))["features_default_ok"]


def test_writer_estado_por_flag_login_y_presencia(auth_on, monkeypatch) -> None:
    monkeypatch.setattr(settings, "historico_base_writer", False)
    e = hw.writer_estado()
    assert e["writer"] is False and e["motivo"] == "base_writer=0"
    monkeypatch.setattr(settings, "historico_base_writer", True)
    # muro puesto y nadie entró todavía → esta instancia sólo journalea
    e = hw.writer_estado()
    assert e["writer"] is False and "sin superuser ni premium" in e["motivo"] and not hw.es_writer()
    # un básico no alcanza
    auth.create_user("juan", "clave123", "basico")
    auth.marcar_visto("juan")
    assert not hw.es_writer()
    # un premium sí (default); si el superuser le saca la feature, deja de alcanzar al instante
    auth.create_user("ana", "clave123", "premium")
    auth.marcar_visto("ana")
    e = hw.writer_estado()
    assert e["writer"] is True and e["usuario"] == "ana" and "premium" in e["motivo"]
    auth.set_role_features("premium", [])
    assert not hw.es_writer()
    # el superuser siempre
    auth.marcar_visto("su_test")
    assert hw.writer_estado()["usuario"] == "su_test"
    # visto AYER no cuenta
    auth._VISTOS["su_test"] = time.time() - 36 * 3600
    assert not hw.es_writer() and "su_test" not in auth.vistos_hoy()
    # captura headless: decide el flag, no la presencia
    monkeypatch.setattr(hw, "_WRITER_HEADLESS", True)
    assert hw.es_writer() and "headless" in hw.writer_estado()["motivo"]
    # sin muro de login todo request es superuser → writer (dev / suite)
    monkeypatch.setattr(hw, "_WRITER_HEADLESS", False)
    monkeypatch.setattr(settings, "auth_enabled", False)
    assert hw.es_writer()


def test_estado_cierre_consolidacion_e_importar_base_sin_writer(env, auth_on, monkeypatch) -> None:
    monkeypatch.setattr(settings, "historico_base_writer", True)
    e = hw.estado_cierre()
    assert e["writer"] is False and "sin superuser ni premium" in e["writer_motivo"]
    assert cierres.importar_base()["skipped"] == e["writer_motivo"]
    assert hw.consolidar_journal() is None
    auth.marcar_visto("su_test")
    e = hw.estado_cierre()
    assert e["writer"] is True and "su_test" in e["writer_motivo"]
    assert cierres.importar_base()["skipped"] == "sin espejo parquet de la base"      # ya pasó el gate de writer


@pytest.mark.asyncio
async def test_el_middleware_marca_presencia_cookie_y_token_excel(auth_on, monkeypatch) -> None:
    monkeypatch.setattr(settings, "historico_base_writer", True)
    bond_universe.ensure_loaded()
    async with _client() as su:
        r = await su.post("/login", data=_SU)
        assert r.status_code in (200, 303)
        r = await su.post("/admin/users", data={"username": "juan", "password": "clave123",
                                                "role": "basico", "email": ""})
        assert r.status_code < 400, r.text[:200]
        r = await su.get("/admin")
        assert r.status_code == 200 and "Escribe la base histórica compartida" in r.text
    auth._VISTOS.clear()                                   # arrancamos de cero: ¿quién usa la instancia?
    async with _client() as ac:
        r = await ac.post("/login", data={"username": "juan", "password": "clave123", "next": "/yas"})
        assert r.status_code in (200, 303)
        assert (await ac.get("/yas")).status_code == 200
    assert "juan" in auth.vistos_hoy() and not hw.es_writer()           # básico: la instancia no escribe
    async with _client() as su:
        r = await su.post("/login", data=_SU)
        assert r.status_code in (200, 303)
        assert (await su.get("/yas")).status_code == 200
    assert hw.writer_estado()["usuario"] == "su_test"
    # el add-in de Excel (token por usuario) también cuenta como uso de la instancia
    auth._VISTOS.clear()
    auth.set_excel_access("su_test", True)
    token = next(u["excel_token"] for u in auth.list_users() if u["username"] == "su_test")
    async with _client() as ac:
        r = await ac.get("/excel/v1/snapshot?codes=TX26", headers={"x-oms-token": token})
        assert r.status_code == 200
    assert hw.writer_estado()["usuario"] == "su_test"
