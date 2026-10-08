"""Pizarra de Inicio (07/10): cuadros (libro / cotización) por usuario, default
vacía, un render por tick, persistencia y validaciones."""
from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from backend.services import bond_universe, curves, marketdata_store, pizarra, symbols as syms
from tests.test_historico_writer import auth_on  # noqa: F401 — fixture (muro de login en tmp)

# ruff: noqa: F811 — los fixtures importados se piden por nombre como parámetro (patrón pytest)

_SU = {"username": "su_test", "password": "clave-de-test-2026!"}


@pytest.fixture()
def piz_tmp(tmp_path, monkeypatch):
    p = tmp_path / "pizarra.json"
    monkeypatch.setenv("PIZARRA_PATH", str(p))
    pizarra._version.clear()
    from backend.routes import inicio as rt
    rt._PREFS_MEMO.clear()
    rt._PIZ_MEMO.clear()
    return p


def _client() -> AsyncClient:
    from backend.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


def _un_global() -> str:
    bond_universe.ensure_loaded()
    return curves.build_curve_codes()["globales"][0]


# ── servicio ────────────────────────────────────────────────────────────────
def test_pizarra_default_vacia_valida_y_persiste(piz_tmp) -> None:
    assert pizarra.load_user("ana") == {"y": "tirea", "cuadros": []}
    g = _un_global()
    ent = pizarra.agregar("ana", g.lower(), "libro", "24hs")
    assert ent["cuadros"] == [{"code": g, "tipo": "libro", "plazo": "24hs"}]
    with pytest.raises(pizarra.PizarraError, match="ya está"):
        pizarra.agregar("ana", g, "libro", "24hs")
    with pytest.raises(pizarra.PizarraError, match="no es un bono"):
        pizarra.agregar("ana", "NOEXISTE", "libro")
    with pytest.raises(pizarra.PizarraError):
        pizarra.agregar("ana", g, "grafico")
    pizarra.agregar("ana", g, "cotizacion", "ci")                 # mismo bono, otro tipo: vale
    pizarra.agregar("ana", "TX26", "cotizacion")
    assert [c["plazo"] for c in pizarra.load_user("ana")["cuadros"]] == ["24hs", "CI", "24hs"]
    # mover y quitar
    pizarra.mover("ana", 2, -1)
    assert [c["code"] for c in pizarra.load_user("ana")["cuadros"]] == [g, "TX26", g]
    pizarra.mover("ana", 0, -1)                                    # borde: no pasa nada
    pizarra.quitar("ana", 1)
    assert [c["tipo"] for c in pizarra.load_user("ana")["cuadros"]] == ["libro", "cotizacion"]
    pizarra.quitar("ana", 99)                                      # fuera de rango: no pasa nada
    # métrica por usuario
    pizarra.set_metrica("ana", "margen")
    assert pizarra.load_user("ana")["y"] == "margen"
    with pytest.raises(pizarra.PizarraError):
        pizarra.set_metrica("ana", "bps")
    # otro usuario no ve nada; la versión sube con cada mutación
    assert pizarra.load_user("juan")["cuadros"] == [] and pizarra.version("ana") >= 7
    raw = json.loads(piz_tmp.read_text(encoding="utf-8"))
    assert set(raw["users"]) == {"ana"} and raw["users"]["ana"]["y"] == "margen"
    # tope
    for i in range(pizarra.MAX_CUADROS):
        try:
            pizarra.agregar("pepe", _un_global(), "libro", "24hs" if i % 2 else "CI")
        except pizarra.PizarraError:
            break
    pizarra.limpiar("pepe")
    assert pizarra.load_user("pepe")["cuadros"] == []


def test_archivo_corrupto_se_aparta_y_arranca_vacio(piz_tmp) -> None:
    piz_tmp.write_text("{no es json", encoding="utf-8")
    assert pizarra.load_user("ana") == {"y": "tirea", "cuadros": []}
    assert any(p.name.startswith("pizarra.json.corrupto") for p in piz_tmp.parent.iterdir())
    # basura dentro de la estructura se filtra sin romper
    piz_tmp.write_text(json.dumps({"users": {"ana": {"y": "zzz", "cuadros": [{"code": "gd30", "tipo": "libro"},
                                                                              {"tipo": "libro"}, "x", {"code": "AL30", "tipo": "raro"}]}}}),
                       encoding="utf-8")
    assert pizarra.load_user("ana") == {"y": "tirea", "cuadros": [{"code": "GD30", "tipo": "libro", "plazo": "24hs"}]}


# ── HTTP ────────────────────────────────────────────────────────────────────
def _sembrar(code: str) -> None:
    from backend.tools.bench_tick import _precio_para
    px = _precio_para(code, {}) or 100.0
    marketdata_store.get_store().update_from_md(syms.md_symbol(code, "24hs"), {
        "LA": {"price": round(px, 3), "size": 100, "date": "2026-10-06T14:00:00-03:00"},
        "CL": {"price": round(px * 0.995, 3), "date": "2026-10-05"},
        "OP": {"price": round(px * 0.997, 3)}, "HI": {"price": round(px * 1.004, 3)}, "LO": {"price": round(px * 0.993, 3)},
        "BI": [{"price": round(px * (1 - 0.002 * k), 3), "size": 1e5 * k} for k in range(1, 4)],
        "OF": [{"price": round(px * (1 + 0.002 * k), 3), "size": 1e5 * k} for k in range(1, 4)],
        "NV": {"size": 5e6}, "EV": {"size": 5e6 * px / 100}})


@pytest.mark.asyncio
async def test_pizarra_por_usuario_libro_cotizacion_y_render_compartido(piz_tmp, auth_on) -> None:
    from backend.routes import inicio as rt
    g = _un_global()
    _sembrar(g)
    _sembrar("TX26")
    async with _client() as su:
        r = await su.post("/login", data=_SU)
        assert r.status_code == 303
        await su.post("/admin/users", data={"username": "juan", "password": "clave123", "role": "basico", "email": ""})
        # el superuser arranca sin cuadros
        page = await su.get("/inicio")
        assert page.status_code == 200 and "Tu pizarra está vacía" in page.text
        assert 'id="piz-codes"' in page.text and 'hx-post="/inicio/pizarra/agregar"' in page.text
        assert 'hx-get="/inicio/pizarra"' in page.text
    async with _client() as ac:
        r = await ac.post("/login", data={"username": "juan", "password": "clave123"})
        assert r.status_code == 303
        r = await ac.get("/inicio/pizarra")
        assert r.status_code == 200 and "Tu pizarra está vacía" in r.text
        # agregar un libro: la respuesta ya trae el libro embebido, sin auto-refresh propio ni chips
        r = await ac.post("/inicio/pizarra/agregar", data={"code": g.lower(), "tipo": "libro", "plazo": "24hs"})
        assert r.status_code == 200 and f"Libro · {g}" in r.text and "piz-libro" in r.text
        assert 'hx-get="/mercado/book/' not in r.text and "book-y" not in r.text
        assert 'hx-post="/inicio/pizarra/quitar"' in r.text and "Bid TIREA" in r.text
        # el GET inmediato (misma seq) refleja el cuadro nuevo: el memo se invalida por la firma del archivo
        r2 = await ac.get("/inicio/pizarra")
        assert f"Libro · {g}" in r2.text
        # agregar una cotización
        r = await ac.post("/inicio/pizarra/agregar", data={"code": "TX26", "tipo": "cotizacion", "plazo": "24hs"})
        assert r.status_code == 200 and "piz-cot" in r.text and 'href="/yas?code=TX26"' in r.text and "Compra" in r.text
        # duplicado → aviso, la pizarra sigue igual
        r = await ac.post("/inicio/pizarra/agregar", data={"code": "TX26", "tipo": "cotizacion", "plazo": "24hs"})
        assert "ya está en tu pizarra" in r.text and r.text.count("piz-item") >= 2
        # bono inexistente → aviso
        r = await ac.post("/inicio/pizarra/agregar", data={"code": "ZZZZ", "tipo": "libro", "plazo": "24hs"})
        assert "no es un bono de la app" in r.text
        # métrica para todos los libros
        r = await ac.post("/inicio/pizarra/metrica", data={"y": "tem"})
        assert r.status_code == 200 and "Bid TEM" in r.text
        # mover y quitar
        r = await ac.post("/inicio/pizarra/mover", data={"idx": 1, "delta": -1})
        assert r.text.find("piz-cot") < r.text.find("piz-libro")
        r = await ac.post("/inicio/pizarra/quitar", data={"idx": 0})
        assert "piz-cot" not in r.text and f"Libro · {g}" in r.text
        # render compartido entre refrescos con la seq quieta
        rt.piz_stats.update(hit=0, miss=0)
        a = await ac.get("/inicio/pizarra")
        b = await ac.get("/inicio/pizarra")
        assert a.text == b.text and rt.piz_stats["hit"] >= 1
        # un tick invalida
        marketdata_store.get_store().update_from_md(syms.md_symbol(g, "24hs"), {"NV": {"size": 6e6}})
        rt.piz_stats.update(hit=0, miss=0)
        await ac.get("/inicio/pizarra")
        assert rt.piz_stats["miss"] == 1
        # la página de Inicio del usuario trae su pizarra ya renderizada
        page = await ac.get("/inicio")
        assert f"Libro · {g}" in page.text and "Tu pizarra está vacía" not in page.text
    # el superuser sigue sin cuadros (es por usuario)
    async with _client() as su:
        await su.post("/login", data=_SU)
        r = await su.get("/inicio/pizarra")
        assert "Tu pizarra está vacía" in r.text
        assert pizarra.usuarios_con_cuadros() == ["juan"]


def _render_book(piz) -> str:
    """El partial del libro con una tenencia sintética: el mismo template que
    Mercado / Órdenes, embebido (`piz`) o no."""
    from backend.main import app
    tpl = app.state.templates.env.get_template("partials/mercado_book.html")
    return tpl.render(code="GD30", plazo="24hs", leg="native", fuente="byma", y="tirea", y_label="TIREA",
                      nombre="Global 2030", symbol="MERV - XMEV - GD30 - 24hs", row=None,
                      bids=[{"price": 100.0, "size": 1000, "cum": 1000, "frac": 1.0, "own": None, "tirea": 0.10}],
                      offers=[{"price": 101.0, "size": 2000, "cum": 2000, "frac": 1.0, "own": None, "tirea": 0.09}],
                      instr=None, margen_ok=False, piz=piz,
                      position={"total_cantidad": 1000, "n_fondos": 1,
                                "funds": [{"nombre": "Delta Ahorro", "cantidad": 1000, "valor": 1234, "pct_pn": 0.01}]})


def test_mi_posicion_plegada_en_la_pizarra_y_abierta_en_mercado() -> None:
    """07/10: en la pizarra la tenencia arranca plegada (pedido del desk); en el
    libro de Mercado / Órdenes sigue abierta. El resto del libro es el MISMO
    (libro completo, no la versión compacta que el desk rechazó)."""
    piz = _render_book({"idx": 0, "n": 1})
    merc = _render_book(None)
    assert "Mi posición · 1.000 VN en 1 fondo" in piz and "Delta Ahorro" in piz
    assert '<details style="margin-top:14px">' in piz and '<details style="margin-top:14px" open>' not in piz
    assert '<details style="margin-top:14px" open>' in merc
    # el libro embebido es el completo: mismas puntas (book-grid) y stats, sin escalera compacta
    assert "book-grid" in piz and "Bid TIREA" in piz and "Offer TIREA" in piz and "piz-ladder" not in piz
    assert "piz-tools" in piz and "piz-tools" not in merc


@pytest.mark.asyncio
async def test_libro_de_mercado_sigue_igual_fuera_de_la_pizarra() -> None:
    """El refactor (book_context) no cambia el libro de Mercado: sigue con su
    auto-refresh, sus chips de métrica y sin botones de pizarra."""
    g = _un_global()
    _sembrar(g)
    async with _client() as ac:
        r = await ac.get(f"/mercado/book/{g}")
        assert r.status_code == 200
        assert f'hx-get="/mercado/book/{g}?plazo=24hs' in r.text and 'y=tirea"' in r.text
        assert 'hx-trigger="md-update from:body, every 30s"' in r.text and "book-y" in r.text
        assert "piz-tools" not in r.text


# ── Auditoría 08/10 (lote seguro) ─────────────────────────────────────────────
def test_pizarra_acepta_codigo_con_sufijo_minuscula_del_universo(piz_tmp) -> None:
    """A09: una variante del universo con sufijo en MINÚSCULA (proyectada /
    dual, p. ej. PBA28j) no debe rechazarse por uppercasear a ciegas; se
    canoniza al código real tanto si entra en may como en min."""
    bond_universe.ensure_loaded()
    cod = next((c for c in bond_universe.all_codes() if c != c.upper()), None)
    if cod is None:
        pytest.skip("el universo no tiene códigos con minúscula")
    ent = pizarra.agregar("ana", cod.upper(), "cotizacion", "24hs")   # entra en MAYÚSCULAS
    assert ent["cuadros"][-1]["code"] == cod                          # → código real del universo
    ent = pizarra.agregar("ana", cod.lower(), "libro")                # y en minúsculas
    assert ent["cuadros"][-1]["code"] == cod


def test_pizarra_no_pisa_json_corrupto_si_no_puede_apartarlo(piz_tmp, monkeypatch) -> None:
    """A08: JSON corrupto que NO se puede mover a cuarentena → la mutación
    aborta (OSError) en vez de sobrescribirlo con sólo el usuario que guarda
    (perdería las pizarras de los demás). El archivo corrupto queda intacto."""
    original = '{"users": {"otro": ESTO-NO-ES-JSON'
    piz_tmp.write_text(original, encoding="utf-8")
    import backend.services.archivos as arch
    monkeypatch.setattr(arch, "apartar_corrupto", lambda p, motivo="": None)   # la cuarentena falla
    with pytest.raises(OSError):
        pizarra.agregar("ana", _un_global(), "libro")
    assert piz_tmp.read_text(encoding="utf-8") == original                     # NO se pisó


@pytest.mark.asyncio
async def test_pizarra_cache_se_invalida_al_cambiar_permisos(piz_tmp, auth_on) -> None:
    """A04: el HTML de la pizarra (tenencia filtrada por fondos, marcas de orden
    propia) se cachea por usuario+seq. Revocar fondos con la seq quieta NO debe
    seguir sirviendo el HTML viejo: la clave incluye la huella de permisos."""
    from backend.routes import inicio as rt
    from backend.services import auth
    g = _un_global()
    _sembrar(g)
    async with _client() as su:
        await su.post("/login", data=_SU)
        await su.post("/admin/users", data={"username": "lu", "password": "clave123", "role": "premium", "email": ""})
    async with _client() as ac:
        await ac.post("/login", data={"username": "lu", "password": "clave123"})
        await ac.post("/inicio/pizarra/agregar", data={"code": g.lower(), "tipo": "libro", "plazo": "24hs"})
        rt.piz_stats.update(hit=0, miss=0)
        await ac.get("/inicio/pizarra")
        await ac.get("/inicio/pizarra")
        assert rt.piz_stats["hit"] >= 1                       # cacheado (seq quieta)
        auth.set_visible_fondos("lu", [])                     # revoco fondos (no toca prefs ni seq)
        rt.piz_stats.update(hit=0, miss=0)
        await ac.get("/inicio/pizarra")
        assert rt.piz_stats["miss"] == 1                      # la clave de permisos cambió → re-render


@pytest.mark.asyncio
async def test_libro_no_filtra_ordenes_propias_a_rol_sin_oms(piz_tmp, auth_on) -> None:
    """A05: el tamaño de las órdenes propias de la mesa es confidencial (como
    /ordenes). El libro se reusa en Inicio/Mercado (accesibles a un básico), así
    que un rol SIN OMS no debe ver las marcas de orden propia; uno con OMS sí."""
    from backend.services import oms
    from backend.tools.bench_tick import _precio_para
    g = _un_global()
    _sembrar(g)
    px = _precio_para(g, {}) or 100.0
    top_bid = round(px * (1 - 0.002), 3)                      # mejor punta comprada por _sembrar
    oms._OWN.clear()
    oms.recordar_propia({"symbol": syms.md_symbol(g, "24hs"), "side": "buy",
                         "price": top_bid, "qty": 77777, "client_order_id": "AUDIT-A05"})
    try:
        assert oms.own_levels(syms.md_symbol(g, "24hs"))["buy"]            # precondición: el seed matchea un nivel
        async with _client() as su:
            await su.post("/login", data=_SU)
            await su.post("/admin/users", data={"username": "baz", "password": "clave123", "role": "basico", "email": ""})
            r = await su.get(f"/mercado/book/{g}")
            assert r.status_code == 200 and "own-order" in r.text and "77.777" in r.text    # superuser SÍ ve
        async with _client() as ac:
            await ac.post("/login", data={"username": "baz", "password": "clave123"})
            assert (await ac.get("/ordenes")).status_code == 403                            # básico sin OMS
            r = await ac.get(f"/mercado/book/{g}")
            assert r.status_code == 200 and "own-order" not in r.text and "77.777" not in r.text   # NO ve las propias
    finally:
        oms._OWN.clear()
