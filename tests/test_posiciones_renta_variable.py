"""Renta variable en Posiciones (17/11): hoja 'Base RV' de Delta - Especies y
subdivisión por SECTOR en los fondos de acciones.

Pedido del desk: la base de especies tiene una hoja de renta variable; con
ella un portafolio de acciones (más del 60 % en renta variable) se lee por
sector — en la tabla de tenencias y en la composición — y el resto de los
fondos no cambia.

- `delta_especies`: la hoja 'Base RV' (misma cabecera de dos filas que la
  Base RF) se indexa APARTE por BYMA, con alias por `Cod_Delta`; sin la hoja
  la Base RF carga igual.
- `routes/posiciones`: categoría por la columna Instrumento, sector por
  'Sector Delta' (si falta, el GICS), umbral estricto del 60 %, grupos por
  sector y dimensión Sector con su torta.
"""
from __future__ import annotations

import pytest


# ── hoja Base RV ────────────────────────────────────────────────────────────
_COLS_RV = ["Cod_Delta", "Descripción", "Instrumento", "Sector", "Sector Delta",
            "Emisor / Sponsor", "ISIN", "BYMA"]
_FILAS_RV = [
    ["GGAL AR", "GGAL AR / GRUPO FINANCIERO GALICIA-B", "ACCIONES", "Financials",
     "Bancos y Servicios Financieros ", "Grupo Financiero Galicia", "ARP495251018", "GGAL"],
    ["YPFD AR", "YPFD AR / YPF S.A.-D", "ACCIONES", "Energy", "Petroleo & Gas", "YPF", "ARP9897X1319", "YPFD"],
    ["AAPL AR", "AAPL AR / APPLE INC-CEDEAR", "CEDEARs", "Information Technology", "Tecnología", "Apple", None, "AAPL"],
    # sin 'Sector Delta': cae al GICS
    ["KO AR", "KO AR / COCA-COLA-CEDEAR", "CEDEARs", "Consumer Staples", None, "Coca-Cola", None, "KO"],
    # sin BYMA: se encuentra por su Cod_Delta entero (no por el primer token)
    ["VIST US", "VIST US / VISTA ENERGY", "ADRs", "Energy", "Petroleo & Gas", "Vista", None, None],
    # ticker repetido con otro sector: manda la primera fila
    ["TSM AR", "TSM AR / TAIWAN SEMI-CEDEAR", "CEDEARs", "Information Technology", "Tecnología", "TSMC", None, "TSM"],
    ["TSM US", "TSM US / TAIWAN SEMI-ADR", "ADRs", "Industrials", "Industria", "TSMC", None, "TSM"],
    # fórmula rota en la planilla: el error de Excel no es un sector
    ["PAMP AR", "PAMP AR / PAMPA ENERGIA", "ACCIONES", "#REF!", "#N/A", "Pampa Energía", None, "PAMP"],
    # fila vacía de la planilla
    [None, None, None, None, None, None, None, "NC"],
]


def _hoja(ws, cols, filas) -> None:
    """Cabecera de DOS filas en las filas 3 y 4 de Excel (`header=[2, 3]`):
    arriba el grupo, abajo el nombre de la columna — como la base real."""
    ws.append(["Base de especies"])
    ws.append([])
    ws.append(["Identificación"] + [None] * (len(cols) - 1))
    ws.append(cols)
    for f in filas:
        ws.append(f)


def _especies_xlsx(path, con_rv: bool = True) -> str:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Categorías"
    ws.append(["hoja que no se lee"])
    if con_rv:
        _hoja(wb.create_sheet("Base RV"), _COLS_RV, _FILAS_RV)
    _hoja(wb.create_sheet("Base RF"), ["Cod_Delta", "Ajuste", "Tasa", "Emisor / Sponsor", "BYMA"],
          [["ONT1", "ARS", "TAMAR", "Emisor SA", "ONT1"]])
    wb.save(path)
    return str(path)


@pytest.fixture
def especies(tmp_path, monkeypatch):
    """`delta_especies` cargado desde un xlsx sintético con las dos hojas."""
    from backend.services import delta_especies

    monkeypatch.setenv("DELTA_ESPECIES_PATH", _especies_xlsx(tmp_path / "Delta - Especies.xlsx"))
    monkeypatch.setattr(delta_especies, "_cache", None)
    yield delta_especies
    monkeypatch.setattr(delta_especies, "_cache", None)


def test_base_rv_se_indexa_por_byma_con_alias_y_aparte_de_la_rf(especies) -> None:
    de = especies
    st = de.status()
    assert st["loaded"] and st["error"] is None and st["error_rv"] is None
    assert st["n"] == 1 and st["n_rv"] == 8          # la fila "NC" vacía no cuenta
    assert de.info_rv("PAMP")["Instrumento"] == "ACCIONES" and de.sector_rv("PAMP") is None   # "#REF!" no es sector
    g = de.info_rv("ggal")
    assert g["Instrumento"] == "ACCIONES" and g["Emisor / Sponsor"] == "Grupo Financiero Galicia"
    assert g["Sector Delta"] == "Bancos y Servicios Financieros"       # sin el espacio de más
    assert de.sector_rv("GGAL") == "Bancos y Servicios Financieros"
    assert de.sector_rv("KO") == "Consumer Staples"                    # sin Sector Delta: el GICS
    # alias por Cod_Delta: como viene en la cartera y por su primer token
    assert de.info_rv("GGAL AR") is g
    assert de.sector_rv("VIST US") == "Petroleo & Gas"
    # ...pero NO por su primer token: 'VIST US' (el ADR) no es la fila de una
    # tenencia 'VIST' (el CEDEAR) — con 'AGRO US' sería directamente otra empresa
    assert de.info_rv("VIST") is None
    assert de.sector_rv("TSM") == "Tecnología"                         # BYMA repetido: la primera fila
    # la fila repetida no se pierde: se llega por su Cod_Delta completo
    assert de.info_rv("TSM US")["Instrumento"] == "ADRs" and de.sector_rv("TSM US") == "Industria"
    assert de.info_rv("TSM AR")["Instrumento"] == "CEDEARs"
    assert de.info_rv("NC") is None and de.info_rv(None) is None and de.sector_rv("ZZZ") is None
    # índices separados: la clasificación de bonos no ve la renta variable
    assert de.info("GGAL") is None and de.info_rv("ONT1") is None
    assert de.info("ONT1")["Tasa"] == "TAMAR"


def test_indexar_rv_celdas_y_cabeceras_sucias() -> None:
    """Planilla real: una columna de fórmulas toda en 0 llega float ("0.0" no
    es un sector), dos columnas con el mismo nombre tras aplanar la cabecera
    daban una Series por celda, y el alias corto sale de la MISMA
    normalización que el ticker de una tenencia (sin depender del orden)."""
    import pandas as pd

    from backend.services import delta_especies as de

    df = pd.DataFrame(
        [["BAC US", "ADRs", 0.0, "Bancos", "x", None],
         ["BAC AR", "CEDEARs", 0.0, "Bancos", "y", "BA.C"],
         ["AGRO US", "ADRs", 0.0, "Agro", "z", None],
         ["CENCOSUD CI", "ACCIONES", 0.0, None, "w", "CENCOSUD"]],
        columns=["Cod_Delta", "Instrumento", "Sector", "Sector Delta", "Sector Delta", "BYMA"])
    df = de._sin_duplicadas(df, "Base RV")
    assert list(df.columns) == ["Cod_Delta", "Instrumento", "Sector", "Sector Delta", "BYMA"]
    by = de._indexar_rv(df)["by_code"]
    assert by["BA.C"]["Sector Delta"] == "Bancos"                      # la primera columna, texto limpio
    assert "Sector" not in by["BA.C"]                                  # el 0.0 de la fórmula no es dato
    assert by["BAC"]["Instrumento"] == "CEDEARs"                       # 'BAC AR' → BAC, no el ADR de arriba
    assert by["BAC US"]["Instrumento"] == "ADRs" and by["BAC AR"]["Instrumento"] == "CEDEARs"
    assert "AGRO" not in by and by["AGRO US"]["Sector Delta"] == "Agro"
    assert by["CENCOSUD"]["Instrumento"] == "ACCIONES" and "Sector Delta" not in by["CENCOSUD"]


def test_sin_hoja_rv_la_base_rf_carga_igual(tmp_path, monkeypatch) -> None:
    from backend.services import delta_especies as de

    monkeypatch.setenv("DELTA_ESPECIES_PATH", _especies_xlsx(tmp_path / "e.xlsx", con_rv=False))
    monkeypatch.setattr(de, "_cache", None)
    st = de.status()
    assert st["loaded"] and st["error"] is None and st["n"] == 1
    assert st["n_rv"] == 0 and "Base RV" in st["error_rv"]
    assert de.info("ONT1")["Ajuste"] == "ARS" and de.info_rv("GGAL") is None
    monkeypatch.setattr(de, "_cache", None)


# ── Posiciones ──────────────────────────────────────────────────────────────
def _cartera(positions, monkeypatch, holdings, pn) -> None:
    monkeypatch.setattr(positions, "_cache", {
        "loaded": True, "error": None, "paths": {}, "asof": "t", "by_code": {},
        "pn": pn, "fondos": {7: "Acciones Argentina", 8: "Renta Mixta"}, "holdings": holdings,
    })


_H7 = [   # fondo 7: 88 % en renta variable
    {"cod_fondo": 7, "cod_delta": "GGAL", "especie": "GRUPO FINANCIERO GALICIA", "cantidad": 10.0, "valor": 300.0, "clase": "Renta Variable"},
    {"cod_fondo": 7, "cod_delta": "YPFD", "especie": "YPF", "cantidad": 5.0, "valor": 250.0, "clase": "Renta Variable"},
    {"cod_fondo": 7, "cod_delta": "VIST US", "especie": "VISTA", "cantidad": 2.0, "valor": 150.0, "clase": "Renta Variable"},
    {"cod_fondo": 7, "cod_delta": "AAPL", "especie": "APPLE CEDEAR", "cantidad": 3.0, "valor": 100.0, "clase": "Renta Variable"},
    # acción que todavía no está en la Base RV: es RV por la Clase, sin sector
    {"cod_fondo": 7, "cod_delta": "NUEVA", "especie": "EMPRESA NUEVA", "cantidad": 1.0, "valor": 80.0, "clase": "Acciones"},
    {"cod_fondo": 7, "cod_delta": None, "especie": "CAUCION COLOCADORA 1 DIA", "cantidad": None, "valor": 120.0, "clase": "Liquidez"},
]
_H8 = [   # fondo 8: 60 % justo → NO es fondo de acciones (el umbral es "más del 60 %")
    {"cod_fondo": 8, "cod_delta": "GGAL", "especie": "GRUPO FINANCIERO GALICIA", "cantidad": 10.0, "valor": 600.0, "clase": "Renta Variable"},
    {"cod_fondo": 8, "cod_delta": None, "especie": "PLAZO FIJO BANCO MACRO", "cantidad": None, "valor": 400.0, "clase": "Renta Fija"},
]


def test_fondo_de_acciones_se_subdivide_por_sector(especies, monkeypatch) -> None:
    from backend.routes import posiciones as P
    from backend.services import positions

    _cartera(positions, monkeypatch, _H7 + _H8, {7: 1000.0, 8: 1000.0})
    ctx = P._fondo_ctx(7, "24hs")
    assert ctx["fondo_rv"] is True and ctx["pct_rv"] == pytest.approx(0.88)
    by = {r["cod_delta"]: r for r in ctx["rows"] if r["cod_delta"]}
    # categoría por la columna Instrumento de la base, no por la Clase cruda
    assert (by["GGAL"]["categoria"], by["GGAL"]["cat_src"]) == ("Acciones", "base_rv")
    assert by["AAPL"]["categoria"] == "CEDEARs" and by["VIST US"]["categoria"] == "ADRs"
    assert by["NUEVA"]["categoria"] == "Acciones" and by["NUEVA"]["cat_src"] == "clase"
    assert by["GGAL"]["sector"] == "Bancos y Servicios Financieros" and by["NUEVA"]["sector"] == "(sin sector)"
    assert by["GGAL"]["emisor"] == "Grupo Financiero Galicia"          # emisor de la Base RV
    assert "Sector: Petroleo & Gas" in by["YPFD"]["cat_src_txt"]
    # tabla: la renta variable por sector (Σ valor desc), lo demás por categoría
    gs = [(g["cat"], g["sector"], g["n"], g["valor"]) for g in ctx["grupos"]]
    assert gs == [
        ("Petroleo & Gas", True, 2, 400.0),                            # YPFD + VIST (acción + ADR)
        ("Bancos y Servicios Financieros", True, 1, 300.0),
        ("Caución", False, 1, 120.0),
        ("Tecnología", True, 1, 100.0),
        ("(sin sector)", True, 1, 80.0),
    ]
    # composición: dimensión Sector después de Categoría, el resto al final
    assert list(ctx["summary"])[:3] == ["Clase de Activo", "Categoría", "Sector"]
    assert [(r["cat"], r["monto"]) for r in ctx["summary"]["Sector"]] == [
        ("Petroleo & Gas", 400.0), ("Bancos y Servicios Financieros", 300.0), ("Tecnología", 100.0),
        ("(sin sector)", 80.0), ("Resto de la cartera", 120.0)]
    assert ctx["summary"]["Sector"][0]["pct"] == pytest.approx(0.40)
    cats = {r["cat"]: r["monto"] for r in ctx["summary"]["Categoría"]}
    assert cats == {"Acciones": 630.0, "ADRs": 150.0, "CEDEARs": 100.0, "Caución": 120.0}
    assert "Sector" in ctx["donas"] and ctx["donas"]["Sector"]["n"] == 5


def test_fondo_mixto_no_cambia(especies, monkeypatch) -> None:
    """60 % justo no es "más del 60 %": la tabla sigue por Categoría y la
    composición no lleva Sector — pero la fila sabe su sector (tooltip)."""
    from backend.routes import posiciones as P
    from backend.services import positions

    _cartera(positions, monkeypatch, _H7 + _H8, {7: 1000.0, 8: 1000.0})
    ctx = P._fondo_ctx(8, "24hs")
    assert ctx["fondo_rv"] is False and ctx["pct_rv"] == pytest.approx(0.60)
    assert [(g["cat"], g["sector"]) for g in ctx["grupos"]] == [("Acciones", False), ("Plazos Fijos", False)]
    assert "Sector" not in ctx["summary"] and "Sector" not in ctx["donas"]
    assert ctx["rows"][0]["sector"] == "Bancos y Servicios Financieros"
    # sin PN el peso sale sobre lo invertido (mismo denominador que el resto)
    _cartera(positions, monkeypatch, _H7 + _H8, {})
    assert P._fondo_ctx(7, "24hs")["pct_rv"] == pytest.approx(880.0 / 1000.0)
    assert P._fondo_ctx(8, "24hs")["fondo_rv"] is False
    # un PN viejo / más chico que la cartera no convierte un fondo de renta
    # fija en "fondo de acciones": el peso va contra el mayor de los dos
    _cartera(positions, monkeypatch, [
        {"cod_fondo": 8, "cod_delta": "GGAL", "especie": "GALICIA", "cantidad": 1.0, "valor": 70.0, "clase": "Renta Variable"},
        {"cod_fondo": 8, "cod_delta": None, "especie": "PLAZO FIJO BANCO MACRO", "cantidad": None, "valor": 930.0, "clase": "Renta Fija"},
    ], {8: 100.0})
    ctx = P._fondo_ctx(8, "24hs")
    assert ctx["fondo_rv"] is False and ctx["pct_rv"] == pytest.approx(0.07)


def test_una_fila_de_renta_fija_nunca_se_lee_como_accion(especies, monkeypatch) -> None:
    """Ficha de especies.py y fila de la Base RF mandan sobre la Base RV: un
    ticker que estuviera en las dos hojas sigue siendo el bono."""
    from backend.routes import posiciones as P

    h = {"cod_fondo": 7, "cod_delta": "GGAL", "especie": "X", "valor": 1.0, "clase": "Renta Fija"}
    assert P._clasif(h, None) == ("Acciones", "base_rv")
    monkeypatch.setattr(especies, "info", lambda c: {"Ajuste": "ARS", "Tasa": "TAMAR"} if c == "GGAL" else None)
    cat, src = P._clasif(h, None)
    assert src == "base" and "TAMAR" in cat and not P._es_rv(cat, src)


def test_agrupar_no_mezcla_un_sector_con_una_categoria_homonima() -> None:
    from backend.routes.posiciones import _agrupar_tenencias

    rows = [{"categoria": "Acciones", "es_rv": True, "sector": "Otros", "valor": 10.0, "pct_pn": 0.1},
            {"categoria": "Otros", "es_rv": False, "sector": None, "valor": 5.0, "pct_pn": 0.05}]
    assert [(g["cat"], g["sector"], g["n"]) for g in _agrupar_tenencias(rows, por_sector=True)] == [
        ("Otros", True, 1), ("Otros", False, 1)]
    assert [(g["cat"], g["sector"]) for g in _agrupar_tenencias(rows)] == [("Acciones", False), ("Otros", False)]


def test_reporte_renta_variable_sin_sector(especies, monkeypatch) -> None:
    """/admin: la renta variable no pide Ajuste / Tasa; lo que falta es su
    fila (o su sector) en la hoja Base RV."""
    from backend.routes import posiciones as P
    from backend.services import positions

    _cartera(positions, monkeypatch, _H7 + _H8, {7: 1000.0, 8: 1000.0})
    rep = P.reporte_clasificacion()
    assert rep["n_rv"] == 6 and rep["n_base"] == 5            # GGAL ×2, YPFD, VIST, AAPL por la base
    assert [r["code"] for r in rep["sin_sector"]] == ["NUEVA"] and rep["n_sin_sector"] == 1
    assert rep["sin_sector"][0]["en_base"] is False and rep["rv_error"] is None
    assert "NUEVA" not in {r["code"] for r in rep["con_ticker"]}
    # "Especies faltantes": un ticker que la Base RV sí tiene (el ADR 'VIST US',
    # que no está en los paneles) no es un "bono sin ficha"; NUEVA sí falta
    falt = {r["code"] for r in positions.especies_faltantes()["faltantes"]}
    assert "VIST US" not in falt and "NUEVA" in falt
    # renta variable SIN ticker y con la Clase cruda: no hay fila de la Base RV
    # que cargar → sigue en "descripciones sin ticker" (no desaparece)
    _cartera(positions, monkeypatch, _H7 + [
        {"cod_fondo": 7, "cod_delta": None, "especie": "DIVIDENDOS A COBRAR", "cantidad": None, "valor": 20.0,
         "clase": "Renta Variable"}], {7: 1000.0})
    rep = P.reporte_clasificacion()
    assert [r["especie"] for r in rep["sin_ticker"]] == ["DIVIDENDOS A COBRAR"]
    assert [r["code"] for r in rep["sin_sector"]] == ["NUEVA"]


def test_dona_conserva_el_indice_de_la_fila() -> None:
    """Un sector en 0 (una acción sin valor) no se dibuja, pero la porción
    siguiente conserva el índice de SU fila: mismo color, mismo resaltado y el
    salto al grupo correcto (antes "Resto de la cartera" quedaba corrido)."""
    from backend.services import svg_charts

    d = svg_charts.donut([{"label": "A", "val": 3.0}, {"label": "Cero", "val": 0.0},
                          {"label": "Resto de la cartera", "val": 1.0}])
    assert [(s["i"], s["label"]) for s in d["slices"]] == [(0, "A"), (2, "Resto de la cartera")]
    assert d["n"] == 2


@pytest.mark.asyncio
async def test_http_posiciones_fondo_de_acciones(especies, monkeypatch) -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app
    from backend.services import positions

    _cartera(positions, monkeypatch, _H7 + _H8, {7: 1000.0, 8: 1000.0})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/posiciones/table", params={"fondo": "7"})
        assert r.status_code == 200
        t = r.text
        assert 'data-grp="Sector · Petroleo &amp; Gas"' in t and "pos-grp-sector" in t
        assert 'data-dim="Sector"' in t and "Resto de la cartera" in t
        assert "por sector" in t and "88,0" in t
        # el sector también es TEXTO de la fila (filtro, orden y CSV leen celdas)
        assert 'Acciones <span class="pos-sector">· Petroleo &amp; Gas</span>' in t
        assert 'sector</span> Petroleo &amp; Gas' in t                  # tag y nombre no van pegados
        assert t.count("comp-resto") == 3                              # fila, porción y leyenda de "Resto"
        assert 'class="comp-lg" data-i="4" data-cat="Resto de la cartera"' in t
        assert t.index('data-dim="Categoría"') < t.index('data-dim="Sector"') < t.index('data-dim="Tasa"')
        r8 = await ac.get("/posiciones/table", params={"fondo": "8"})
        assert r8.status_code == 200
        assert 'data-dim="Sector"' not in r8.text and "pos-grp-sector" not in r8.text
        assert "pos-sector" not in r8.text and "comp-resto" not in r8.text
        assert 'data-grp="Acciones"' in r8.text
