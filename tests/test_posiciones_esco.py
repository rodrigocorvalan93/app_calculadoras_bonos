"""Código de ESCO → ficha del bono en Posiciones (18/11).

Pedido del desk: el sistema de carteras (ESCO) escribe un bono en dólares con
su ticker de PESOS, más una "D" si la contabilidad del fondo es en dólares
(`GD30D`, `TTCDOD`), y no distingue MEP de cable. La app valúa con la ficha
NATIVA (`GD30C`, `TTCDC`), y los tickers no siempre siguen "O / D / C"
(`RCC1OD` → `RC1CC`, `BPOC7D` → `BPC7D`). Delta Renta Dólares Plus no
reconocía `TTCDOD`.

Se concilia por ISIN (el archivo de carteras lo trae por fila en `IsinCode`,
con `Pago` y `CAFCI_BYMA`; la Base RF de Delta - Especies es el respaldo):
`services/esco.py`. Los tests usan fichas reales del universo y un archivo de
carteras con el layout REAL (columnas `Inversion`, `IsinCode`, `Pago`…).
"""
from __future__ import annotations

import pandas as pd
import pytest

from backend.services import bond_universe, esco, positions

ISIN_TTCD = "USP90187AT55"       # Tecpetrol 2030: TTCDO (ref) / TTCDC (nativa, cable)
ISIN_GD30 = "US040114HS26"       # en especies.py lo comparten GD29 y GD30
ISIN_YM34 = "USP989MJBY67"       # YPF 2034: YM34O / YM34C
ISIN_MGCQ = "AR0519406398"       # Pampa 2028: sólo MGCQD (MEP)
ISIN_BPA8 = "AR0029227748"       # BOPREAL: BPA8D y BPB8D comparten todo


def _r(code, isin=None, pago=None, ticker=None):
    return esco.resolver(code, isin, pago, ticker)


# ── conciliación ────────────────────────────────────────────────────────────
def test_codigo_esco_de_fondo_dolar_va_a_la_ficha_nativa_por_isin() -> None:
    bond_universe.ensure_loaded()
    f = _r("TTCDOD", ISIN_TTCD, "USD")
    assert (f.calc, f.via, f.isin, f.pago, f.nota) == ("TTCDC", "isin", ISIN_TTCD, "USD", "")
    # el orden de las letras cambia: no es "sacar la D y poner la C"
    assert _r("RCC1OD", "USP04559BE29", "USD").calc == "RC1CC"
    assert _r("BPOC7D", "AR0763285209", "USB", "BPC7D").calc == "BPC7D"
    # el ticker con el que el desk lo valúa (YM34D) no decide: manda la nativa
    assert _r("YM34OD", ISIN_YM34, "USD", "YM34D").calc == "YM34C"
    # ESCO no usa el ticker ni para la especie en pesos: YPF34 es YM34O
    assert _r("YPF34", ISIN_YM34, "USD", "YM34O").calc == "YM34C"
    # un bono en pesos con otro código: la ficha base, nunca la pata j / v
    assert _r("XXCER", "AR0585812156").calc == "TXMJ9"


def test_un_codigo_con_ficha_propia_no_se_toca() -> None:
    bond_universe.ensure_loaded()
    for code, isin in (("AL30D", "ARARGE3209S6"), ("GD30", ISIN_GD30), ("TTCDO", ISIN_TTCD), ("TTCDC", ISIN_TTCD)):
        assert bond_universe.get(code) is not None
        assert _r(code, isin, "USD") is None
    assert _r(None) is None and _r("") is None


def test_isin_repetido_entre_series_se_separa_por_bono_y_nunca_se_adivina() -> None:
    """especies.py tiene el ISIN de GD30 también en GD29: el grupo se parte
    por vencimiento y se elige el bono que comparte raíz con el código."""
    bond_universe.ensure_loaded()
    assert set(esco._indice()[ISIN_GD30]) >= {"GD29", "GD29C", "GD30", "GD30C"}
    assert _r("GD30D", ISIN_GD30, "USD").calc == "GD30C"
    h = {"cod_delta": "ZZZ9", "isin": ISIN_GD30, "pago": "USD", "ticker": None}
    assert esco.resolver_h(h) is None and "varias fichas" in esco.motivo(h)
    # con el ISIN real de GD29 (que ninguna ficha tiene) cae al sufijo de ESCO
    f = _r("GD29D", "US040114HX11", "USD", "GD29D")
    assert (f.calc, f.via) == ("GD29C", "sufijo") and "US040114HX11" in f.nota
    assert _r("GD29D").calc == "GD29C"                     # sin ningún dato: igual


def test_varias_nativas_decide_el_pago_el_ticker_y_al_final_el_parecido() -> None:
    bond_universe.ensure_loaded()
    f = _r("BPOA8D", ISIN_BPA8, "USB", "BPA8D")
    assert (f.calc, f.nota) == ("BPA8D", "")               # el ticker de la base está entre las candidatas
    g = _r("BPOA8D", ISIN_BPA8, "USB")
    assert g.calc == "BPA8D" and "parecido" in g.nota       # sin ticker: se avisa cómo se eligió
    assert _r("BPOB8D", ISIN_BPA8, "USB").calc == "BPB8D"
    # la base dice USD y la única nativa es MEP: manda la ficha, y se avisa
    m = _r("MGCQOD", ISIN_MGCQ, "USD", "MGCQD")
    assert m.calc == "MGCQD" and "pago USD" in m.nota


def test_lo_que_no_se_puede_conciliar_queda_sin_ficha_con_su_motivo() -> None:
    bond_universe.ensure_loaded()
    h = {"cod_delta": "CO27D", "isin": "USP79171AF45", "pago": "USD", "ticker": "CO27D"}
    assert esco.resolver_h(h) is None and "USP79171AF45" in esco.motivo(h)
    # marcadores que no son un ISIN
    assert esco.isin_ok("Sin_Isin_FCI") is None and esco.isin_ok("PENDIENTE") is None
    assert esco.isin_ok(" usp90187at55 ") == ISIN_TTCD
    h2 = {"cod_delta": "FCIXX", "isin": "Sin_Isin_FCI", "pago": "en Pesos", "ticker": None}
    assert esco.resolver_h(h2) is None and "sin ISIN" in esco.motivo(h2)


# ── carteras con el layout real ─────────────────────────────────────────────
# (CodFondo, IsinCode, Cod_Delta, Pago, Inversion, Clase de Activo, CAFCI_BYMA, Cantidad, Valor)
_FILAS = [
    (26, ISIN_TTCD, "TTCDOD", "USD", "ON Tecpetrol S.A. Clase 12 Vto 03 11 2030 D", "Renta Fija", "TTCDD", 1_000_000.0, 1.02e6),
    (26, ISIN_GD30, "GD30D", "USD", "Bonos Globales Rep Arg en USD Step Up 2030 Vto 09 07 2030 D", "Renta Fija", "GD30D", 500_000.0, 4.1e5),
    (26, ISIN_MGCQ, "MGCQOD", "USD", "ON Pampa Energia Clase XXV Vto 06 08 2028 D", "Renta Fija", "MGCQD", 300_000.0, 3.1e5),
    (26, "USP79171AF45", "CO27D", "USD", "Título de Deuda Provincia de Córdoba al 7,125%", "Renta Fija", "CO27D", 100_000.0, 9.0e4),
    (15, ISIN_TTCD, "TTCDO", "USD", "ON Tecpetrol S.A. Clase 12 Vto 03 11 2030", "Renta Fija", "TTCDO", 200_000.0, 3.0e8),
    (15, ISIN_YM34, "YPF34", "USD", "ON YPF S.A. Clase XXXIV Vto 17 01 2034", "Renta Fija", "YM34O", 400_000.0, 6.0e8),
    (15, "US040114HX11", "GD29", "USD", "Bonos Globales Rep Arg en USD 2029", "Renta Fija", "GD29", 100_000.0, 1.3e8),
    (15, "Sin_Isin_FCI", "NC", "en Pesos", "Pionero Pesos Plus Clase B", "Liquidez", "NC", 1000.0, 5.0e6),
]
_FONDOS = ("CodFondo,NumFondo,CodCAFCI,Nombre,NombreCorto,CodTpFondo,Clasif,Apertura,Moneda\n"
           "15,15,500,DELTA MULTIMERCADO I,MULTIMERCADO,MI,3,Instrumento,ARS\n"
           "26,26,829,DELTA RENTA DÓLARES PLUS,RENTA DÓLARES PLUS,MI,3,Instrumento,USD\n")


@pytest.fixture()
def carteras(tmp_path, monkeypatch):
    monkeypatch.setenv("DELTA_BASES_DIR", str(tmp_path))
    for env in ("DELTA_COMPOSICION_PATH", "DELTA_PN_PATH", "DELTA_FONDOS_PATH", "DELTA_HISTORICO_DIR"):
        monkeypatch.delenv(env, raising=False)
    cols = ["CodFondo", "IsinCode", "Cod_Delta", "Pago", "Inversion", "Clase de Activo", "CAFCI_BYMA", "Cantidad", "Valor"]
    pd.DataFrame(_FILAS, columns=cols).to_excel(tmp_path / "Delta_Composicion.xlsx", sheet_name="Sheet1", index=False)
    pd.DataFrame({"CodFondo": [15, 26], "PN": [2e9, 2e6]}).to_excel(tmp_path / "Delta_PN.xlsx", sheet_name="Sheet1", index=False)
    (tmp_path / "Delta_Fondos.txt").write_text(_FONDOS, encoding="utf-8")
    bond_universe.ensure_loaded()
    positions.refresh()
    yield tmp_path
    with positions._lock:
        positions._cache = None


def test_la_cartera_real_trae_descripcion_isin_pago_y_moneda_del_fondo(carteras) -> None:
    hs = {h["cod_delta"]: h for h in positions.holdings(26)}
    t = hs["TTCDOD"]
    assert t["especie"] == "ON Tecpetrol S.A. Clase 12 Vto 03 11 2030 D"       # columna Inversion
    assert (t["isin"], t["pago"], t["ticker"]) == (ISIN_TTCD, "USD", "TTCDD")
    nc = [h for h in positions.holdings(15) if h["cod_delta"] is None][0]
    assert nc["especie"] == "Pionero Pesos Plus Clase B" and nc["isin"] is None and nc["ticker"] is None
    assert nc["pago"] == "EN PESOS"
    assert positions.fondo_moneda(26) == "USD" and positions.fondo_moneda(15) == "ARS"
    assert positions.fondo_moneda(99) is None and positions.fondo_label(26) == "26 — RENTA DÓLARES PLUS"


def test_fondo_en_dolares_reconoce_el_codigo_de_esco(carteras) -> None:
    from backend.routes import posiciones as P

    ctx = P._fondo_ctx(26, "24hs")
    by = {r["cod_delta"]: r for r in ctx["rows"]}
    t = by["TTCDOD"]
    assert t["ficha"] == "TTCDC" and t["in_universe"] is True and t["cat_src"] == "ficha"
    assert t["categoria"] == "ON USD" and t["vencimiento"] == bond_universe.get("TTCDC").vencimiento
    assert "TTCDOD" in t["ficha_txt"] and ISIN_TTCD in t["ficha_txt"] and "paga USD" in t["ficha_txt"]
    assert by["GD30D"]["ficha"] == "GD30C" and by["GD30D"]["categoria"] == "Soberano USD"
    assert by["MGCQOD"]["ficha"] == "MGCQD" and "Ojo" in by["MGCQOD"]["ficha_txt"]
    # sin ficha posible: queda como siempre, sin inventar
    assert by["CO27D"]["ficha"] is None and by["CO27D"]["in_universe"] is False
    cats = {r["cat"]: r["monto"] for r in ctx["summary"]["Categoría"]}
    assert cats["ON USD"] == pytest.approx(1.02e6) and cats["Soberano USD"] == pytest.approx(4.1e5)


def test_precio_nativo_en_fondo_dolar_y_especie_en_pesos_en_fondo_pesos(carteras, monkeypatch) -> None:
    """Fondo en dólares: fila de la ficha nativa con su ticker (precio en
    dólares). Fondo en pesos: la especie en pesos del mismo bono (el ticker
    de la base si tiene ficha; si no, la pata ARS de la nativa)."""
    from backend.routes import posiciones as P

    pedidos = []

    def fake(code, plazo, leg="native", settle=None, **kw):
        pedidos.append((code, leg))
        return {"last": 100.0, "price_source": "LA", "tirea": 0.08, "duration": 2.0}

    monkeypatch.setattr(P, "_row_for_code", fake)
    P._enrich(positions.holdings(26), 2e6, "24hs")
    assert ("TTCDC", "native") in pedidos and ("GD30C", "native") in pedidos and ("MGCQD", "native") in pedidos
    assert not any(c in ("TTCDOD", "GD30D", "TTCDD") for c, _ in pedidos if c != "CO27D")
    pedidos.clear()
    P._enrich(positions.holdings(15), 2e9, "24hs")
    assert ("YM34O", "native") in pedidos              # YPF34: la especie en pesos tiene ficha propia
    assert ("TTCDO", "native") in pedidos              # ficha propia: el camino de siempre
    assert ("YM34C", "native") not in pedidos
    # sin ticker de la base: la pata en pesos de la nativa; sin precio ahí, la nativa
    h = {"cod_fondo": 15, "cod_delta": "YPF34", "isin": ISIN_YM34, "pago": "USD", "ticker": None}
    pedidos.clear()
    P._fila_precio(h, esco.resolver_h(h), "24hs", None)
    assert pedidos == [("YM34C", "ARS")]
    monkeypatch.setattr(P, "_row_for_code", lambda code, plazo, leg="native", settle=None, **kw: (
        pedidos.append((code, leg)) or {"last": None, "price_source": None if leg == "ARS" else "CL"}))
    pedidos.clear()
    assert P._fila_precio(h, esco.resolver_h(h), "24hs", None)["price_source"] == "CL"
    assert pedidos == [("YM34C", "ARS"), ("YM34C", "native")]
    # sin Delta_Fondos (moneda del fondo desconocida) decide el sufijo de ESCO
    monkeypatch.setattr(positions, "fondo_moneda", lambda cod: None)
    pedidos.clear()
    hd = {"cod_fondo": 26, "cod_delta": "TTCDOD", "isin": ISIN_TTCD, "pago": "USD", "ticker": "TTCDD"}
    P._fila_precio(hd, esco.resolver_h(hd), "24hs", None)
    assert pedidos == [("TTCDC", "native")]


def test_tenencia_por_ficha_faltantes_y_reporte_de_admin(carteras) -> None:
    from backend.routes import posiciones as P

    # YAS / Comparador / Curvas piden la tenencia por la FICHA
    pos = positions.position_for("TTCDC")
    assert pos is not None and [f["cod_fondo"] for f in pos["funds"]] == [26]
    assert positions.position_for("TTCDC", visibles=[15]) is None            # no ve el fondo 26
    assert [f["cod_fondo"] for f in positions.position_for("TTCDO")["funds"]] == [15]
    assert [f["cod_fondo"] for f in positions.position_for("YM34C")["funds"]] == [15]
    falt = {r["code"] for r in positions.especies_faltantes()["faltantes"]}
    assert "TTCDOD" not in falt and "GD30D" not in falt and "YPF34" not in falt and "CO27D" in falt
    d = P.reporte_clasificacion()["esco"]
    res = {r["code"]: r for r in d["resueltos"]}
    assert res["TTCDOD"]["ficha"] == "TTCDC" and res["TTCDOD"]["via"] == "isin"
    assert res["YPF34"]["ficha"] == "YM34C" and res["MGCQOD"]["nota"]
    assert [r["code"] for r in d["sin_resolver"]] == ["CO27D"] and "USP79171AF45" in d["sin_resolver"][0]["motivo"]
    # GD29 tiene ficha, pero el ISIN de la cartera no es el de la ficha: se avisa
    assert [(r["code"], r["isin"], r["isin_ficha"]) for r in d["isin_distinto"]] == [("GD29", "US040114HX11", ISIN_GD30)]


def test_base_rf_por_codigo_de_esco_es_el_respaldo(tmp_path, monkeypatch) -> None:
    """Si la cartera no trae ISIN, la fila de la Base RF del código de ESCO
    (`Cod_Delta`, no el ticker BYMA) aporta ISIN, Pago y ticker."""
    from openpyxl import Workbook

    from backend.services import delta_especies as de

    wb = Workbook()
    ws = wb.active
    ws.title = "Base RF"
    ws.append(["Base de especies"]); ws.append([]); ws.append(["Nombres", None, None, None, None])
    ws.append(["Cod_Delta", "Pago", "ISIN", "BYMA", "CAFCI_BYMA"])
    ws.append(["TTCDOD", "USD", ISIN_TTCD, "TTCDD", "TTCDD"])
    ws.append(["TTCDO", "USD", ISIN_TTCD, "TTCDO", "TTCDO"])
    ws.append(["X31L6 CI", "ARS", "AR0000000001", "X31L6", "X31L6"])
    wb.save(tmp_path / "e.xlsx")
    monkeypatch.setenv("DELTA_ESPECIES_PATH", str(tmp_path / "e.xlsx"))
    monkeypatch.setattr(de, "_cache", None)
    try:
        assert de.info_cod("ttcdod") == {"ISIN": ISIN_TTCD, "Pago": "USD", "BYMA": "TTCDD", "CAFCI_BYMA": "TTCDD"}
        assert de.info_cod("X31L6")["ISIN"] == "AR0000000001"      # normalizado como una tenencia (sin " CI")
        assert de.info("TTCDOD") is None                            # el índice por ticker no cambia
        f = esco.resolver("TTCDOD")                                 # la cartera no trajo nada
        assert (f.calc, f.via, f.isin, f.pago) == ("TTCDC", "isin", ISIN_TTCD, "USD")
    finally:
        monkeypatch.setattr(de, "_cache", None)


@pytest.mark.asyncio
async def test_http_posiciones_muestra_la_ficha_conciliada(carteras) -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/posiciones/table", params={"fondo": "26"})
        assert r.status_code == 200
        t = r.text
        assert '<a href="/yas?code=TTCDC" title="Abrir en YAS">TTCDOD</a>' in t
        assert '→ TTCDC</span>' in t and '→ GD30C</span>' in t and "pos-ficha" in t
        assert "ON Tecpetrol S.A. Clase 12 Vto 03 11 2030 D" in t          # el nombre sale de Inversion
        assert 'data-grp="ON USD"' in t


@pytest.mark.asyncio
async def test_http_admin_lista_los_codigos_conciliados(carteras, tmp_path, monkeypatch) -> None:
    """/admin · Especies faltantes: la tabla para validar a qué ficha va cada
    código de ESCO, los bonos en dólares que quedaron sin ficha y los códigos
    cuyo ISIN no es el de su ficha."""
    from httpx import ASGITransport, AsyncClient

    from backend.config import settings
    from backend.services import auth

    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "app_users_path", str(tmp_path / "users.json"))
    auth.refresh()
    assert auth.ensure_bootstrapped()["created"]
    from backend.main import app

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            await ac.post("/login", data={"username": "su_test", "password": "clave-de-test-2026!", "next": "/admin"})
            r = await ac.get("/admin/especies-faltantes")
            assert r.status_code == 200
            t = r.text
            assert "Códigos de ESCO → ficha" in t and "3 código(s) conciliado(s)" not in t   # son 4: TTCDOD, GD30D, MGCQOD, YPF34
            assert "4 código(s) conciliado(s)" in t
            for code, ficha in (("TTCDOD", "TTCDC"), ("GD30D", "GD30C"), ("MGCQOD", "MGCQD"), ("YPF34", "YM34C")):
                assert f">{code}</td>" in t and f">{ficha}</td>" in t
            assert "mismo ISIN que la ficha" in t and "USP79171AF45" in t        # CO27D sin ficha, con su motivo
            assert "ISIN de la ficha" in t and "US040114HX11" in t              # GD29: ISIN distinto al de la ficha
    finally:
        auth.refresh()
