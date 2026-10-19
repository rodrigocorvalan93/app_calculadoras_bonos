"""Add-in de Excel con las patas calculadas en minúscula (15/10).

`OMS.TIREA("TMVE8v"; …)` / `OMS.MARGEN("TXMD8v"; …)` daban #N/A con "Bono
'TMVE8V' no encontrado": functions.js (también el que cada Excel tiene
cacheado) y `_calc_batch` suben el código a mayúsculas, y las fichas
calculadas llevan sufijo en minúscula — `…v` = pata TAMAR de los duales,
`…j` = CER proyectado. El server resuelve ahora el código contra el universo
sin distinguir mayúsculas (`bond_universe.resolve`), así anda sin reinstalar
el add-in."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from backend.config import settings


def test_resolve_sin_distinguir_mayusculas() -> None:
    from backend.services import bond_universe

    bond_universe.ensure_loaded()
    for tipeado, ficha in (("TMVE8v", "TMVE8v"), ("TMVE8V", "TMVE8v"), ("tmve8v", "TMVE8v"),
                           ("TXMD8V", "TXMD8v"), ("TXMD8J", "TXMD8j"), (" gd30 ", "GD30"),
                           ("TXMD8", "TXMD8")):
        assert bond_universe.resolve(tipeado) == ficha, tipeado
    assert bond_universe.resolve("NOEXISTE") is None
    assert bond_universe.resolve("") is None and bond_universe.resolve(None) is None
    # TODAS las fichas con minúscula (patas j / v) se encuentran desde su forma
    # en mayúsculas, que es lo que manda el add-in
    con_minuscula = [c for c in bond_universe.all_codes() if c != c.upper()]
    assert len(con_minuscula) > 20
    assert all(bond_universe.resolve(c.upper()) == c for c in con_minuscula)


def test_codigos_que_chocan_en_mayusculas_no_se_adivinan() -> None:
    """Si algún día dos fichas difieren sólo en mayúsculas, ninguna se resuelve
    por la vía insensible (la exacta sigue andando): nunca se elige una al azar."""
    from backend.services import bond_universe

    assert bond_universe._upper_map(["AB", "ab", "CDv"]) == {"CDV": "CDv"}


@pytest.mark.asyncio
async def test_tir_margen_y_ficha_de_las_patas_desde_el_addin(tmp_path, monkeypatch) -> None:
    from backend.main import app
    from backend.services import auth, bond_universe, marketdata_store, pricing, symbols as syms

    bond_universe.ensure_loaded()
    settle = pricing.settlement_date_str("24hs")

    def directo(code: str, px: float) -> dict:
        m = pricing.compute_metrics(code, "precio", px, settle=settle, include_cashflows=False)
        assert not m.get("error"), m
        return m

    tmve8v, txmd8v, txmd8j = directo("TMVE8v", 150_000.0), directo("TXMD8v", 100.0), directo("TXMD8j", 100.0)
    assert tmve8v["margen_tna"] is not None and txmd8v["margen_tna"] is not None
    # precio de mercado por default: la pata v cotiza con el ticker base (TXMD8)
    marketdata_store.get_store().update_from_md(syms.md_symbol("TXMD8v", "24hs"), {"LA": {"price": 101.5}})
    assert syms.md_symbol("TXMD8v", "24hs") == syms.md_symbol("TXMD8", "24hs")
    mercado = directo("TXMD8v", 101.5)

    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "app_users_path", str(tmp_path / "store.json"))
    auth.refresh()
    auth.ensure_bootstrapped()
    try:
        auth.create_user("mesa_duales", "clave123", "basico")
        tok = auth.set_excel_access("mesa_duales", True)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            # tal cual lo manda functions.js: código en MAYÚSCULAS
            r = await ac.post("/excel/v1/calc", headers={"X-OMS-Token": tok}, json={"items": [
                {"code": "TMVE8V", "modo": "precio", "valor": 150_000.0, "plazo": "24hs"},   # OMS.TIREA / OMS.MARGEN
                {"code": "TXMD8V", "modo": "precio", "valor": 100.0, "plazo": "24hs"},
                {"code": "txmd8v", "modo": "precio", "valor": 100.0, "plazo": "24hs"},
                {"code": "TXMD8J", "modo": "precio", "valor": 100.0, "plazo": "24hs"},       # pata CER proyectada
                {"code": "TXMD8V", "modo": "precio", "plazo": "24hs"},                       # sin precio → mercado
                {"code": "TMVE8V", "tipo": "meta"},                                          # OMS.VENCIMIENTO
                {"code": "noexiste", "modo": "precio", "valor": 100.0, "plazo": "24hs"},
            ]})
        assert r.status_code == 200
        res = r.json()["results"]
        for i in range(6):
            assert "error" not in res[i], (i, res[i])
        assert res[0]["codigo"] == "TMVE8v"
        assert res[0]["tirea"] == pytest.approx(tmve8v["tirea"]) and res[0]["margen_tna"] == pytest.approx(tmve8v["margen_tna"])
        assert res[1]["codigo"] == res[2]["codigo"] == "TXMD8v"
        assert res[1]["margen_tna"] == pytest.approx(txmd8v["margen_tna"]) and res[2]["tirea"] == pytest.approx(txmd8v["tirea"])
        assert res[3]["codigo"] == "TXMD8j" and res[3]["tirea"] == pytest.approx(txmd8j["tirea"])
        assert res[4]["margen_tna"] == pytest.approx(mercado["margen_tna"])
        assert res[5]["codigo"] == "TMVE8v" and res[5]["vencimiento"] == "2028-01-28"
        # un código que no existe sigue saliendo en mayúsculas en el error, como antes
        assert "NOEXISTE" in res[6]["error"]
    finally:
        auth.refresh()
