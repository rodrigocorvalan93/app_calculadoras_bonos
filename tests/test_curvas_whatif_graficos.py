"""Curvas con what-if y gráfico · Gráficos con todas las curvas · M30A7 (19/11).

Pedidos del desk:
  1) Gráficos (sólo superuser): un cuadro de 2-3 columnas con un gráfico por
     curva — UN pedido (`/graficos/multi`) para todas.
  2) Curvas: editar el Last de una fila (what-if) y ver qué rinde, con el punto
     en rojo en un gráfico debajo de la tabla (`/curves/whatif` + charts.js).
  4) Gráficos: M30A7 no aparecía en "Todos ARS". El payload alineaba los
     puntos por duration (`ars_at[d]`): M30A7 (TAMAR bullet) y la LECAP que
     vence el mismo día tienen la MISMA duration y una pisaba a la otra.
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from backend.config import settings
from backend.routes import curves as cr
from backend.services import auth, bond_universe, curves, marketdata_store as mds, pricing, symbols as syms

ROOT = Path(__file__).resolve().parent.parent


def _client() -> AsyncClient:
    from backend.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


def _fila(code: str, dur: float, tirea: float, mon: str = "ARS") -> dict:
    return {"code": code, "duration": dur, "tirea": tirea, "tna": tirea, "tem": tirea / 12, "moneda": mon,
            "px_calc": 100.0, "price_source": "LA", "price_date": None, "bid": 99.9, "offer": 100.1,
            "tirea_bid": tirea + 0.002, "tirea_offer": tirea - 0.002, "margen_tna": 0.02}


# ── 4) dos bonos con la misma duration no se pisan ───────────────────────────
def test_x_unicos_separa_durations_repetidas_sin_tocar_el_resto() -> None:
    a = [("A", 0.5, 1.0), ("B", 0.9, 2.0)]
    assert cr._x_unicos(a) is a                                   # sin repetidos: la misma lista
    pts = [("M30A7", 0.44, 29.7, "ARS"), ("T30A7", 0.44, 30.4, "ARS"), ("X", 0.44, 31.0, "ARS"), ("Y", 0.9, 32.0, "ARS")]
    out = cr._x_unicos(pts)
    assert [p[0] for p in out] == ["M30A7", "T30A7", "X", "Y"]     # orden y datos intactos
    xs = [p[1] for p in out]
    assert len(set(xs)) == 4 and xs[0] == 0.44 and xs[0] < xs[1] < xs[2] < xs[3]
    assert xs[2] - xs[0] < 1e-12                                  # el mismo píxel
    assert [p[2:] for p in out] == [p[2:] for p in pts]
    assert pts[1][1] == 0.44                                      # la entrada no se muta


@pytest.mark.asyncio
async def test_graficos_data_muestra_los_dos_bonos_de_la_misma_duration(monkeypatch) -> None:
    """M30A7 (TAMAR) y T30A7 (LECAP) vencen el mismo día: los dos tienen que
    llegar al gráfico, a la tabla y al hover — antes quedaba uno solo."""
    filas = [_fila("S31L7", 0.20, 0.28), _fila("M30A7", 0.4411, 0.297), _fila("T30A7", 0.4411, 0.304),
             _fila("TML27", 0.69, 0.31), _fila("AL30D", 0.4411, 0.09, "USB"), _fila("TMG27", 0.78, 0.315)]

    async def fake(curve_key, plazo="24hs", only_quoting=True, leg="native", book=False, fuente="byma"):
        return [dict(r) for r in filas], {}

    monkeypatch.setattr(cr, "_rows_for", fake)
    async with _client() as ac:
        r = await ac.get("/graficos/data", params={"curve": "todos_ars_proyectado", "dmin": "0,01"})
        j = r.json()
        codes = [c for c in j["codes"] if c]
        assert r.status_code == 200 and j["n"] == 6
        assert sorted(codes) == ["AL30D", "M30A7", "S31L7", "T30A7", "TMG27", "TML27"]
        assert j["xs"] == sorted(j["xs"]) and len(set(j["xs"])) == len(j["xs"])
        i_m, i_t, i_a = j["codes"].index("M30A7"), j["codes"].index("T30A7"), j["codes"].index("AL30D")
        assert j["ars"][i_m] == pytest.approx(29.7) and j["ars"][i_t] == pytest.approx(30.4)
        assert j["usd"][i_a] == pytest.approx(9.0) and j["ars"][i_a] is None
        assert j["bid"][i_m] is not None and j["off"][i_t] is not None      # cada uno con sus puntas
        assert set(j["meta"]) == set(codes)
        assert len(j["nss"]) == len(j["xs"]) and len(j["xs"]) > 6          # con NSS: grilla fina
        # nss=0 (chart de Curvas): sin ajuste ni grilla — sólo los bonos
        r0 = await ac.get("/graficos/data", params={"curve": "todos_ars_proyectado", "dmin": "0,01", "nss": "0"})
        j0 = r0.json()
        assert len(j0["xs"]) == 6 and j0["nss"] == [] and sorted(c for c in j0["codes"] if c) == sorted(codes)
        assert len(r0.content) < len(r.content)


def test_m30a7_esta_en_tamar_y_en_todos_ars() -> None:
    """La ficha siempre estuvo en la curva: lo que la escondía era el choque
    de durations del payload, no la partición."""
    bond_universe.ensure_loaded()
    if bond_universe.get("M30A7") is None:
        pytest.skip("M30A7 ya no está en el universo")
    t = curves.build_curve_codes()
    if "M30A7" not in t["tamar"]:
        pytest.skip("M30A7 venció")
    assert "M30A7" in t["todos_ars_proyectado"]


# ── 2) what-if del Last ──────────────────────────────────────────────────────
def _un_codigo(curva: str) -> str:
    bond_universe.ensure_loaded()
    codes = curves.build_curve_codes().get(curva) or []
    assert codes, f"sin bonos en {curva}"
    return codes[0]


@pytest.mark.asyncio
async def test_whatif_valua_con_la_ficha_y_liquidacion_de_la_fila() -> None:
    code = _un_codigo("lecap")
    settle = pricing.settlement_date_str("24hs")
    ref = pricing.metrics_for_market_price(code, 101.25, settle)
    assert ref and ref.get("tirea") is not None
    async with _client() as ac:
        r = await ac.get("/curves/whatif", params={
            "curve": "lecap", "plazo": "24hs", f"price_{code}": "101,25",       # es-AR, como se tipea
            "price_NOEXISTE": "50", "price_AL30D": "70"})                       # fuera de la curva: se ignoran
        j = r.json()
        assert r.status_code == 200 and j["settle"] == settle and list(j["rows"]) == [code]
        w = j["rows"][code]
        assert w["pxn"] == 101.25 and w["px"] == "101,25"
        assert w["t"] == pytest.approx(ref["tirea"] * 100.0) and w["d"] == pytest.approx(ref["duration"])
        from backend.locale_ar import fmt_num, fmt_pct
        assert w["tir"] == fmt_pct(ref["tirea"], 2) and w["tna"] == fmt_pct(ref["tna"], 2)
        assert w["tem"] == fmt_pct(ref["tem"], 2) and w["dur"] == fmt_num(ref["duration"], 2)
        assert w["tna_lbl"] == (ref.get("tna_convention_label") or "")
        # precio más alto = rinde menos
        r2 = await ac.get("/curves/whatif", params={"curve": "lecap", f"price_{code}": "103"})
        assert r2.json()["rows"][code]["t"] < w["t"]
        # CI: otra liquidación
        r3 = await ac.get("/curves/whatif", params={"curve": "lecap", "plazo": "CI", f"price_{code}": "101,25"})
        assert r3.json()["settle"] == pricing.settlement_date_str("CI")
        # sin precios / precio inválido: nada que valuar
        vac = await ac.get("/curves/whatif", params={"curve": "lecap", f"price_{code}": "abc"})
        assert vac.status_code == 200 and vac.json()["rows"] == {}
        neg = await ac.get("/curves/whatif", params={"curve": "lecap", f"price_{code}": "-5"})
        assert neg.json()["rows"] == {}
        # combinada: vale cualquier código de las curvas elegidas
        mix = await ac.get("/curves/whatif", params={"curve": "mix:lecap,tamar", f"price_{code}": "101,25"})
        assert list(mix.json()["rows"]) == [code]


def test_whatif_tope_de_precios_por_pedido(monkeypatch) -> None:
    assert cr._WHATIF_MAX <= 100          # el pedido lo arma el navegador: acotado


def test_whatif_de_especie_en_pesos_de_un_hard_dollar_usa_la_nativa(monkeypatch) -> None:
    """GD30 / AL30 (pesos) valúan con la ficha nativa y precio ÷ FX, igual que
    su fila en Curvas: el what-if en pesos no entra crudo a la ficha en dólares."""
    from backend.services import fx as fx_svc

    bond_universe.ensure_loaded()
    if bond_universe.get("AL30") is None or pricing.native_dollar_code("AL30") is None:
        pytest.skip("sin especie pesos AL30 en el universo")
    nativa = pricing.native_dollar_code("AL30")
    fx = fx_svc.FxSnapshot(ccl=1500.0, usb=1450.0)
    settle = pricing.settlement_date_str("24hs")
    w = cr._whatif_uno("AL30", "24hs", "native", 101500.0, settle, fx)
    ref = pricing.metrics_for_market_price(nativa, 101500.0 / 1450.0, settle)
    assert w and "error" not in w and w["t"] == pytest.approx(ref["tirea"] * 100.0)
    # sin FX no se inventa una TIR
    assert "error" in cr._whatif_uno("AL30", "24hs", "native", 101500.0, settle, fx_svc.FxSnapshot())


@pytest.mark.asyncio
async def test_tabla_de_curvas_lleva_el_codigo_por_fila_y_el_chart_abajo() -> None:
    code = _un_codigo("lecap")
    st = mds.get_store()
    st.update_from_md(syms.md_symbol(code, "24hs"), {"LA": {"price": 101.0, "size": 10}, "CL": {"price": 100.5}})
    async with _client() as ac:
        r = await ac.get("/curves", params={"curve": "lecap"})
        html = r.text
        assert r.status_code == 200
        assert f'<tr data-code="{code}">' in html
        for cls in ("c-last", "c-dy", "c-dur", "c-tir", "c-tna", "c-tem", "c-par", "c-mar"):
            assert f'class="{cls}' in html, cls
        assert 'data-curve-chart' in html and 'id="cv-wi-bar"' in html and 'id="cv-wi-clear"' in html
        assert "every 30s, refresh" in html                         # el what-if pide ponerse al día
        assert html.index('id="curve-table"') < html.index('id="curve-chart"')    # el gráfico va DEBAJO y fuera del swap
        t = await ac.get("/curves/table", params={"curve": "lecap"})
        assert f'<tr data-code="{code}">' in t.text and "data-curve-chart" not in t.text


# ── 1) todas las curvas en un cuadro (superuser) ─────────────────────────────
@pytest.mark.asyncio
async def test_graficos_multi_trae_todas_las_curvas_en_un_pedido() -> None:
    bond_universe.ensure_loaded()
    st = mds.get_store()
    tabla = curves.build_curve_codes()
    sembradas = [k for k in ("lecap", "tamar", "cer") if tabla.get(k)]
    for k in sembradas:
        for i, c in enumerate(tabla[k]):
            st.update_from_md(syms.md_symbol(c, "24hs"), {"LA": {"price": 100.0 + i, "size": 10}, "CL": {"price": 99.5 + i}})
    async with _client() as ac:
        r = await ac.get("/graficos/multi")                 # sin muro (suite) = superuser
        j = r.json()
        assert r.status_code == 200 and j["metric"] == "tirea" and j["ylabel"] == "TIREA"
        por = {c["k"]: c for c in j["curvas"]}
        for k in sembradas:
            cv = por[k]
            assert cv["n"] == len(cv["x"]) == len(cv["y"]) == len(cv["c"]) == len(cv["u"]) > 0
            assert cv["x"] == sorted(cv["x"]) and set(cv["c"]) <= set(tabla[k])
            assert all(math.isfinite(v) for v in cv["y"]) and len(cv["gx"]) == len(cv["gy"]) <= cr._MULTI_GRID
            assert "_x" not in cv and "_y" not in cv and cv["l"]
        # el filtro de duration y de códigos de la página también vale acá
        fuera = por[sembradas[0]]["c"][0]
        r2 = await ac.get("/graficos/multi", params={"exclude": fuera, "dmin": "0,001"})
        assert fuera not in {c["k"]: c for c in r2.json()["curvas"]}[sembradas[0]]["c"]
        # métrica margen: sólo floaters con benchmark (las LECAP no tienen margen)
        r3 = await ac.get("/graficos/multi", params={"metric": "margen"})
        assert "lecap" not in {c["k"] for c in r3.json()["curvas"]}
        # página: la sección existe para el superuser
        pg = await ac.get("/graficos")
        assert 'id="graf-multi-card"' in pg.text and "data-graf-multi" in pg.text


def test_tendencia_del_cuadro_es_barata_robusta_y_nunca_tira() -> None:
    """La línea de cada gráfico chico: cuadrática en ln(1 + duration), una
    pasada robusta. Sin scipy (re-ajustar la NSS de 19 curvas por tick costaba
    280 ms p50) y sin RuntimeWarning (rentafija los sube a error)."""
    import time
    import warnings

    xs = [0.2, 0.5, 0.9, 1.4, 2.0, 2.7, 3.5, 4.4]
    ys = [30.0, 31.0, 31.8, 32.4, 32.9, 33.2, 33.4, 33.5]
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        gx, gy = cr._multi_tendencia(xs, ys)
        assert len(gx) == len(gy) == cr._MULTI_GRID and gx[0] == 0.2 and gx[-1] == 4.4
        assert gx == sorted(gx) and all(29.5 < v < 34.0 for v in gy) and gy[0] < gy[-1]
        # un outlier (bono por vencer con TIR disparatada) no arrastra la curva
        gx2, gy2 = cr._multi_tendencia(xs + [0.05], ys + [900.0])
        assert all(29.0 < v < 34.5 for v in gy2) and gx2[0] == 0.2      # ni lo ajusta ni estira el eje hasta él
        # sin con qué: vacío, nunca una excepción
        assert cr._multi_tendencia([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == ([], [])          # < 4 bonos
        assert cr._multi_tendencia([1.0] * 6, [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]) == ([], [])  # una sola duration
        assert cr._multi_tendencia([1.0, 2.0, 3.0, 4.0], [float("nan")] * 4) == ([], [])
        assert cr._multi_tendencia([], []) == ([], [])
        gx5, gy5 = cr._multi_tendencia([1.0, 2.0, 3.0, 4.0, 5.0], [10.0, 11.0, 12.0, 13.0, 14.0])   # 4-5 bonos: recta
        assert len(gx5) == cr._MULTI_GRID and gy5[0] < gy5[-1]
    t0 = time.perf_counter()
    for _ in range(200):
        cr._multi_tendencia(xs, ys)
    assert (time.perf_counter() - t0) / 200 < 0.005            # < 5 ms cada una (medido: ~0,1 ms)
    # el endpoint no ajusta NSS: scipy no participa del camino por tick
    import inspect
    src = inspect.getsource(cr._graficos_multi.__wrapped__) + inspect.getsource(cr._multi_cerrar)
    assert "nss_svc" not in src and "run_in_executor" not in src


@pytest.fixture()
def auth_on(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "app_users_path", str(tmp_path / "store.json"))
    auth.refresh()
    assert auth.ensure_bootstrapped()["created"]
    yield
    auth.refresh()


@pytest.mark.asyncio
async def test_graficos_multi_es_solo_superuser_aunque_el_cache_este_caliente(auth_on) -> None:
    """El cache por seq no lleva usuario: el chequeo va ANTES. Un premium con
    la pestaña Gráficos ve la página sin el cuadro y el endpoint le da 403,
    también justo después de que un superuser lo dejó cacheado."""
    auth.create_user("mesa_graf", "clave-mesa-2026!", "premium")
    async with _client() as su:
        await su.post("/login", data={"username": "su_test", "password": "clave-de-test-2026!", "next": "/graficos"})
        ok = await su.get("/graficos/multi")
        assert ok.status_code == 200 and "curvas" in ok.json()
        assert 'id="graf-multi-card"' in (await su.get("/graficos")).text
    async with _client() as us:
        await us.post("/login", data={"username": "mesa_graf", "password": "clave-mesa-2026!", "next": "/graficos"})
        no = await us.get("/graficos/multi")
        assert no.status_code == 403 and "curvas" not in no.text
        pg = await us.get("/graficos")
        if pg.status_code == 200:                                   # con la pestaña: página sin el cuadro
            assert 'id="graf-multi-card"' not in pg.text
    async with _client() as anon:
        r = await anon.get("/graficos/multi", follow_redirects=False)
        assert r.status_code in (302, 303, 307, 401, 403) and "curvas" not in r.text


# ── JS ───────────────────────────────────────────────────────────────────────
@pytest.mark.skipif(shutil.which("node") is None, reason="node no disponible")
def test_charts_js_curvas_y_cuadro_en_node() -> None:
    r = subprocess.run([shutil.which("node"), str(ROOT / "tests" / "curvas_chart_harness.cjs")],
                       capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert len(out) >= 19
    malos = {k: v for k, v in out.items() if v is not True}
    assert not malos, malos


def test_app_js_what_if_no_pelea_con_el_motor_live() -> None:
    js = (ROOT / "backend" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    bloque = js[js.index("// ── Curvas: what-if del Last"):]
    # mientras se tipea: ni pedido ni swap de la tabla, y el skip de swaps idénticos se resetea
    assert "htmx:beforeRequest" in bloque and "e.preventDefault()" in bloque
    assert "e.detail.shouldSwap = false" in bloque and "__lastHtml = null" in bloque
    assert "htmx:afterSwap" in bloque and "cv-whatif" in bloque and "/curves/whatif?" in bloque
    # las celdas pintadas por el what-if no flashean en el swap siguiente
    snap = js[js.index("function snapshot(root)"):js.index("// Flash en DOS fases")]
    assert "data-noflash" in snap
    charts = (ROOT / "backend" / "static" / "js" / "charts.js").read_text(encoding="utf-8")
    assert "nss=0" in charts and "/graficos/multi?" in charts and "IntersectionObserver" in charts
