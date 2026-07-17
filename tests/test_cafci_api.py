"""API CAFCI (fase B0): VCP de fondos propios, gating superuser y
normalización defensiva del vector (preparada para la fase B1)."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from backend.config import settings
from backend.services import auth, cafci_api


@pytest.fixture(autouse=True)
def _limpio(monkeypatch):
    """Snapshot y token limpios en cada test (no contaminar test_cafci.py)."""
    monkeypatch.delenv("CAFCI_TOKEN", raising=False)
    monkeypatch.delenv("CAFCI_FONDOS", raising=False)
    with cafci_api._lock:
        cafci_api._snap.update({"funds": [], "funds_fecha": None, "rows": [],
                                "fecha": None, "n": 0, "ts": 0.0,
                                "error": None, "auth_error": False})
    yield
    with cafci_api._lock:
        cafci_api._snap.update({"funds": [], "funds_fecha": None,
                                "error": None, "auth_error": False})


class _Resp:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def test_refresh_daily_divide_vcp_y_respeta_orden(monkeypatch) -> None:
    monkeypatch.setenv("CAFCI_TOKEN", "Bearer test")
    monkeypatch.setenv("CAFCI_FONDOS", "Delta Renta - Clase A;Delta Acciones - Clase A")
    records = [
        {"nombreDeLaClaseDeFondo": "Delta Acciones - Clase A", "fecha": "2026-07-16",
         "vcp": "12345678", "moneda": "$"},
        {"nombreDeLaClaseDeFondo": "Delta Renta - Clase A", "fecha": "2026-07-16",
         "vcp": 4567890.0, "moneda": "$"},
        {"nombreDeLaClaseDeFondo": "Otro Fondo Ajeno", "fecha": "2026-07-16",
         "vcp": "1", "moneda": "$"},
    ]
    monkeypatch.setattr(cafci_api, "_get", lambda p, params=None: {"records": records})
    assert cafci_api.refresh() is True
    fondos, fecha, error = cafci_api.funds()
    assert error is None and fecha == "16/07/2026"
    assert [f["nombre"] for f in fondos] == ["Delta Renta - Clase A", "Delta Acciones - Clase A"]
    assert fondos[0]["vcp"] == pytest.approx(4567.890)      # ÷1000
    assert fondos[1]["vcp"] == pytest.approx(12345.678)
    assert "Otro Fondo Ajeno" not in {f["nombre"] for f in fondos}


def test_sin_token_deshabilitado() -> None:
    assert not cafci_api.enabled()
    assert cafci_api.refresh() is False
    assert cafci_api.status()["enabled"] is False


def test_auth_401_marca_token_vencido(monkeypatch) -> None:
    monkeypatch.setenv("CAFCI_TOKEN", "Bearer vencido")
    import requests
    monkeypatch.setattr(requests, "get",
                        lambda *a, **k: _Resp(401, None, '{"message":"jwt expired"}'))
    assert cafci_api.refresh() is False
    st = cafci_api.status()
    assert st["auth_error"] and "vencido" in st["error"]


def test_auth_header_normaliza_bearer(monkeypatch) -> None:
    monkeypatch.setenv("CAFCI_TOKEN", "eyJsintoken")
    assert cafci_api._auth()["Authorization"] == "Bearer eyJsintoken"
    monkeypatch.setenv("CAFCI_TOKEN", "Bearer eyJcontoken")
    assert cafci_api._auth()["Authorization"] == "Bearer eyJcontoken"


def test_normalize_precio_defensiva() -> None:
    """B1 preparada: alias con acentos/case + números es-AR string; sin
    identificador → descartada."""
    row = cafci_api._normalize_precio({
        "Código": "12345", "ISIN": "ARARGE1234", "Precio": "1.234,56",
        "Moneda": "$", "TIR": "12,5",
    })
    assert row is not None
    assert row["cafci"] == "12345" and row["isin"] == "ARARGE1234"
    assert row["cdo"] == pytest.approx(1234.56)
    assert row["tir"] == pytest.approx(12.5)
    assert "ararge1234" in row["_key"] and "12345" in row["_key"]
    assert cafci_api._normalize_precio({"Precio": "10,0"}) is None    # sin id


# ── HTTP + gating superuser ─────────────────────────────────────────────────
def _client() -> AsyncClient:
    from backend.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.asyncio
async def test_panel_fondos_renderiza(monkeypatch) -> None:
    monkeypatch.setenv("CAFCI_TOKEN", "Bearer test")
    with cafci_api._lock:
        cafci_api._snap["funds"] = [{"nombre": "Delta Renta - Clase A", "vcp": 4567.890123,
                                     "moneda": "$", "fecha": "16/07/2026"}]
        cafci_api._snap["funds_fecha"] = "16/07/2026"
    async with _client() as ac:
        r = await ac.get("/cafci/fondos")
        assert r.status_code == 200
        assert "Fondos propios" in r.text and "Delta Renta - Clase A" in r.text
        assert "4.567,890123" in r.text
        # sin auth (dev = superuser) la página trae el div lazy
        page = await ac.get("/cafci")
        assert 'id="cafci-fondos"' in page.text


@pytest.mark.asyncio
async def test_panel_sin_token_vacio() -> None:
    async with _client() as ac:
        r = await ac.get("/cafci/fondos")
        assert r.status_code == 200 and "Fondos propios" not in r.text


@pytest.mark.asyncio
async def test_fondos_solo_superuser(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "app_users_path", str(tmp_path / "store.json"))
    auth.refresh()
    assert auth.ensure_bootstrapped()["created"]
    async with _client() as su:
        await su.post("/login", data={"username": "rodricor93", "password": "Rc_874562", "next": "/yas"})
        await su.post("/admin/users", data={"username": "prem", "password": "clave123", "role": "premium"})
        assert (await su.get("/cafci/fondos")).status_code == 200
        assert 'id="cafci-fondos"' in (await su.get("/cafci")).text
    async with _client() as ac:
        await ac.post("/login", data={"username": "prem", "password": "clave123", "next": "/yas"})
        assert (await ac.get("/cafci/fondos")).status_code == 403       # endpoint gateado
        page = await ac.get("/cafci")
        assert page.status_code == 200                                  # la pestaña sigue global
        assert 'id="cafci-fondos"' not in page.text                     # sin div lazy
    auth.refresh()
