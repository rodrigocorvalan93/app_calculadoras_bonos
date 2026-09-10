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
        "CodFondo": [5, 18, 18], "Cod_Delta": ["AL30", "TX26", "ZZZZ9"],
        "Especie": ["BONAR 2030", "BONCER 2026", "ON DESCONOCIDA 2031"],
        "Cantidad": [1_000_000.0, 2_000_000.0, 50_000.0],
        "Valor": [8.4e8, 1.5e9, 1.0e6],
        "Clase de Activo": ["Soberano USD", "CER", "ON"],
    }).to_excel(d / "Delta_Composicion.xlsx", sheet_name="Sheet1", index=False)
    pd.DataFrame({"CodFondo": [5, 18], "PN": [5e10, 9e9]}).to_excel(
        d / "Delta_PN.xlsx", sheet_name="Sheet1", index=False)


def _galileo_files(d, isin_local: str, venc_fantasma=None) -> None:
    filas = [
        # (cod, fondo, descripcion, isin, instrumento, clase, cant, valor)
        (5, "GALILEO AHORRO", "Bonar 2030 (local)", isin_local,
         "Bonos Soberano", "Soberano USD MEP", 300_000.0, 2.5e8),
        (5, "GALILEO AHORRO", "BC Avianca 9.5% 28 01 2031", "USG2957NAD33",
         "Bonos Corporativo", "Bonos Corporativo USD", 1_500_000.0, 1.35e6),
        (2, "GALILEO EVENT DRIVEN", "BC Petroleos Mexicanos 28 01 2060", "US71654QDF63",
         "Bonos Corporativo", "Bonos Corporativo USD", 2_000_000.0, 1.64e6),
        # Acciones con los tres formatos reales de descripción:
        (8, "GALILEO ACCIONES", "BBAR AR / BBVA BANCO FRANCES SA", "ARP125991090",
         "Acciones", "Acciones", 10_000.0, 9.0e7),
        (8, "GALILEO ACCIONES", "GGAL AR / GRUPO FINANCIERO GALICIA-B", "ARP495251018",
         "Acciones", "Acciones", 5_000.0, 8.0e7),
        (8, "GALILEO ACCIONES", "GRUPO CONCESIONARIO DEL OESTE S.A. (OEST)", "ARGCAO010012",
         "Acciones", "Acciones", 3_000.0, 2.0e7),
        (8, "GALILEO ACCIONES", "Boldt Gaming SA", "ARBOLG010010",
         "Acciones", "Acciones", 4_000.0, 1.0e7),
        # Cheque garantizado: NO es especie de mercado (no ensucia nada)
        (8, "GALILEO ACCIONES", "*BIS131000155", None,
         "Cheques Garantizados", None, None, 5.0e6),
        # Bono local SIN ficha en especies.py → 'sin normalizar' en el reporte
        (8, "GALILEO ACCIONES", "ON Fantasma 2031", "ARFAKE000012",
         "Bonos Corporativo", "Bonos Corporativo USD", 100_000.0, 3.0e6),
    ]
    pd.DataFrame({
        "Fecha": ["2026-09-08"] * len(filas),
        "CodFondo": [f[0] for f in filas],
        "fondo": [f[1] for f in filas],
        "descripcion": [f[2] for f in filas],
        "isin": [f[3] for f in filas],
        "instrumento": [f[4] for f in filas],
        "Clasifica_Ficha": [f[5] for f in filas],
        "cantidad": [f[6] for f in filas],
        "valor": [f[7] for f in filas],
        # vencimiento sólo en la ON fantasma → el reporte sugiere candidatas
        "vencimiento": [pd.Timestamp(venc_fantasma) if (venc_fantasma and f[2] == "ON Fantasma 2031") else pd.NaT
                        for f in filas],
    }).to_excel(d / "Galileo_Composicion.xlsx", sheet_name="Sheet1", index=False)
    pd.DataFrame({"CodFondo": [5, 2, 8], "PN": [3.7e10, 2.8e8, 1.1e11]}).to_excel(
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
    v = getattr(bond_universe.get("TX26"), "vencimiento", None)
    _galileo_files(tmp_path, _isin_al30(),
                   venc_fantasma=(v.date() if hasattr(v, "date") else v))
    positions.refresh()
    yield tmp_path
    with positions._lock:
        positions._cache = None       # el próximo test recarga su propio estado


def test_carga_galileo_junto_a_delta(carteras) -> None:
    fs = positions.fondos()
    cods = {f["cod"] for f in fs}
    assert cods == {5, 18, G + 2, G + 5, G + 8}
    por_cod = {f["cod"]: f for f in fs}
    # labels: Delta intacto; Galileo con prefijo G + nombre de la col `fondo`
    assert por_cod[5]["nombre"] == "5 — Pesos"
    assert por_cod[G + 5]["nombre"] == "G5 — GALILEO AHORRO"
    assert por_cod[G + 2]["nombre"] == "G2 — GALILEO EVENT DRIVEN"
    # PN por familia sin pisarse (el 5 existe en ambas)
    assert por_cod[5]["pn"] == 5e10 and por_cod[G + 5]["pn"] == 3.7e10
    st = positions.status()
    assert st["n_fondos_galileo"] == 3 and st["error"] is None
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


def test_normalizacion_acciones_esquema_delta(carteras) -> None:
    """Lo que pidió el desk: 'BBAR AR / BBVA…' debe quedar SOLO 'BBAR AR'
    (esquema Delta), más el ticker entre paréntesis y el alias por ISIN."""
    hs = positions.holdings(G + 8)
    por_esp = {h["especie"]: h for h in hs}
    assert "BBAR AR" in por_esp and por_esp["BBAR AR"]["cod_delta"] == "BBAR"
    assert "GGAL AR" in por_esp and por_esp["GGAL AR"]["cod_delta"] == "GGAL"
    oeste = next(h for h in hs if "OESTE" in h["especie"])
    assert oeste["cod_delta"] == "OEST"                # "(OEST)" al final
    boldt = next(h for h in hs if "Boldt" in h["especie"])
    assert boldt["cod_delta"] == "BOLT"                # alias semidefinitivo
    cheque = next(h for h in hs if h["especie"].startswith("*BIS"))
    assert cheque["es_especie"] is False and cheque["cod_delta"] is None


def test_isin_ambiguo_no_mapea(carteras) -> None:
    """especies.py arrastra ISINs copy-pasteados entre bonos DISTINTOS
    (GD29/GD30): mapearlos agregaría la posición al bono equivocado en
    silencio → quedan afuera del mapa (y visibles en el reporte)."""
    gd30 = getattr(bond_universe.get("GD30"), "isin", None)
    gd29 = getattr(bond_universe.get("GD29"), "isin", None)
    if not gd30 or gd30 != gd29:
        pytest.skip("especies.py ya no comparte el ISIN GD29/GD30")
    assert positions._isin_a_ticker().get(str(gd30).upper()) is None


def test_reporte_especies_faltantes(carteras) -> None:
    rep = positions.especies_faltantes()
    falt = {r["code"]: r for r in rep["faltantes"]}
    # ticker de Delta que la app no conoce → faltante, con su familia
    assert "ZZZZ9" in falt and falt["ZZZZ9"]["familias"] == "Delta"
    # una acción normalizada y conocida por los paneles NO es faltante
    assert "GGAL" not in falt and "BBAR" not in falt
    # bono Galileo con ISIN sin ficha → 'sin normalizar', con el ISIN a mano
    sin = {r["especie"]: r for r in rep["sin_map"]}
    assert "ON Fantasma 2031" in sin
    assert sin["ON Fantasma 2031"]["isin"] == "ARFAKE000012"
    # cheques/cash no ensucian el reporte
    assert not any(str(r["especie"]).startswith("*BIS") for r in rep["sin_map"])


def test_matriz_sin_cheques_familias_y_delta_primero(carteras) -> None:
    """La lentitud de la matriz: los cheques de Galileo metían ~1.100 filas
    únicas. Afuera. Además: switch por familia y especies con presencia
    Delta primero (prevalece el esquema Delta)."""
    from backend.routes.posiciones import _matriz_ctx

    ctx = _matriz_ctx(None, "todos")
    especies = [r["especie"] for r in ctx["rows"]]
    assert not any(str(e).startswith("*BIS") for e in especies)     # cheques afuera
    assert "AL30" in especies and "BBAR" in especies
    assert "BBAR AR / BBVA BANCO FRANCES SA" not in especies        # normalizada
    # abreviatura + nombre completo en columnas separadas
    bbar = next(r for r in ctx["rows"] if r["especie"] == "BBAR")
    assert bbar["abrev"] == "BBAR" and bbar["nombre"] == "BBVA BANCO FRANCES SA"
    al30 = next(r for r in ctx["rows"] if r["especie"] == "AL30")
    assert al30["abrev"] == "AL30" and al30["nombre"] == "BONAR 2030"   # el de Delta prevalece
    fantasma = next(r for r in ctx["rows"] if "Fantasma" in r["especie"])
    assert fantasma["abrev"] == "—" and fantasma["nombre"] == "ON Fantasma 2031"
    solo_g = [r["solo_galileo"] for r in ctx["rows"]]
    assert solo_g == sorted(solo_g)                                 # Delta primero
    assert next(r for r in ctx["rows"] if r["especie"] == "AL30")["solo_galileo"] is False

    d = _matriz_ctx(None, "delta")
    assert all(not positions.es_galileo(f["cod"]) for f in d["fondos"])
    assert "BBAR" not in [r["especie"] for r in d["rows"]]          # sólo-Galileo afuera
    g = _matriz_ctx(None, "galileo")
    assert all(positions.es_galileo(f["cod"]) for f in g["fondos"])
    assert "TX26" not in [r["especie"] for r in g["rows"]]          # sólo-Delta afuera
    assert "AL30" in [r["especie"] for r in g["rows"]]              # compartida queda


def test_reporte_sugiere_candidatas_por_vencimiento(carteras) -> None:
    """Las filas sin normalizar sugieren fichas con el MISMO vencimiento —
    sugerencia, nunca mapeo automático (T15E7 y D15E7 vencen el mismo día)."""
    rep = positions.especies_faltantes()
    sin = {r["especie"]: r for r in rep["sin_map"]}
    assert "TX26" in (sin["ON Fantasma 2031"]["candidatos"] or "")


@pytest.mark.asyncio
async def test_http_matriz_familia(carteras) -> None:
    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/matriz/table", params={"familia": "galileo", "view": "vn"})
        assert r.status_code == 200 and "GALILEO AHORRO" in r.text
        assert "*BIS" not in r.text
        page = await ac.get("/matriz", params={"familia": "delta"})
        assert page.status_code == 200 and "Sólo Delta" in page.text


@pytest.mark.asyncio
async def test_http_admin_reporte_especies(carteras, tmp_path, monkeypatch) -> None:
    """El reporte vive en el panel de control: 403 sin sesión de superuser,
    200 con login (bootstrap) y muestra el ticker faltante."""
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
            await ac.post("/login", data={"username": "rodricor93",
                                          "password": "Rc_874562", "next": "/admin"})
            ok = await ac.get("/admin/especies-faltantes")
            assert ok.status_code == 200 and "ZZZZ9" in ok.text
            page = await ac.get("/admin")
            assert "Especies faltantes" in page.text
    finally:
        auth.refresh()


@pytest.mark.asyncio
async def test_http_posiciones_fondo_galileo(carteras) -> None:
    from backend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/posiciones", params={"fondo": G + 5})
        assert r.status_code == 200 and "GALILEO AHORRO" in r.text
        t = await ac.get("/posiciones/table", params={"fondo": G + 5})
        assert t.status_code == 200
        # tabla de posiciones con Abreviatura + Nombre completo (como matriz)
        t8 = await ac.get("/posiciones/table", params={"fondo": G + 8})
        assert t8.status_code == 200
        assert ">Nombre</th>" in t8.text
        assert "BBVA BANCO FRANCES SA" in t8.text      # razón social en col. Nombre
        import re as _re
        assert _re.search(r">\s*BBAR\s*<", t8.text)    # celda Especie = abreviatura
