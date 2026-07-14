"""Escenario: defaults vivos (economista / ROFEX / TAMAR), persistencia de
senderos editados, reset, categorías destildadas y patas duales."""
from __future__ import annotations

from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient

from backend.services import escenario as esc
from backend.services import escenario_prefs as prefs


@pytest.fixture()
def prefs_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("ESCENARIO_PREFS_PATH", str(tmp_path / "prefs.json"))
    return tmp_path


def _client() -> AsyncClient:
    from backend.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


# ── persistencia ────────────────────────────────────────────────────────────
def test_prefs_roundtrip_y_reset(prefs_tmp) -> None:
    assert prefs.load() == {}
    prefs.save(senderos={"infl_path": "2,0;1,8"}, cats_off=["dlk", "bonares"])
    got = prefs.load()
    assert got["senderos"] == {"infl_path": "2,0;1,8"}
    assert got["cats_off"] == ["dlk", "bonares"]
    # save parcial: cats_off None no pisa lo guardado
    prefs.save(senderos={"tamar_path": "36,5"})
    got = prefs.load()
    assert got["senderos"] == {"tamar_path": "36,5"}     # senderos se REEMPLAZA
    assert got["cats_off"] == ["dlk", "bonares"]         # cats_off intacto
    # claves desconocidas se descartan (nunca basura al archivo)
    prefs.save(senderos={"infl_path": "1", "hack": "x"})
    assert "hack" not in prefs.load()["senderos"]
    prefs.reset()
    assert prefs.load() == {}


# ── presets nombrados ───────────────────────────────────────────────────────
def test_presets_fotografian_aplican_y_sobreviven_al_reset(prefs_tmp) -> None:
    prefs.save(senderos={"infl_path": "2,0"}, cats_off=["dlk"])
    assert prefs.preset_save("base")
    prefs.save(senderos={"infl_path": "4,0", "a3500_path": "3,0"}, cats_off=[])
    assert prefs.preset_save("estrés deva")
    assert prefs.preset_names() == ["base", "estrés deva"]
    # apply carga el snapshot como estado activo
    assert prefs.preset_apply("base")
    got = prefs.load()
    assert got["senderos"] == {"infl_path": "2,0"} and got["cats_off"] == ["dlk"]
    # reset borra lo ACTIVO pero la biblioteca de presets sobrevive
    prefs.reset()
    got = prefs.load()
    assert got["senderos"] == {} and got["cats_off"] == []
    assert prefs.preset_names() == ["base", "estrés deva"]
    # delete + inexistentes
    assert prefs.preset_delete("base")
    assert not prefs.preset_delete("base")
    assert not prefs.preset_apply("nunca-existió")
    assert not prefs.preset_save("")                    # nombre vacío → rechazo
    assert prefs.preset_names() == ["estrés deva"]


@pytest.mark.asyncio
async def test_preset_endpoint_y_select_en_pagina(prefs_tmp) -> None:
    async with _client() as ac:
        r = await ac.post("/escenario/prefs/preset", json={"action": "save", "name": "base"})
        assert r.status_code == 200 and r.json() == {"ok": True, "presets": ["base"]}
        page = await ac.get("/escenario")
        assert 'value="base"' in page.text              # aparece en el <select> de presets
        r = await ac.post("/escenario/prefs/preset", json={"action": "delete", "name": "base"})
        assert r.json() == {"ok": True, "presets": []}
        r = await ac.post("/escenario/prefs/preset", json={"action": "hack", "name": "x"})
        assert r.json()["ok"] is False


# ── defaults ────────────────────────────────────────────────────────────────
def test_infl_default_alineada_y_extendida(monkeypatch) -> None:
    import indices
    monkeypatch.setattr(indices, "proyeccion_inflacion_mensual",
                        {"Jul-26": 1.8, "Aug-26": 1.6, "Sep-26": 1.4})
    # settle en julio: M1=jul, M2=ago, M3=sep, M4/M5 extienden el último (1,4)
    got = prefs.infl_default(date(2026, 7, 9), 5)
    assert got == "1,80;1,60;1,40;1,40;1,40"


def test_rofex_monthly_interpola_y_extrapola(monkeypatch) -> None:
    from backend.services import futuros
    # Contratos a 30 y 91 días con deva acumulada 2% y 6% (mes 2/3 sin dato →
    # interpola ln-lineal; más allá extrapola con la última pendiente).
    monkeypatch.setattr(futuros, "rows",
                        lambda canal="may", spot_v=None: [
                            {"dias": 30, "td": 0.02}, {"dias": 91, "td": 0.06}])
    out = prefs.rofex_monthly_deva(date(2026, 7, 9), 4)
    assert len(out) == 4
    assert all(v > 0 for v in out)
    assert out[0] == pytest.approx(0.0204, abs=3e-3)      # ~2%/mes el 1er mes
    # acumulada a 3 meses ≈ 6% (el punto de 91 días)
    acum3 = (1 + out[0]) * (1 + out[1]) * (1 + out[2]) - 1
    assert acum3 == pytest.approx(0.06, abs=5e-3)
    assert out[3] == pytest.approx(out[2], rel=0.3)       # extrapola suave


def test_defaults_brecha_constante_y_tamar_flat(monkeypatch) -> None:
    from backend.services import futuros
    monkeypatch.setattr(futuros, "rows",
                        lambda canal="may", spot_v=None: [{"dias": 30, "td": 0.02}])
    d = prefs.defaults(date(2026, 7, 9), 3, tamar_now=36.5, deva_mens_flat=0.02)
    assert d["ccl_path"] == d["a3500_path"] == d["mep_path"]   # brecha/canje constantes
    assert d["tamar_path"] == "36,50;36,50;36,50"              # flat al nivel actual
    assert d["a3500_path"].count(";") == 2                     # 3 meses


def test_defaults_sin_futuros_cae_a_flat(monkeypatch) -> None:
    from backend.services import futuros
    monkeypatch.setattr(futuros, "rows", lambda canal="may", spot_v=None: [])
    d = prefs.defaults(date(2026, 7, 9), 2, tamar_now=None, deva_mens_flat=0.015)
    assert d["a3500_path"] == "1,50;1,50"
    assert d["tamar_path"] == ""                               # sin TAMAR → vacío (serie actual)


# ── duales en el comparativo ────────────────────────────────────────────────
def test_duales_en_categorias_con_pata_correcta() -> None:
    keys = [c.key for c in esc.CATEGORIES]
    assert "dual_tamar_cer" in keys and "dual_cer" in keys
    assert esc.CAT_BY_KEY["dual_tamar_cer"].tamar_leg is True   # pata TAMAR: recibe sendero TAMAR
    assert esc.CAT_BY_KEY["dual_cer"].tamar_leg is False        # pata CER: recibe inflación
    assert esc.CAT_BY_KEY["tamar"].tamar_leg is True
    assert esc.CAT_BY_KEY["dual_tamar_cer"].curve == "dualtamar_cer"
    assert esc.CAT_BY_KEY["dual_cer"].curve == "dualcer"


# ── HTTP: página, endpoints de prefs y skip de categorías ───────────────────
@pytest.mark.asyncio
async def test_pagina_muestra_defaults_duales_y_checkboxes(prefs_tmp) -> None:
    import json as _json
    import re

    async with _client() as ac:
        r = await ac.get("/escenario")
    assert r.status_code == 200
    assert "Dual TAMAR/CER" in r.text and "Dual CER/TAMAR" in r.text
    assert "↺ defaults" in r.text
    assert 'toggleCat' in r.text                              # checkboxes por categoría
    # La config viaja en el <script type="application/json"> y PARSEA — nunca
    # como JSON crudo dentro del atributo x-data (las comillas lo rompían y
    # el grid quedaba vacío).
    assert 'x-data="escSenderosInit()"' in r.text
    m = re.search(r'id="esc-init">(.*?)</script>', r.text, re.S)
    assert m, "falta el <script id=esc-init> con la config"
    cfg = _json.loads(m.group(1))
    assert set(cfg) >= {"n_months", "senderos", "saved_keys", "cats_off"}
    assert set(cfg["senderos"]) == {"infl_path", "a3500_path", "ccl_path", "mep_path", "tamar_path"}


@pytest.mark.asyncio
async def test_prefs_endpoints_guardan_y_resetean(prefs_tmp) -> None:
    async with _client() as ac:
        r = await ac.post("/escenario/prefs",
                          json={"senderos": {"infl_path": "2,5;2,0"}, "cats_off": ["dlk"]})
        assert r.status_code == 200 and r.json()["ok"] is True
        assert prefs.load() == {"senderos": {"infl_path": "2,5;2,0"}, "cats_off": ["dlk"]}
        # la página siguiente muestra lo fijado y la categoría destildada
        page = await ac.get("/escenario")
        assert "2,5;2,0" in page.text
        assert '"dlk"' in page.text                           # cats_off_json
        r = await ac.post("/escenario/prefs/reset")
        assert r.status_code == 200
        assert prefs.load() == {}


@pytest.mark.asyncio
async def test_tabla_saltea_categorias_destildadas(prefs_tmp, monkeypatch) -> None:
    # Sin precios en el store no hay filas que renderizar, así que el skip se
    # verifica en el lugar que importa (eficiencia): las categorías
    # destildadas NI SE PROCESAN (no se piden sus filas de curva).
    from backend.routes import escenario as route

    pedidas: list = []

    async def _spy(cat, plazo):
        pedidas.append(cat.key)
        return []

    monkeypatch.setattr(route, "_cat_rows", _spy)
    async with _client() as ac:
        r = await ac.get("/escenario/table", params={
            "cats_off": "globales,bonares,dlk,dual_tamar_cer,dual_cer",
        })
    assert r.status_code == 200
    assert "globales" not in pedidas and "bonares" not in pedidas
    assert "dual_tamar_cer" not in pedidas and "dual_cer" not in pedidas
    assert "tasa_fija" in pedidas and "tamar" in pedidas      # las prendidas sí
