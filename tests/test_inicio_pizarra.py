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
