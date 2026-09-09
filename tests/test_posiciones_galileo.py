"""Fondos GALILEO en Posiciones: composición + PN propios (identifican por
ISIN + descripción, nombre del fondo en la columna `fondo`), CodFondo
namespaceado con GALILEO_OFFSET (su numeración colisiona con la de Delta),
mapeo ISIN → ticker BYMA vía el universo, visibilidad por usuario intacta y
carga best-effort (sin archivos Galileo → todo exactamente igual que antes)."""
from __future__ import annotations

import pandas as pd
import pytest
from httpx import ASGITransport, AsyncClient

from backend.services import bond_universe, positions

G = positions.GALILEO_OFFSET


def _delta_files(d) -> None:
    pd.DataFrame({
        "CodFondo": [5, 18], "Cod_Delta": ["AL30", "TX26"],
        "Especie": ["BONAR 2030", "BONCER 2026"],
        "Cantidad": [1_000_000.0, 2_000_000.0], "Valor": [8.4e8, 1.5e9],
        "Clase de Activo": ["Soberano USD", "CER"],
    }).to_excel(d / "Delta_Composicion.xlsx", sheet_name="Sheet1", index=False)
    pd.DataFrame({"CodFondo": [5, 18], "PN": [5e10, 9e9]}).to_excel(
        d / "Delta_PN.xlsx", sheet_name="Sheet1", index=False)


def _galileo_files(d, isin_local: str) -> None:
    pd.DataFrame({
        "Fecha": ["2026-09-08"] * 3,
        "CodFondo": [5, 5, 2],                       # ¡el 5 colisiona con Delta!
        "fondo": ["GALILEO AHORRO", "GALILEO AHORRO", "GALILEO EVENT DRIVEN"],
        "descripcion": ["Bonar 2030 (local)", "BC Avianca 9.5% 28 01 2031",
                        "BC Petroleos Mexicanos 28 01 2060"],
        "isin": [isin_local, "USG2957NAD33", "US71654QDF63"],
        "cantidad": [300_000.0, 1_500_000.0, 2_000_000.0],
        "valor": [2.5e8, 1.35e6, 1.64e6],
        "Clasifica_Ficha": ["Soberano USD MEP", "Bonos Corporativo USD",
                            "Bonos Corporativo USD"],
    }).to_excel(d / "Galileo_Composicion.xlsx", sheet_name="Sheet1", index=False)
    pd.DataFrame({"CodFondo": [5, 2], "PN": [3.7e10, 2.8e8]}).to_excel(
        d / "Galileo_PN.xlsx", sheet_name="Sheet1", index=False)


def _isin_al30() -> str:
    bond_universe.ensure_loaded()
    isin = getattr(bond_universe.get("AL30"), "isin", None)
    if not isin:
        pytest.skip("AL30 sin ISIN en especies.py")
    return str(isin)


@pytest.fixture()
def carteras(tmp_path, monkeypatch):
    monkeypatch.setenv("DELTA_BASES_DIR", str(tmp_path))
    for env in ("DELTA_COMPOSICION_PATH", "DELTA_PN_PATH",
                "GALILEO_COMPOSICION_PATH", "GALILEO_PN_PATH"):
        monkeypatch.delenv(env, raising=False)
    _delta_files(tmp_path)
    _galileo_files(tmp_path, _isin_al30())
    positions.refresh()
    yield tmp_path
    with positions._lock:
        positions._cache = None       # el próximo test recarga su propio estado


def test_carga_galileo_junto_a_delta(carteras) -> None:
    fs = positions.fondos()
    cods = {f["cod"] for f in fs}
    assert cods == {5, 18, G + 2, G + 5}
    por_cod = {f["cod"]: f for f in fs}
    # labels: Delta intacto; Galileo con prefijo G + nombre de la col `fondo`
    assert por_cod[5]["nombre"] == "5 — Pesos"
    assert por_cod[G + 5]["nombre"] == "G5 — GALILEO AHORRO"
    assert por_cod[G + 2]["nombre"] == "G2 — GALILEO EVENT DRIVEN"
    # PN por familia sin pisarse (el 5 existe en ambas)
    assert por_cod[5]["pn"] == 5e10 and por_cod[G + 5]["pn"] == 3.7e10
    st = positions.status()
    assert st["n_fondos_galileo"] == 2 and st["error"] is None
    assert st["paths"]["galileo"]["composicion"]


def test_isin_local_se_agrega_a_la_posicion(carteras) -> None:
    """Un bono local en la cartera Galileo (identificado por ISIN) se suma a
    la MISMA posición que el de Delta — VN agregado y detalle por fondo."""
    p = positions.position_for("AL30")
    assert p is not None and p["n_fondos"] == 2
    assert p["total_cantidad"] == pytest.approx(1_300_000.0)
    fam = {f["cod_fondo"]: f for f in p["funds"]}
    assert 5 in fam and (G + 5) in fam
    assert fam[G + 5]["pct_pn"] == pytest.approx(2.5e8 / 3.7e10)
    # y entra al universo de la matriz por su ticker BYMA
    assert "AL30" in positions.especies_universe()


def test_isin_internacional_solo_en_vista_fondo(carteras) -> None:
    hs = positions.holdings(G + 2)
    assert len(hs) == 1
    h = hs[0]
    assert h["cod_delta"] is None                      # sin ficha local
    assert h["especie"] == "BC Petroleos Mexicanos 28 01 2060"
    assert h["clase"] == "Bonos Corporativo USD"
    assert h["valor"] == pytest.approx(1.64e6)
    # los ISIN sin mapear no ensucian el universo de especies
    assert all(e and not e.startswith("US") for e in positions.especies_universe())


def test_visibilidad_oculta_galileo_no_tildado(carteras) -> None:
    """Invariante de seguridad: la allowlist vieja de un usuario restringido
    NO incluye los cods namespaceados → los fondos Galileo quedan ocultos
    hasta que el superuser los tilde."""
    assert {f["cod"] for f in positions.fondos(visibles={5, 18})} == {5, 18}
    p = positions.position_for("AL30", visibles={5})
    assert p is not None and p["n_fondos"] == 1
    assert p["total_cantidad"] == pytest.approx(1_000_000.0)   # sólo lo visible
    assert positions.holdings(G + 5, visibles={5}) == []


def test_sin_archivos_galileo_todo_igual(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DELTA_BASES_DIR", str(tmp_path))
    for env in ("DELTA_COMPOSICION_PATH", "DELTA_PN_PATH",
                "GALILEO_COMPOSICION_PATH", "GALILEO_PN_PATH"):
        monkeypatch.delenv(env, raising=False)
    _delta_files(tmp_path)
    try:
        c = positions.refresh()
        assert c["loaded"] and c["error"] is None
        assert {f["cod"] for f in positions.fondos()} == {5, 18}
        assert positions.status()["n_fondos_galileo"] == 0
    finally:
        with positions._lock:
            positions._cache = None


@pytest.mark.asyncio
async def test_http_posiciones_fondo_galileo(carteras) -> None:
    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/posiciones", params={"fondo": G + 5})
        assert r.status_code == 200 and "GALILEO AHORRO" in r.text
        t = await ac.get("/posiciones/table", params={"fondo": G + 5})
        assert t.status_code == 200
