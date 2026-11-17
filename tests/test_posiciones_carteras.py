"""Carteras en Posiciones / Matriz: UNA sola fuente, Delta_Composicion.xlsx +
Delta_PN.xlsx. Los fondos Galileo viven ahí como fondos Delta comunes; los
viejos Galileo_Composicion.xlsx / Galileo_PN.xlsx NO se leen aunque sigan en
la carpeta (duplicaban fondos con las tenencias del último día en que se
bajaban — pedido del desk 17/11)."""
from __future__ import annotations

import logging
import os

import pandas as pd
import pytest
from httpx import ASGITransport, AsyncClient

from backend.services import bond_universe, positions

# (fondo, Cod_Delta, Especie, Cantidad, Valor, Clase de Activo)
_DELTA = [
    (5, "AL30", "BONAR 2030", 1_000_000.0, 8.4e8, "Soberano USD"),
    (22, "AL30", "BONAR 2030", 300_000.0, 2.5e8, "Soberano USD"),
    (18, "TX26", "BONCER 2026", 2_000_000.0, 1.5e9, "CER"),
    (18, "ZZZZ9", "ON DESCONOCIDA 2031", 50_000.0, 1.0e6, "ON"),
    (5, "GGAL AR", "GRUPO FINANCIERO GALICIA", 5_000.0, 8.0e7, "Acciones"),   # ticker Bloomberg
    (18, "NC", "PLAZO FIJO BANCO X", None, 5.0e6, "Renta Fija"),              # sin ticker: no es especie
]
_PN = {5: 5e10, 18: 9e9, 22: 3.7e10}


def _delta_files(d) -> None:
    pd.DataFrame({
        "CodFondo": [f[0] for f in _DELTA], "Cod_Delta": [f[1] for f in _DELTA],
        "Especie": [f[2] for f in _DELTA], "Cantidad": [f[3] for f in _DELTA],
        "Valor": [f[4] for f in _DELTA], "Clase de Activo": [f[5] for f in _DELTA],
    }).to_excel(d / "Delta_Composicion.xlsx", sheet_name="Sheet1", index=False)
    pd.DataFrame({"CodFondo": list(_PN), "PN": list(_PN.values())}).to_excel(
        d / "Delta_PN.xlsx", sheet_name="Sheet1", index=False)


def _galileo_viejo_files(d, nombre: str = "Galileo_Composicion.xlsx") -> None:
    """Los archivos de la familia vieja tal como quedaron en la carpeta: un
    fondo con el MISMO nombre que uno de Delta (el 18, ver Delta_Fondos.txt) y
    otro que Delta no tiene, con un AL30 por ISIN que el loader viejo sumaba
    a la posición."""
    bond_universe.ensure_loaded()
    isin_al30 = str(getattr(bond_universe.get("AL30"), "isin", None) or "ARARGE3209S6")
    filas = [
        # (cod, fondo, descripcion, isin, instrumento, clase, cant, valor)
        (8, "GALILEO ACCIONES", "BBAR AR / BBVA BANCO FRANCES SA", "ARP125991090",
         "Acciones", "Acciones", 10_000.0, 9.0e7),
        (8, "GALILEO ACCIONES", "Bonar 2030 (local)", isin_al30,
         "Bonos Soberano", "Soberano USD MEP", 777_000.0, 6.5e8),
        (2, "GALILEO EVENT DRIVEN", "Bonar 2030 (local)", isin_al30,
         "Bonos Soberano", "Soberano USD MEP", 123_000.0, 1.0e8),
        (2, "GALILEO EVENT DRIVEN", "BC Petroleos Mexicanos 28 01 2060", "US71654QDF63",
         "Bonos Corporativo", "Bonos Corporativo USD", 2_000_000.0, 1.64e6),
    ]
    pd.DataFrame({
        "Fecha": ["2026-09-08"] * len(filas),
        "CodFondo": [f[0] for f in filas], "fondo": [f[1] for f in filas],
        "descripcion": [f[2] for f in filas], "isin": [f[3] for f in filas],
        "instrumento": [f[4] for f in filas], "Clasifica_Ficha": [f[5] for f in filas],
        "cantidad": [f[6] for f in filas], "valor": [f[7] for f in filas],
    }).to_excel(d / nombre, sheet_name="Sheet1", index=False)
    pd.DataFrame({"CodFondo": [2, 8], "PN": [2.8e8, 1.1e11]}).to_excel(
        d / "Galileo_PN.xlsx", sheet_name="Sheet1", index=False)


def _env(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DELTA_BASES_DIR", str(tmp_path))
    for env in ("DELTA_COMPOSICION_PATH", "DELTA_PN_PATH", "DELTA_FONDOS_PATH", "DELTA_HISTORICO_DIR"):
        monkeypatch.delenv(env, raising=False)


def _soltar_cache() -> None:
    with positions._lock:
        positions._cache = None       # el próximo test recarga su propio estado


@pytest.fixture()
def carteras(tmp_path, monkeypatch):
    _env(tmp_path, monkeypatch)
    _delta_files(tmp_path)
    positions.refresh()
    yield tmp_path
    _soltar_cache()


@pytest.fixture()
def carteras_con_galileo_viejo(tmp_path, monkeypatch):
    """Delta + los Galileo_* viejos en la MISMA carpeta. El fondo 18 de Delta
    se llama igual que el 8 del archivo viejo ("Galileo Acciones")."""
    _env(tmp_path, monkeypatch)
    _delta_files(tmp_path)
    _galileo_viejo_files(tmp_path)
    (tmp_path / "Delta_Fondos.txt").write_text(
        "5\tPesos\n18\tGalileo Acciones\n22\tRenta Dolares\n", encoding="utf-8")
    positions.refresh()
    yield tmp_path
    _soltar_cache()


def test_carga_delta(carteras) -> None:
    fs = positions.fondos()
    por_cod = {f["cod"]: f for f in fs}
    assert set(por_cod) == {5, 18, 22}
    assert por_cod[5]["nombre"] == "5 — Pesos" and por_cod[5]["pn"] == 5e10
    st = positions.status()
    assert st["loaded"] and st["error"] is None
    assert st["n_holdings"] == len(_DELTA) and st["n_fondos_pn"] == 3
    assert st["galileo_viejo"] is False
    assert "n_fondos_galileo" not in st and "galileo_ignorados" not in st
    assert set(st["paths"]) == {"composicion", "pn"}
    # el ticker Bloomberg queda como el de BYMA y la fila sin ticker no es especie
    assert positions.especies_universe() == ["AL30", "GGAL", "TX26", "ZZZZ9"]
    p = positions.position_for("AL30")
    assert p is not None and p["n_fondos"] == 2
    assert p["total_cantidad"] == pytest.approx(1_300_000.0)
    assert {f["cod_fondo"] for f in p["funds"]} == {5, 22}
    fu = positions.fuentes()
    assert [f["cod"] for f in fu] == [5, 18, 22]
    assert {f["archivo"] for f in fu} == {"Delta_Composicion.xlsx"} and not any(f["ignorado"] for f in fu)
    assert set(fu[0]) == {"cod", "nombre", "n", "pn", "archivo", "ignorado"}


def test_visibilidad_recalcula_totales_sobre_lo_visible(carteras) -> None:
    """Invariante de seguridad: con allowlist, sólo los fondos tildados — y
    los totales de la posición se recalculan sobre lo visible."""
    assert {f["cod"] for f in positions.fondos(visibles={5, 18})} == {5, 18}
    p = positions.position_for("AL30", visibles={5})
    assert p is not None and p["n_fondos"] == 1
    assert p["total_cantidad"] == pytest.approx(1_000_000.0)
    assert positions.holdings(22, visibles={5}) == []
    assert positions.position_for("TX26", visibles={5}) is None


def test_galileo_viejo_en_la_carpeta_no_se_carga(carteras_con_galileo_viejo, monkeypatch, caplog) -> None:
    """Pedido del desk 17/11: "ignorá el viejo Delta composición de Galileo,
    ahora es sólo Delta, porque si no duplica fondos con las tenencias del
    último día en que se bajaban". Con Galileo_Composicion.xlsx + Galileo_PN.xlsx
    todavía en la carpeta (un fondo con el nombre de uno de Delta y otro que
    Delta no tiene) se cargan SÓLO los fondos de Delta: el archivo viejo ni se
    abre, y la carga lo avisa UNA vez."""
    leidos = []
    real = pd.read_excel

    def _espia(path, *a, **kw):
        leidos.append(os.path.basename(str(path)).lower())
        return real(path, *a, **kw)

    monkeypatch.setattr(pd, "read_excel", _espia)
    with caplog.at_level(logging.INFO, logger="backend.positions"):
        c = positions.refresh()
    assert c["loaded"] and c["error"] is None
    assert leidos == ["delta_composicion.xlsx", "delta_pn.xlsx"]         # el viejo nunca se abre
    avisos = [r.getMessage() for r in caplog.records if "Galileo_Composicion.xlsx" in r.getMessage()]
    assert len(avisos) == 1 and "se ignora" in avisos[0]

    fs = positions.fondos()
    assert [f["cod"] for f in fs] == [5, 18, 22]                         # ni el repetido ni el que Delta no tiene
    assert all(f["cod"] < 10_000 for f in fs)
    assert {f["cod"]: f["pn"] for f in fs} == _PN
    assert positions.fondo_label(18) == "18 — Galileo Acciones"          # el fondo Galileo ES un fondo Delta
    assert all(h["cod_fondo"] < 10_000 for h in c["holdings"]) and len(c["holdings"]) == len(_DELTA)
    assert positions.holdings(10_002) == [] and positions.pn_of(10_008) is None
    # la posición no suma las tenencias viejas (777.000 + 123.000 de AL30 por ISIN)
    p = positions.position_for("AL30")
    assert p["n_fondos"] == 2 and {f["cod_fondo"] for f in p["funds"]} == {5, 22}
    assert p["total_cantidad"] == pytest.approx(1_300_000.0)
    assert p["total_valor"] == pytest.approx(8.4e8 + 2.5e8)
    assert positions.position_for("BBAR") is None
    assert positions.especies_universe() == ["AL30", "GGAL", "TX26", "ZZZZ9"]
    st = positions.status()
    assert st["galileo_viejo"] is True and st["n_holdings"] == len(_DELTA) and st["n_fondos_pn"] == 3
    assert "galileo" not in st["paths"]
    assert {f["archivo"] for f in positions.fuentes()} == {"Delta_Composicion.xlsx"}


@pytest.mark.asyncio
async def test_http_galileo_viejo_matriz_y_link_viejo(carteras_con_galileo_viejo) -> None:
    """Matriz y Posiciones sólo con fondos Delta; un link viejo con ?familia=
    o con un ?fondo= namespaceado (10000 + n) sigue respondiendo 200."""
    from backend.main import app
    from backend.routes import posiciones as P

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        base = await ac.get("/matriz/table", params={"view": "vn"})
        for fam in ("galileo", "delta", "todos"):
            r = await ac.get("/matriz/table", params={"familia": fam, "view": "vn"})
            assert r.status_code == 200 and r.content == base.content
        assert "EVENT DRIVEN" not in base.text and "BBAR" not in base.text
        assert "3 fondos" in base.text and "18 — Galileo Acciones" in base.text
        page = await ac.get("/matriz", params={"familia": "galileo"})
        assert page.status_code == 200 and "EVENT DRIVEN" not in page.text
        assert 'name="familia"' not in page.text and "familia=" not in page.text
        pos = await ac.get("/posiciones", params={"fondo": 10_002})
        assert pos.status_code == 200 and "EVENT DRIVEN" not in pos.text
    # ?familia= ya no entra a la key del cache: UN render por (generación, vista, visibles)
    gen = positions.generation()
    assert [k for k in P._MATRIZ_CACHE if k[0] == gen] == [(gen, "vn", None)]


@pytest.mark.parametrize("nombre", [None, "GALILEO_COMPOSICION.XLSX"])
def test_aviso_galileo_viejo_sin_distinguir_mayusculas(tmp_path, monkeypatch, nombre) -> None:
    _env(tmp_path, monkeypatch)
    _delta_files(tmp_path)
    if nombre:
        _galileo_viejo_files(tmp_path, nombre)
    try:
        c = positions.refresh()
        assert c["loaded"] and c["error"] is None
        assert {f["cod"] for f in positions.fondos()} == {5, 18, 22}
        assert positions.status()["galileo_viejo"] is bool(nombre)
    finally:
        _soltar_cache()


@pytest.mark.asyncio
async def test_http_posiciones_tenencias_primero_y_torta(carteras) -> None:
    """Pedido del desk 06/11: la tabla de tenencias va ANTES de la composición;
    cada dimensión de la composición trae su dona (server-side) oculta con una
    porción por fila; la tabla dice a qué hora se valuó."""
    from backend.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/posiciones/table", params={"fondo": 5, "plazo": "24hs"})
    assert r.status_code == 200
    t = r.text
    assert t.index("· tenencias") < t.index("Composición por categoría")
    assert 'class="comp-dim" data-dim="Categoría"' in t and 'class="comp-donut"' in t
    assert t.count('class="comp-slice') >= 2 and 'data-cat="' in t
    assert 'class="pos-fresh" data-ts="' in t and "precios " in t


@pytest.mark.asyncio
async def test_http_posiciones_abreviatura_y_nombre(carteras) -> None:
    """Tabla de posiciones con Abreviatura + Nombre completo (como la matriz)."""
    import re

    from backend.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/posiciones", params={"fondo": 5})
        assert r.status_code == 200 and "5 — Pesos" in r.text
        t = await ac.get("/posiciones/table", params={"fondo": 5})
    assert t.status_code == 200 and ">Nombre</th>" in t.text
    assert "GRUPO FINANCIERO GALICIA" in t.text and "BONAR 2030" in t.text     # descripción en col. Nombre
    assert re.search(r">\s*GGAL\s*<", t.text) and re.search(r">\s*AL30\s*<", t.text)   # celda Especie = abreviatura


def test_donut_geometria() -> None:
    from backend.services import svg_charts
    d = svg_charts.donut([{"label": "A", "val": 60.0}, {"label": "B", "val": 40.0}, {"label": "C", "val": 0.0}])
    assert d["n"] == 2 and [s["label"] for s in d["slices"]] == ["A", "B"]
    assert d["slices"][0]["frac"] == pytest.approx(0.6) and d["slices"][0]["d"].startswith("M")
    assert " 1 1 " in d["slices"][0]["d"]                   # 60 % > 180°: arco grande
    assert " 0 1 " in d["slices"][1]["d"]                   # 40 %: arco chico
    uno = svg_charts.donut([{"label": "Todo", "val": 5.0}])
    assert uno["n"] == 1 and uno["slices"][0]["frac"] == 1.0 and uno["slices"][0]["d"].count("M") == 2
    assert svg_charts.donut([]) is None and svg_charts.donut([{"label": "x", "val": -1}]) is None


def test_reporte_especies_faltantes(carteras) -> None:
    rep = positions.especies_faltantes()
    assert set(rep) == {"faltantes", "n_faltantes"}
    # ticker que la app no conoce → faltante; bono con ficha y acción de los paneles, no
    assert [r["code"] for r in rep["faltantes"]] == ["ZZZZ9"] and rep["n_faltantes"] == 1
    z = rep["faltantes"][0]
    assert z == {"code": "ZZZZ9", "especie": "ON DESCONOCIDA 2031", "n_filas": 1, "valor": 1.0e6}


def test_matriz_solo_especies_y_orden_por_valor(carteras) -> None:
    """Las filas sin ticker (plazo fijo, cash) no son filas de la matriz — ahí
    estaba la lentitud —; abreviatura + nombre en columnas separadas; orden
    por valor total, de mayor a menor; un fondo oculto no aporta fila ni columna."""
    from backend.routes.posiciones import _matriz_ctx

    ctx = _matriz_ctx(None)
    assert [f["cod"] for f in ctx["fondos"]] == [5, 18, 22]
    assert [r["especie"] for r in ctx["rows"]] == ["TX26", "AL30", "GGAL", "ZZZZ9"]
    assert not any("PLAZO FIJO" in r["nombre"] for r in ctx["rows"])
    al30 = next(r for r in ctx["rows"] if r["especie"] == "AL30")
    assert al30["abrev"] == "AL30" and al30["nombre"] == "BONAR 2030"
    assert [c["vn"] for c in al30["cells"]] == [1_000_000.0, None, 300_000.0]
    ggal = next(r for r in ctx["rows"] if r["especie"] == "GGAL")
    assert ggal["abrev"] == "GGAL" and ggal["nombre"] == "GRUPO FINANCIERO GALICIA"
    assert "familia" not in ctx and all("solo_galileo" not in r for r in ctx["rows"])

    solo5 = _matriz_ctx(frozenset({5}))
    assert [f["cod"] for f in solo5["fondos"]] == [5]
    assert [r["especie"] for r in solo5["rows"]] == ["AL30", "GGAL"]


@pytest.mark.asyncio
async def test_http_matriz_markup_compacto(carteras) -> None:
    """La velocidad de la matriz vive en el markup (el server la sirve de
    cache): celdas sin whitespace, vacías como <td></td>, filas en trozos con
    content-visibility, anchos por <col> y la página la embebe en un
    <template> (un solo layout). Regresión = la matriz vuelve a tardar 1 s."""
    from backend.main import app
    from backend.routes.posiciones import _matriz_ctx

    ctx = _matriz_ctx(None, "pct")
    assert len(ctx["w_cols"]) == len(ctx["fondos"]) and ctx["w_total"] >= sum(ctx["w_cols"])
    for r in ctx["rows"]:
        assert len(r["txt"]) == len(ctx["fondos"])
        assert all(t == "" or t.endswith("%") for t in r["txt"])     # vista % ya formateada
    vn = _matriz_ctx(None, "vn")
    al30 = next(r for r in vn["rows"] if r["especie"] == "AL30")
    assert "1.000.000" in al30["txt"] and "" in al30["txt"]          # es-AR + celda vacía

    # Vista "VN y %" (desk 09/10): nominales + espacio + % sobre PN en la misma
    # celda, texto plano; sin % (fondo sin PN) queda sólo el VN; vacía sigue vacía.
    ambos = _matriz_ctx(None, "vnpct")
    al30_ab = next(r for r in ambos["rows"] if r["especie"] == "AL30")
    con = [t for t in al30_ab["txt"] if t]
    assert con and all(t.endswith("%") and t.count(" ") == 1 for t in con)
    i = al30["txt"].index("1.000.000")
    assert al30_ab["txt"][i].startswith("1.000.000 ") and al30_ab["txt"][i].endswith("%")
    assert al30_ab["txt"][i].split(" ")[1] == ctx["rows"][[r["especie"] for r in ctx["rows"]].index("AL30")]["txt"][i]
    assert [t == "" for t in al30_ab["txt"]] == [t == "" for t in al30["txt"]]
    assert ambos["w_cols"][i] > vn["w_cols"][i]                          # la columna se ensancha para el texto

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/matriz/table", params={"view": "vn"})
        assert r.status_code == 200
        assert 'class="matriz-chunk"' in r.text and "content-visibility" not in r.text  # CSS, no inline
        assert '<td class="m-esp">AL30</td>' in r.text and "⊚G" not in r.text
        r2 = await ac.get("/matriz/table", params={"view": "vnpct"})
        assert r2.status_code == 200 and "VN y % sobre PN" in r2.text and "<td>1.000.000 " in r2.text
        page2 = await ac.get("/matriz", params={"view": "vnpct"})
        assert 'value="vnpct" selected' in page2.text
        assert 'href="/matriz?refresh=1&view=vnpct"' in page2.text
        assert "<colgroup>" in r.text and "--w-total:" in r.text
        assert "<td></td>" in r.text and "<td>\n" not in r.text and "\n<td" not in r.text
        assert 'matriz matriz-head"' in r.text and r.text.count("<colgroup>") >= 2
        page = await ac.get("/matriz")
        assert '<template id="matriz-tpl">' in page.text and "matriz-chunk" in page.text
        assert 'name="familia"' not in page.text and "Sólo Galileo" not in page.text


@pytest.mark.asyncio
async def test_http_admin_reporte_especies(carteras_con_galileo_viejo, tmp_path, monkeypatch) -> None:
    """El reporte vive en el panel de control: 403 sin sesión de superuser,
    200 con login (bootstrap) y muestra el ticker faltante. La tarjeta de
    fondos dice de qué archivo salió cada uno y que el Galileo viejo se ignora."""
    from backend.config import settings
    from backend.services import auth

    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "app_users_path", str(tmp_path / "users.json"))
    auth.refresh()
    assert auth.ensure_bootstrapped()["created"]
    from backend.main import app

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            r = await ac.get("/admin/especies-faltantes")
            assert r.status_code in (302, 401, 403)        # sin sesión no pasa
            await ac.post("/login", data={"username": "su_test",
                                          "password": "clave-de-test-2026!", "next": "/admin"})
            ok = await ac.get("/admin/especies-faltantes")
            assert ok.status_code == 200 and "ZZZZ9" in ok.text
            assert "normalizar" not in ok.text and "Familia" not in ok.text and "ISIN" not in ok.text
            page = await ac.get("/admin")
            assert "Especies faltantes" in page.text
            assert "Fuentes: 3 fondos cargados · Galileo_Composicion.xlsx ignorado" in page.text
            assert "18 — Galileo Acciones" in page.text and "EVENT DRIVEN" not in page.text
    finally:
        auth.refresh()


@pytest.mark.asyncio
async def test_http_posiciones_tir_dur_fondo_manual(carteras) -> None:
    """TIR y Duration ponderadas del FONDO (chip client-side, como Ret. día):
    TODAS las tasas son inputs editables precargados con el valor calculado,
    lo tipeado entra al ponderado sin tocar precios, y el switch 'proy.'
    cambia los defaults a la versión proyectada (ficha j / ROFEX)."""
    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        t = await ac.get("/posiciones/table", params={"fondo": 18})
    assert t.status_code == 200
    assert 'id="pos-fondo-tirdur"' in t.text           # chip TIR/Dur del fondo
    assert 'id="pos-proy"' in t.text                   # switch proyectado
    assert 'id="pos-tirdur-reset"' in t.text           # restaurar calculados
    assert "data-tirea=" in t.text and "data-tirea-proy=" in t.text
    assert "data-dur=" in t.text and "data-dur-proy=" in t.text
    assert 'class="pos-tir cell-edit"' in t.text       # tasa editable por fila
    assert 'class="pos-dur cell-edit"' in t.text       # duration editable


def test_enrich_version_proyectada(monkeypatch) -> None:
    """Defaults del modo 'proy.': un CER con ficha hermana j toma la TIR/Dur
    NOMINALES de la j (mismo precio de pantalla, cache de la curva proyectada);
    un DLK compone (1+tir)·(1+tea_ROFEX a la duration)−1 sin cambiar su
    duration; el resto queda igual a la base."""
    from backend.routes import posiciones as pos
    from backend.services import futuros as fut_svc

    filas = {
        "TX99": {"tirea": 0.05, "duration": 1.5, "last": 100.0, "tna": 0.05,
                 "tna_convention_label": "180/360", "price_source": "LA"},
        "TX99j": {"tirea": 0.32, "duration": 1.4, "last": 100.0, "tna": 0.30,
                  "tna_convention_label": "180/360", "price_source": "LA"},
        "TVDLK": {"tirea": 0.08, "duration": 2.0, "last": 100.0, "tna": 0.08,
                  "tna_convention_label": "90/365", "price_source": "LA"},
        "S9999": {"tirea": 0.40, "duration": 0.5, "last": 100.0, "tna": 0.38,
                  "tna_convention_label": "182/365", "price_source": "LA"},
    }
    monkeypatch.setattr(pos, "_row_for_code", lambda c, p, settle=None: filas.get(c))
    monkeypatch.setattr(pos.bond_universe, "get",
                        lambda c: object() if c in filas else None)
    monkeypatch.setattr(pos.pricing, "_bond_index_kind",
                        lambda c: {"TX99": "cer", "TVDLK": "a3500"}.get(c, ""))
    monkeypatch.setattr(fut_svc, "rows",
                        lambda canal="may", spot_v=None: [
                            {"dias": 365, "tea": 0.30}, {"dias": 730, "tea": 0.25}])

    rows = pos._enrich(
        [{"cod_delta": "TX99", "especie": "TX99", "valor": 100.0, "cantidad": 1.0,
          "cod_fondo": 1, "clase": ""},
         {"cod_delta": "TVDLK", "especie": "TVDLK", "valor": 100.0, "cantidad": 1.0,
          "cod_fondo": 1, "clase": ""},
         {"cod_delta": "S9999", "especie": "S9999", "valor": 100.0, "cantidad": 1.0,
          "cod_fondo": 1, "clase": ""}],
        pn=300.0, plazo="24hs")
    by = {r["abrev"]: r for r in rows}
    # CER → ficha j (TIR nominal + SU duration)
    assert by["TX99"]["tirea"] == pytest.approx(0.05)
    assert by["TX99"]["tirea_proy"] == pytest.approx(0.32)
    assert by["TX99"]["duration_proy"] == pytest.approx(1.4)
    # DLK → compuesta con la TEA del contrato a ~2 años (0.25); duration intacta
    assert by["TVDLK"]["tirea_proy"] == pytest.approx(1.08 * 1.25 - 1.0)
    assert by["TVDLK"]["duration_proy"] == pytest.approx(2.0)
    # LECAP: proyectado == base (el switch no la toca)
    assert by["S9999"]["tirea_proy"] == pytest.approx(0.40)
    assert by["S9999"]["duration_proy"] == pytest.approx(0.5)
