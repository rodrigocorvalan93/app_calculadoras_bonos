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
    assert prefs.load_user("_local")["senderos"] == {}
    prefs.save(senderos={"infl_path": "2,0;1,8"}, cats_off=["dlk", "bonares"])
    got = prefs.load_user("_local")
    assert got["senderos"] == {"infl_path": "2,0;1,8"}
    assert got["cats_off"] == ["dlk", "bonares"]
    # save parcial: cats_off None no pisa lo guardado
    prefs.save(senderos={"tamar_path": "36,5"})
    got = prefs.load_user("_local")
    assert got["senderos"] == {"tamar_path": "36,5"}     # senderos se REEMPLAZA
    assert got["cats_off"] == ["dlk", "bonares"]         # cats_off intacto
    # claves desconocidas se descartan (nunca basura al archivo)
    prefs.save(senderos={"infl_path": "1", "hack": "x"})
    assert "hack" not in prefs.load_user("_local")["senderos"]
    prefs.reset()
    assert prefs.load_user("_local")["senderos"] == {}


# ── presets nombrados ───────────────────────────────────────────────────────
def test_presets_fotografian_aplican_y_sobreviven_al_reset(prefs_tmp) -> None:
    prefs.save(senderos={"infl_path": "2,0"}, cats_off=["dlk"])
    assert prefs.preset_save("base")
    prefs.save(senderos={"infl_path": "4,0", "a3500_path": "3,0"}, cats_off=[])
    assert prefs.preset_save("estrés deva")
    assert prefs.preset_names() == ["base", "estrés deva"]
    # apply carga el snapshot como estado activo
    assert prefs.preset_apply("base")
    got = prefs.load_user("_local")
    assert got["senderos"] == {"infl_path": "2,0"} and got["cats_off"] == ["dlk"]
    # reset borra lo ACTIVO pero la biblioteca de presets sobrevive
    prefs.reset()
    got = prefs.load_user("_local")
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
def test_infl_default_alineada_al_dato_ipc(monkeypatch) -> None:
    import indices
    monkeypatch.setattr(indices, "proyeccion_inflacion_mensual",
                        {"Jul-26": 1.8, "Aug-26": 1.6, "Sep-26": 1.4})
    # settle 09/07: los puntos medios de los tramos caen el ~24 de cada mes
    # (≥16 ⇒ rige el IPC del MES ANTERIOR): jun,jul,ago,sep,oct. Sin dato de
    # jun usa la primera proyección conocida (jul); oct extiende la última.
    got = prefs.infl_default(date(2026, 7, 9), 5)
    assert got == "1,80;1,80;1,60;1,40;1,40"


def test_slot_meses_lag_cer() -> None:
    # settle 21/08: mid del tramo 1 = 05/09 (día <16 ⇒ IPC de 2 meses atrás,
    # el dato de julio publicado a mediados de agosto).
    slots = prefs.slot_meses(date(2026, 8, 21), 6)
    assert [s["mes"] for s in slots[:4]] == ["sep", "oct", "nov", "dic"]
    assert [s["ipc"] for s in slots[:4]] == ["jul", "ago", "sep", "oct"]
    assert slots[4]["mes"] == "ene ’27" and slots[4]["ipc"] == "nov"   # cruce de año
    assert slots[0]["rango"] == "21/08 → 20/09"
    # settle 05/09: mid del tramo 1 = 20/09 (≥16 ⇒ IPC del mes anterior).
    s2 = prefs.slot_meses(date(2026, 9, 5), 1)
    assert s2[0] == {"mes": "sep", "ipc": "ago", "rango": "05/09 → 05/10"}


async def test_page_incluye_slots_de_meses(prefs_tmp) -> None:
    async with _client() as ac:
        r = await ac.get("/escenario")
    assert r.status_code == 200
    assert '"slots"' in r.text          # etiquetas en el JSON de bootstrap
    assert "sendero-ipc" in r.text      # sub-etiqueta IPC en la fila Inflación


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
        got = prefs.load_user("_local")
        assert got["senderos"] == {"infl_path": "2,5;2,0"} and got["cats_off"] == ["dlk"]
        # la página siguiente muestra lo fijado y la categoría destildada
        page = await ac.get("/escenario")
        assert "2,5;2,0" in page.text
        assert '"dlk"' in page.text                           # cats_off_json
        r = await ac.post("/escenario/prefs/reset")
        assert r.status_code == 200
        assert prefs.load_user("_local")["senderos"] == {}


@pytest.mark.asyncio
async def test_tabla_saltea_categorias_destildadas(prefs_tmp, monkeypatch) -> None:
    # Sin precios en el store no hay filas que renderizar, así que el skip se
    # verifica en el lugar que importa (eficiencia): las curvas cuyas categorías
    # están TODAS destildadas NI SE CONSTRUYEN (las filas se piden por curva
    # única vía _rows_for, deduplicadas y en paralelo).
    from backend.routes import escenario as route

    pedidas: list = []

    async def _spy(curve, plazo):
        pedidas.append(curve)
        return ([], [])

    monkeypatch.setattr(route, "_rows_for", _spy)
    async with _client() as ac:
        r = await ac.get("/escenario/table", params={
            "cats_off": "globales,bonares,dlk,dual_tamar_cer,dual_cer",
        })
    assert r.status_code == 200
    assert "globales" not in pedidas and "bonares" not in pedidas
    assert "dualtamar_cer" not in pedidas and "dualcer" not in pedidas
    assert "dolarlinked" not in pedidas
    assert "lecap" in pedidas and "tamar" in pedidas          # curvas de las prendidas sí
    assert len(pedidas) == len(set(pedidas))                  # sin duplicados


# ── multi-usuario ───────────────────────────────────────────────────────────
def test_prefs_por_usuario_aisladas(prefs_tmp) -> None:
    """El estado ACTIVO (senderos/tildes) es por usuario: lo que guarda uno no
    pisa lo del otro. Los presets nombrados son COMPARTIDOS (biblioteca)."""
    prefs.save({"infl_path": "2,0;2,0"}, ["globales"], user="rodri")
    prefs.save({"infl_path": "9,9"}, None, user="jose")

    r = prefs.load_user("rodri")
    j = prefs.load_user("jose")
    assert r["senderos"]["infl_path"] == "2,0;2,0" and r["cats_off"] == ["globales"]
    assert j["senderos"]["infl_path"] == "9,9" and j["cats_off"] == []

    # preset compartido: lo guarda rodri, lo aplica jose sobre SU estado
    assert prefs.preset_save("base", user="rodri")
    assert "base" in prefs.load_user("jose").get("presets", {})
    assert prefs.preset_apply("base", user="jose")
    assert prefs.load_user("jose")["senderos"]["infl_path"] == "2,0;2,0"
    assert prefs.load_user("rodri")["cats_off"] == ["globales"]   # rodri intacto

    # reset de jose no toca a rodri ni a los presets
    prefs.reset(user="jose")
    assert prefs.load_user("jose")["senderos"] == {}
    assert prefs.load_user("rodri")["senderos"]["infl_path"] == "2,0;2,0"
    assert prefs.preset_names() == ["base"]


def test_prefs_migra_formato_viejo(prefs_tmp, tmp_path) -> None:
    """Un archivo v1 (estado global único) migra sin perder nada: sirve de
    fallback para usuarios sin estado propio y los presets sobreviven."""
    import json as _json
    (tmp_path / "prefs.json").write_text(_json.dumps({
        "senderos": {"tamar_path": "24,0"}, "cats_off": ["dlk"],
        "presets": {"viejo": {"senderos": {"infl_path": "1,5"}, "cats_off": []}},
    }), encoding="utf-8")
    u = prefs.load_user("cualquiera")
    assert u["senderos"]["tamar_path"] == "24,0" and u["cats_off"] == ["dlk"]
    assert "viejo" in u["presets"]
    # al guardar, el usuario pasa a tener estado propio (el fallback no se toca)
    prefs.save({"infl_path": "3,0"}, None, user="cualquiera")
    assert prefs.load_user("cualquiera")["senderos"] == {"infl_path": "3,0"}
    assert prefs.load_user("otro")["senderos"]["tamar_path"] == "24,0"
