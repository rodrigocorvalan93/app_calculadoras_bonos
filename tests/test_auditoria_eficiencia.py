"""Regresiones de la auditoría de eficiencia (17/09/2026):

E01 · el delta de Mercado hace swap completo cuando cambian los índices sin tick
E02 · esperar un cálculo compartido no ocupa workers del pool (AsyncSingleFlight)
E04 · /historicos/data convierte cada fecha una vez, arma en el pool y memoiza
E06 · el kill-switch / LIVE cambian ya y el audit no bloquea el event loop
E07 · una valuación genera los cashflows una sola vez, con los mismos números
E08 · un solo build del snapshot de Excel por key; ?codes= por lookup directo
E09 · la poda de locks del cache conserva los que están en uso
E03/E05 · motor live y gráficos (harness JS: tests/live_engine_harness.cjs)
+ OMS.MARGEN en el add-in (margen TNA de floaters vía /excel/v1/calc)
"""
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from backend.cache import AsyncSingleFlight, LockedTTLCache
from backend.config import settings

ROOT = Path(__file__).resolve().parent.parent


def _client() -> AsyncClient:
    from backend.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


# ── E09 · locks de cómputo con refcount ──────────────────────────────────────
def test_e09_la_poda_conserva_el_lock_de_un_calculo_en_curso() -> None:
    # maxsize 2: con "vieja" cacheada y "activa" en curso, la key "fallida"
    # deja 3 locks > 2 y dispara la poda con la fábrica de "activa" en vuelo.
    cache = LockedTTLCache(2, 3600)
    cache.get_or_compute("vieja", lambda: 1)
    entro, soltar, cuenta = threading.Event(), threading.Event(), []

    def fabrica():
        cuenta.append(1)
        if len(cuenta) == 1:
            entro.set()
            assert soltar.wait(5)
        return 42

    with ThreadPoolExecutor(2) as pool:
        primero = pool.submit(cache.get_or_compute, "activa", fabrica)
        assert entro.wait(5)
        cache.get_or_compute("fallida", lambda: None)      # otra key dispara la poda con la fábrica en curso
        segundo = pool.submit(cache.get_or_compute, "activa", fabrica)
        time.sleep(0.2)
        assert not segundo.done()                          # espera al productor: no computa en paralelo
        soltar.set()
        assert primero.result(5) == segundo.result(5) == 42
    assert len(cuenta) == 1
    # sin usuarios ni entrada, el lock se va; con entrada cacheada se conserva
    assert "fallida" not in cache._compute_locks and "activa" in cache._compute_locks
    assert cache._compute_locks["activa"][1] == 0


def test_e09_control_compute_once_sin_eviccion() -> None:
    cache = LockedTTLCache(16, 3600)
    llamadas = []

    def build():
        llamadas.append(1)
        time.sleep(0.02)
        return 42

    with ThreadPoolExecutor(8) as pool:
        assert list(pool.map(lambda _: cache.get_or_compute("x", build), range(8))) == [42] * 8
    assert len(llamadas) == 1
    cache.clear()
    assert not cache._compute_locks


# ── E02 · single-flight async antes del pool ─────────────────────────────────
@pytest.mark.asyncio
async def test_e02_esperadores_identicos_no_ocupan_el_pool() -> None:
    from backend.routes import curves as cr, total_return as tr
    from backend.services import total_return as svc

    key = ("test-e02", time.monotonic())
    soltar, entro, cuenta = threading.Event(), threading.Event(), []

    def caro():
        cuenta.append(1)
        entro.set()
        assert soltar.wait(5)
        return 42

    vuelo = AsyncSingleFlight()
    tareas = [asyncio.ensure_future(vuelo.run(key, cr._row_pool, lambda: tr._cached_or(key, caro))) for _ in range(8)]
    await asyncio.get_running_loop().run_in_executor(None, entro.wait, 5)
    assert len(vuelo) == 1
    # con un solo productor en el pool, un trabajo ajeno (el libro) entra enseguida
    t0 = time.monotonic()
    ajeno = await asyncio.wait_for(asyncio.get_running_loop().run_in_executor(cr._row_pool, lambda: "libro"), 2.0)
    assert ajeno == "libro" and time.monotonic() - t0 < 1.0
    soltar.set()
    assert await asyncio.gather(*tareas) == [42] * 8
    assert len(cuenta) == 1 and len(vuelo) == 0
    assert svc._cache.get(key) == 42
    # la cancelación de UN esperador no cancela el cálculo compartido
    key2 = ("test-e02b", time.monotonic())
    soltar2 = threading.Event()

    def caro2():
        assert soltar2.wait(5)
        return 7

    a = asyncio.ensure_future(vuelo.run(key2, cr._row_pool, caro2))
    b = asyncio.ensure_future(vuelo.run(key2, cr._row_pool, caro2))
    await asyncio.sleep(0.05)
    a.cancel()
    soltar2.set()
    assert await b == 7


# ── E06 · kill-switch / LIVE sin bloquear el loop ────────────────────────────
@pytest.mark.asyncio
async def test_e06_kill_switch_cambia_ya_y_no_bloquea_el_loop(monkeypatch, tmp_path) -> None:
    from starlette.requests import Request
    from starlette.responses import HTMLResponse
    from backend.routes import ordenes
    from backend.services import oms

    monkeypatch.setattr(settings, "auth_enabled", False)
    monkeypatch.setattr(ordenes, "_render", lambda *a, **kw: HTMLResponse("ok"))
    monkeypatch.setattr(oms, "_AUDIT_PATH", tmp_path / "audit.jsonl")
    visto = {}
    orig = oms.audit

    def audit_lento(event, data):
        visto["flag_al_escribir"] = oms._kill["on"]
        time.sleep(0.2)                                   # disco lento / OneDrive / lock ocupado
        orig(event, data)

    monkeypatch.setattr(oms, "audit", audit_lento)
    req = Request({"type": "http", "method": "POST", "path": "/ordenes/kill", "headers": []})
    t0 = time.perf_counter()
    esperas = []

    async def sonda():
        await asyncio.sleep(0.01)
        esperas.append(time.perf_counter() - t0)

    s = asyncio.create_task(sonda())
    await asyncio.sleep(0)
    try:
        await ordenes.ordenes_kill(req, on="1")
        await s
        assert oms._kill["on"] is True and visto["flag_al_escribir"] is True   # el freno va ANTES del write
        assert esperas[0] < 0.1, f"el loop esperó {esperas[0] * 1000:.0f} ms al audit síncrono"
        assert any(json.loads(ln)["event"] == "kill_switch" for ln in (tmp_path / "audit.jsonl").read_text().splitlines())
        # LIVE: mismo patrón (apagar es inmediato)
        assert (await oms.set_live_async(False, user="t")) is False
    finally:
        oms.kill_switch(False)
        oms.set_live(None)


# ── E08 · snapshot de Excel: un build por key ────────────────────────────────
def test_e08_snapshot_excel_un_solo_build_por_key(monkeypatch) -> None:
    from backend.routes import excel

    excel._cache.clear()
    excel._build_locks.clear()
    cuenta, barrera = [], threading.Barrier(8)

    def build(codes):
        cuenta.append(1)
        try:
            barrera.wait(timeout=0.15)     # con single-flight nadie más llega: vence
        except threading.BrokenBarrierError:
            pass
        return {"seq": 0, "quotes": {}}

    monkeypatch.setattr(excel, "_build", build)
    with ThreadPoolExecutor(8) as pool:
        respuestas = list(pool.map(lambda _: excel._snapshot_bytes("GD30C"), range(8)))
    assert len(set(respuestas)) == 1 and len(cuenta) == 1
    # keys distintas no se bloquean entre sí
    cuenta.clear()
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(excel._snapshot_bytes, ["AL30D", "TX26"]))
    assert len(cuenta) == 2
    excel._cache.clear()
    excel._build_locks.clear()


def test_e08_filtro_codes_por_lookup_directo(monkeypatch) -> None:
    from backend.routes import excel
    from backend.services import marketdata_store as mds

    st = mds.MarketDataStore()
    monkeypatch.setattr(mds, "_store", st)
    for code, px in (("GD30", 60.0), ("AL30", 55.0), ("TX26", 1200.0)):
        st.update_from_md(f"MERV - XMEV - {code} - 24hs", {"LA": {"price": px, "size": 1000, "date": "1"}})
    st.update_from_md("MERV - XMEV - GD30 - CI", {"LA": {"price": 59.5, "size": 10, "date": "1"}})
    llamadas = []
    orig = st.get_many

    def get_many(symbols):
        llamadas.append(len(list(symbols)))
        return orig(symbols)

    monkeypatch.setattr(st, "get_many", get_many)
    d = excel._build(frozenset({"GD30", "NOEXISTE"}))
    assert set(d["quotes"]) == {"GD30"} and set(d["quotes"]["GD30"]) == {"24hs", "CI"}
    assert d["quotes"]["GD30"]["24hs"]["last"] == 60.0 and d["extras"] == {}
    assert not llamadas                                    # no recorrió el store entero
    full = excel._build(None)
    assert set(full["quotes"]) == {"GD30", "AL30", "TX26"} and llamadas


# ── E07 · cashflows una sola vez por valuación, mismos números ───────────────
_PRECIOS_MUESTRA = {"GD30C": 62.0, "AL30D": 58.0, "TX26": 1250.0, "TTM26": 100.0, "PBA28j": 78.0}


def _codigos_muestra():
    from backend.services import bond_universe
    codes = bond_universe.all_codes()
    return [c for c in _PRECIOS_MUESTRA if c in codes][:4]


def test_e07_una_valuacion_genera_los_flujos_una_vez_y_da_lo_mismo(monkeypatch) -> None:
    import rentafija
    from backend.services import pricing

    codes = _codigos_muestra()
    assert codes, "sin bonos de muestra en el universo"
    settle = pricing.settlement_date_str("24hs")
    gens = []
    orig = rentafija.Bono.generate_cashflows

    def contado(self, settlement_date=None):
        gens.append(getattr(self, "codigo", "?"))
        return orig(self, settlement_date)

    monkeypatch.setattr(rentafija.Bono, "generate_cashflows", contado)
    for code in codes:
        gens.clear()
        m = pricing.compute_metrics(code, "precio", _PRECIOS_MUESTRA[code], settle=settle, include_cashflows=False)
        assert not m.get("error"), (code, m.get("error"))
        assert len(gens) == 1, (code, gens)                # antes: 2 (tirea + intereses corridos)
        gens.clear()
        m2 = pricing.compute_metrics(code, "tir", m["tirea"], settle=settle, include_cashflows=False)
        assert not m2.get("error") and len(gens) == 1
        assert m2["precio"] == pytest.approx(m["precio"], rel=1e-5)   # round-trip precio→TIR→precio (tolerancia del Newton)
    monkeypatch.undo()
    # equivalencia numérica: intereses corridos reutilizando los flujos ==
    # regenerándolos (mismo objeto, misma fecha), en todos los atributos
    for code in codes:
        a = pricing._bond_obj_copy(code)
        b = pricing._bond_obj_copy(code)
        a.generate_cashflows(settle)
        ic_a = a.calcula_intereses_corridos(settle, _flujos_generados=True)
        ic_b = b.calcula_intereses_corridos(settle)
        assert ic_a == pytest.approx(ic_b, rel=1e-12, abs=1e-12)
        for attr in ("valor_tecnico", "dias_corridos", "dias_remanentes", "ultimo_cupon", "proximo_cupon", "valor_residual"):
            assert getattr(a, attr) == getattr(b, attr), (code, attr)
        assert a.cashflow_cpn.equals(b.cashflow_cpn)


def test_e07_paralelo_igual_a_secuencial() -> None:
    from backend.services import pricing

    codes = _codigos_muestra()
    settle = pricing.settlement_date_str("24hs")

    def calc(args):
        code, p = args
        return pricing.compute_metrics(code, "precio", p, settle=settle)

    trabajos = [(c, _PRECIOS_MUESTRA[c] * (0.9 + i * 0.03)) for c in codes for i in range(8)]
    serial = [calc(t) for t in trabajos]
    with ThreadPoolExecutor(4) as pool:
        paralelo = list(pool.map(calc, trabajos))
    for s, p in zip(serial, paralelo):
        assert not s.get("error") and not p.get("error")
        for k in ("tirea", "tna", "precio", "duration", "intereses_corridos", "paridad"):
            assert s[k] == pytest.approx(p[k], rel=1e-10, abs=1e-10), k
        assert s["cashflows"] == p["cashflows"]


# ── E01 · delta de Mercado con la huella de índices ──────────────────────────
@pytest.mark.asyncio
async def test_e01_delta_pide_swap_completo_cuando_cambian_los_indices(monkeypatch) -> None:
    from backend.routes import curves as cr
    from backend.services import pricing

    async def _rows_for(curve, plazo, only_quoting, leg, book=True, fuente="byma"):
        return [{"code": "T30E6", "seq": 1}, {"code": "S31L6", "seq": 1}], {"n": 2}

    huella = [("a",)]
    monkeypatch.setattr(cr, "_rows_for", _rows_for)
    monkeypatch.setattr(pricing, "indices_token", lambda: huella[0])
    cr._ROWS_CACHE.clear()
    cr._ROWS_IDX.clear()
    try:
        _s, _r, _m, h1 = await cr._rows_en_seq("cer", "24hs", False, "native", "byma", "", 0)
        async with _client() as ac:
            r = await ac.get(f"/mercado/rows?curve=cer&plazo=24hs&only_quoting=false&leg=native&since=99&order={h1}")
            assert r.status_code == 200 and r.headers.get("X-Full") is None     # mismos índices: delta normal
            huella[0] = ("b",)                                                   # refresh de índices, feed quieto
            r = await ac.get(f"/mercado/rows?curve=cer&plazo=24hs&only_quoting=false&leg=native&since=99&order={h1}")
            assert r.headers.get("X-Full") == "1"                                # swap completo: TIR nueva a la vista
        _s, _r, _m, h2 = await cr._rows_en_seq("cer", "24hs", False, "native", "byma", "", 0)
        assert h2 != h1
    finally:
        cr._ROWS_CACHE.clear()
        cr._ROWS_IDX.clear()


# ── E04 · /historicos/data ───────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_e04_historicos_data_una_conversion_por_punto_y_memo(monkeypatch) -> None:
    from backend.routes import historico as hr
    from backend.services import historico

    from datetime import date, timedelta

    n = 3000
    puntos = [((date(2016, 1, 1) + timedelta(days=i)).isoformat(), 100.0 + i) for i in range(n)]
    puntos.append(("basura", 1.0))                        # fecha inválida: se descarta
    carga = {"loaded": True, "series": {"CER": {"label": "CER", "points": puntos}}}
    monkeypatch.setattr(historico, "ensure_loaded", lambda: carga)
    monkeypatch.setattr(historico, "series_points", lambda key, days=None, desde=None, hasta=None: {"label": "CER", "points": puntos})
    conv = []
    orig = hr._unix
    monkeypatch.setattr(hr, "_unix", lambda iso: conv.append(1) or orig(iso))
    hr._DATA_MEMO.clear()
    async with _client() as ac:
        r = await ac.get("/historicos/data?serie=CER&rango=todo")
        assert r.status_code == 200
        j = r.json()
        assert j["n"] == n and len(j["x"]) == n and j["y"][0] == 100.0 and j["x"] == sorted(j["x"])
        assert len(conv) == n + 1                          # una conversión por punto (antes: dos)
        r2 = await ac.get("/historicos/data?serie=CER&rango=todo")
        assert r2.json() == j and len(conv) == n + 1       # memo: cero conversiones
        carga2 = dict(carga)                                # refresh del backup → versión nueva → recalcula
        monkeypatch.setattr(historico, "ensure_loaded", lambda: carga2)
        await ac.get("/historicos/data?serie=CER&rango=todo")
        assert len(conv) == 2 * (n + 1)
    hr._DATA_MEMO.clear()


# ── E03 / E05 · JS real en Node ──────────────────────────────────────────────
@pytest.mark.skipif(shutil.which("node") is None, reason="node no disponible")
def test_motor_live_y_graficos_en_node() -> None:
    r = subprocess.run([shutil.which("node"), str(ROOT / "tests" / "live_engine_harness.cjs")],
                       capture_output=True, text=True, timeout=180)
    assert r.returncode in (0, 1), r.stderr
    out = json.loads(r.stdout)
    assert out["delta_fetch"]["ok"], out["delta_fetch"]                 # fetch colgado: plazo + swap completo
    assert out["delta_body"]["ok"], out["delta_body"]                   # cuerpo colgado: ídem
    assert out["fallback_poll_colgado"]["ok"], out["fallback_poll_colgado"]   # un sondeo en vuelo + backoff
    assert out["seq_en_orden"]["ok"], out["seq_en_orden"]               # un md-update por avance
    assert out["controles"]["ok"], out["controles"]
    assert out["historico_orden"]["ok"], out["historico_orden"]         # E05: la respuesta vieja no pisa
    assert out["ok"]


# ── OMS.MARGEN ───────────────────────────────────────────────────────────────
def _floater():
    from backend.services import bond_universe, pricing
    settle = pricing.settlement_date_str("24hs")
    for c in bond_universe.all_codes():
        meta = pricing.bond_meta(c) or {}
        if (meta.get("tipo_tasa_interes") or "").upper() in ("VARIABLE", "VARIABLE_CAP"):
            m = pricing.compute_metrics(c, "precio", 100.0, settle=settle, include_cashflows=False)
            if not m.get("error") and m.get("margen_tna") == m.get("margen_tna"):
                return c, m
    return None, None


@pytest.mark.asyncio
async def test_margen_en_excel_calc(tmp_path, monkeypatch) -> None:
    from backend.services import auth, bond_universe

    bond_universe.ensure_loaded()
    code, esperado = _floater()
    if code is None:
        pytest.skip("sin floater con benchmark en el universo de test")
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "app_users_path", str(tmp_path / "store.json"))
    auth.refresh()
    auth.ensure_bootstrapped()
    try:
        auth.create_user("mesa_margen", "clave123", "basico")
        tok = auth.set_excel_access("mesa_margen", True)
        async with _client() as ac:
            r = await ac.post("/excel/v1/calc", headers={"X-OMS-Token": tok}, json={"items": [
                {"code": code, "modo": "precio", "valor": 100.0},
                {"code": "GD30", "modo": "precio", "valor": 78.5},
            ]})
        assert r.status_code == 200
        res = r.json()["results"]
        assert res[0]["margen_tna"] == pytest.approx(esperado["margen_tna"])
        assert "margen_tna" not in res[1]                  # tasa fija: sin margen → OMS.MARGEN da #N/A con motivo
    finally:
        auth.refresh()
    # el add-in registra la función y la metadata la publica
    fj = json.loads((ROOT / "backend/static/excel/functions.json").read_text(encoding="utf-8"))
    assert any(f["id"] == "MARGEN" for f in fj["functions"])
    js = (ROOT / "backend/static/excel/functions.js").read_text(encoding="utf-8")
    assert 'CustomFunctions.associate("MARGEN", guard(margenFn))' in js and "v19" in js
    assert "OMS.MARGEN" in (ROOT / "backend/static/excel/FORMULAS.md").read_text(encoding="utf-8")
