"""Inicio (07/10): pestaña de aterrizaje con el resumen del mercado en una
request live por tick, reordenamiento de la nav y riesgo país del poller."""
from __future__ import annotations

import json
import os
from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient

from backend.services import auth, bond_universe, curves, inicio, marketdata_store, riesgo_pais, symbols as syms
from tests.test_historico_writer import auth_on  # noqa: F401 — fixture (muro de login en tmp)

# ruff: noqa: F811 — los fixtures importados se piden por nombre como parámetro (patrón pytest)


def _client() -> AsyncClient:
    from backend.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


# ── pestañas ────────────────────────────────────────────────────────────────
def test_orden_de_la_nav_y_matriz_tenencias() -> None:
    keys = [k for k, _, _ in auth.TABS]
    assert keys[:10] == ["home", "mercado", "curves", "yas", "futuros", "dolares",
                         "historicos", "graficos", "posiciones", "matriz"]
    assert dict((k, lbl) for k, lbl, _ in auth.TABS)["matriz"] == "Matriz Tenencias"
    assert dict((k, p) for k, _, p in auth.TABS)["home"] == "/inicio"
    # Inicio la ve todo rol aunque su lista de pestañas no la tenga
    assert "home" in auth.allowed_tabs("basico") and "home" in auth.allowed_tabs("premium")
    assert auth.can_access_path("basico", "/inicio") and auth.can_access_path("basico", "/inicio/body")
    assert auth.nav_for("superuser")[0]["label"] == "Inicio"


@pytest.mark.asyncio
async def test_raiz_y_login_aterrizan_en_inicio(auth_on) -> None:
    async with _client() as ac:
        r = await ac.get("/", follow_redirects=False)
        assert r.status_code in (302, 303) and "/inicio" in r.headers["location"] or "/login" in r.headers["location"]
        r = await ac.post("/login", data={"username": "su_test", "password": "clave-de-test-2026!"})
        assert r.status_code == 303 and r.headers["location"] == "/inicio"
        page = await ac.get("/inicio")
        assert page.status_code == 200 and 'class="tab active" href="/inicio">Inicio<' in page.text
        # la nav arranca con Inicio y Mercado; Matriz dice "Matriz Tenencias"
        i_ini, i_mer, i_yas = page.text.find('href="/inicio">Inicio<'), page.text.find('href="/mercado">Mercado<'), page.text.find('href="/yas">YAS<')
        assert 0 < i_ini < i_mer < i_yas
        assert ">Matriz Tenencias<" in page.text
        # /admin no ofrece Inicio como checkbox (siempre visible)
        adm = await ac.get("/admin")
        assert adm.status_code == 200 and "tab_basico_home" not in adm.text and "tab_basico_mercado" in adm.text
        # un básico sin Inicio en su lista entra igual
        await ac.post("/admin/tabs", data={"tab_basico_yas": "on", "tab_premium_yas": "on"})
        await ac.post("/admin/users", data={"username": "juan", "password": "clave123", "role": "basico", "email": ""})
    async with _client() as ac:
        r = await ac.post("/login", data={"username": "juan", "password": "clave123"})
        assert r.status_code == 303 and r.headers["location"] == "/inicio"
        page = await ac.get("/inicio")
        assert page.status_code == 200 and 'href="/inicio">Inicio<' in page.text and 'href="/yas">YAS<' in page.text
        assert 'href="/mercado"' not in page.text                     # Mercado no está en su lista
        assert (await ac.get("/inicio/body")).status_code == 200
        assert (await ac.get("/mercado")).status_code == 403


# ── servicio: selección de filas y tarjetas ──────────────────────────────────
def _row(code: str, vto: date, nominal: float | None, **kw) -> dict:
    r = {"code": code, "nombre": code, "last": 100.0, "close": 99.0, "var_px": 1.0, "var_pct": 1.01,
         "tirea": 0.10, "delta_yield_bps": -12.3, "tem": 0.008, "margen_tna": float("nan"),
         "duration": 1.0, "vencimiento": vto, "nominal": nominal, "volume": None, "last_cls": "px-up"}
    r.update(kw)
    return r


def test_seleccionar_prioriza_operados_y_ordena_por_vencimiento() -> None:
    filas = [inicio._fila(_row(f"B{i:02d}", date(2027, 1, 1 + i), nominal=(1000.0 * (i % 4) or None)))
             for i in range(14)]
    sel = inicio.seleccionar(filas, max_filas=5)
    assert len(sel) == 5
    assert [f["code"] for f in sel] == sorted(f["code"] for f in sel)          # por vencimiento
    # los 5 más operados (nominal 3000 > 2000 > …) entran antes que los sin volumen
    assert all(f["nominal"] for f in sel)
    # con pocas filas se muestran todas, por vencimiento
    pocas = inicio.seleccionar(filas[:3][::-1], max_filas=5)
    assert [f["code"] for f in pocas] == ["B00", "B01", "B02"]
    # sin volumen en ninguna: completan los más cortos
    sinvol = inicio.seleccionar([inicio._fila(_row(f"C{i}", date(2028, 1, 1 + i), None)) for i in range(8)], 3)
    assert [f["code"] for f in sinvol] == ["C0", "C1", "C2"]


def test_tarjetas_bonos_duales_sin_margen_cer_y_pata_tamar_v_en_tamar() -> None:
    rows_by = {
        "globales": [_row("GD30", date(2030, 7, 9), 5e6), _row("GD35", date(2035, 7, 9), 1e6)],
        # TMVE8 también está en dualfija a propósito: el mismo código no se repite
        "dualfija": [_row("TTD26", date(2026, 12, 15), 1e6), _row("TMVE8", date(2028, 1, 28), 3e6)],
        "dualcer": [_row("TXMD8", date(2028, 12, 15), 2e6), _row("TXMJ8", date(2028, 6, 30), 2e6, margen_tna=0.9)],
        "dualdlk": [_row("TMVE8", date(2028, 1, 28), 3e6)],
        "dualtamar": [_row("TTD26v", date(2026, 12, 15), 1e6, margen_tna=0.0312, tirea=0.31),
                      _row("TXMD8v", date(2028, 12, 15), 2e6, margen_tna=0.045, tirea=0.29),
                      _row("TMVE8v", date(2028, 1, 28), 3e6, margen_tna=0.05, tirea=0.30)],
        "tamar": [_row("TMF27", date(2027, 2, 1), 1e6, margen_tna=0.02)],
    }
    t = inicio.tarjetas_bonos(rows_by)
    assert set(t) == {k for k, _, _ in inicio.TARJETAS_BONOS}
    g = t["globales"]
    assert [f["code"] for f in g["filas"]] == ["GD30", "GD35"] and g["margen"] is False and g["ocultas"] == 0
    assert g["filas"][0]["tirea"] == 0.10 and g["filas"][0]["delta_tir_bps"] == -12.3 and g["filas"][0]["margen"] is None
    assert len(g["secciones"]) == 1 and g["secciones"][0]["titulo"] is None
    # Duales: un dual por fila (pata base) por vencimiento; margen TAMAR sólo en
    # la pata fija / DLK — a la CER no le corresponde (aunque dualtamar lo tenga
    # y aunque la propia fila CER traiga un margen_tna).
    d = t["duales"]
    assert [f["code"] for f in d["filas"]] == ["TTD26", "TMVE8", "TXMJ8", "TXMD8"]
    assert {f["code"]: f["margen"] for f in d["filas"]} == {"TTD26": 0.0312, "TMVE8": 0.05, "TXMJ8": None, "TXMD8": None}
    assert d["margen"] is True and d["margen_tip"] == inicio._TIP_MARGEN_DUALES
    assert d["secciones"][0]["curva"] == "mix:dualfija,dualcer,dualdlk"        # "ver la curva" real, no /curves?curve=duales
    # TAMAR: soberanos arriba y, como subdivisión, la pata TAMAR (v) de los
    # duales CER (los que nombró el desk) con su TIR y su margen propios; la
    # pata v de la fija / DLK NO va (su margen ya está cruzado en Duales).
    tm = t["tamar"]
    assert [s["titulo"] for s in tm["secciones"]] == [None, inicio.SUB_DUALES_V]
    assert [s["curva"] for s in tm["secciones"]] == ["tamar", "mix:dualtamar_cer"]   # /curves sólo conoce CurveDef y mix:
    assert [f["code"] for f in tm["secciones"][0]["filas"]] == ["TMF27"]
    assert [f["code"] for f in tm["secciones"][1]["filas"]] == ["TXMD8v"]
    assert (tm["secciones"][1]["filas"][0]["tirea"], tm["secciones"][1]["filas"][0]["margen"]) == (0.29, 0.045)
    assert [f["code"] for f in tm["filas"]] == ["TMF27", "TXMD8v"] and tm["margen"] is True
    assert tm["total"] == 2 and tm["ocultas"] == 0 and tm["margen_tip"] == inicio._TIP_MARGEN
    # con la curva dualtamar_cer en rows_by manda ésa (es lo que arma la ruta)
    t_cur = inicio.tarjetas_bonos({**rows_by, "dualtamar_cer": [_row("TXMJ9v", date(2029, 6, 29), 1e6, margen_tna=0.04)]})
    assert [f["code"] for f in t_cur["tamar"]["secciones"][1]["filas"]] == ["TXMJ9v"]
    assert t["cer"]["filas"] == [] and t["cer"]["total"] == 0
    # sin duales la subdivisión queda vacía (el template no la pinta) y la tarjeta sigue
    t2 = inicio.tarjetas_bonos({"tamar": rows_by["tamar"]})
    assert t2["tamar"]["secciones"][1]["filas"] == [] and [f["code"] for f in t2["tamar"]["filas"]] == ["TMF27"]
    # el tope aplica por sección: 12 soberanos + 11 duales CER v → 10 + 10; cada
    # sección cuenta lo suyo (el pie de la tarjeta usa la principal)
    muchos = {"tamar": [_row(f"TM{i:02d}", date(2027, 1, 1 + i), 1e6 * (i + 1)) for i in range(12)],
              "dualtamar_cer": [_row(f"TX{i:02d}v", date(2028, 1, 1 + i), 1e6) for i in range(11)]}
    t3 = inicio.tarjetas_bonos(muchos)["tamar"]
    assert [len(s["filas"]) for s in t3["secciones"]] == [10, 10]
    assert [s["ocultas"] for s in t3["secciones"]] == [2, 1] and t3["ocultas"] == 3


def test_kpis_tipos_de_cambio_y_mercado() -> None:
    summary = {"plazo": "24hs",
               "oficial": {"source": "A3500", "last": 1500.0, "close": 1490.0, "var_pct": 1500 / 1490 - 1, "date": "2026-10-01"},
               "usb": {"base": "AL30", "last": 1400.0, "var_pct": -0.01},
               "usd": {"base": "GD30", "last": 1450.0, "var_pct": 0.02},
               "brecha": -0.0333, "brecha_var_pp": 0.0012,
               "canje": {"base": "GD30", "last": 0.0357, "var_pct": 0.0021}, "a3500": None}
    tc = {r["label"]: r for r in inicio.tipos_de_cambio(summary)}
    assert tc["Oficial · A3500"]["sub"] == "01/10/2026" and tc["Oficial · A3500"]["var_px"] == pytest.approx(10.0)
    mep = tc["USD MEP"]
    assert mep["sub"] == "AL30" and mep["var_px"] == pytest.approx(1400 - 1400 / 0.99) and mep["var_pct"] == -0.01
    assert tc["Brecha"]["fmt"] == "pct" and tc["Brecha"]["var_pp"] == pytest.approx(0.12)
    assert tc["Canje"]["var_pp"] == pytest.approx(0.21) and tc["Canje"]["sub"] == "CCL / MEP · GD30"
    # Merval en CCL: nivel / CCL, variación contra el cierre en CCL de ayer
    import backend.services.inicio as mod
    orig = mod.equities.merval_row
    mod.equities.merval_row = lambda: {"last": 2_900_000.0, "close": 2_800_000.0, "var_pct": (29 / 28 - 1) * 100}
    try:
        m = {r["label"] + "|" + (r["sub"] or ""): r for r in inicio.mercado(summary)}
    finally:
        mod.equities.merval_row = orig
    ars = m["MERVAL|ARS"]
    assert ars["value"] == 2_900_000.0 and ars["var_px"] == 100_000.0 and ars["var_pct"] == pytest.approx(29 / 28 - 1)
    ccl = m["MERVAL|en CCL · GD30"]
    assert ccl["value"] == pytest.approx(2_900_000 / 1450)
    close_ccl = 2_800_000 / (1450 / 1.02)
    assert ccl["var_pct"] == pytest.approx(2_900_000 / 1450 / close_ccl - 1)
    assert any(k.startswith("Riesgo país|EMBI") for k in m)      # "EMBI" sin dato, "EMBI · DD/MM/AAAA" con dato


# ── riesgo país ─────────────────────────────────────────────────────────────
def test_riesgo_pais_parseo_merge_y_snapshot(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RIESGO_PAIS_PATH", str(tmp_path / "rp.json"))
    riesgo_pais.reset_para_tests()
    assert riesgo_pais.snapshot()["valor"] is None
    serie = [{"fecha": "2026-10-01", "valor": 1180}, {"fecha": "2026-10-02", "valor": "1150.0"},
             {"fecha": "basura", "valor": 1}, {"fecha": "2026-10-03", "valor": None}, "x"]
    assert riesgo_pais.parsear(serie) == [("2026-10-01", 1180.0), ("2026-10-02", 1150.0)]
    llamadas: list = []

    def fetch(url):
        llamadas.append(url)
        if url.endswith("/ultimo"):
            return {"fecha": "2026-10-06", "valor": 1097}
        return serie

    monkeypatch.setattr(riesgo_pais, "_fetch", fetch)
    assert riesgo_pais.refresh() is True                 # sin historia → serie completa
    assert llamadas == [riesgo_pais._url()]
    s = riesgo_pais.snapshot()
    assert s["valor"] == 1150.0 and s["fecha"] == "02/10/2026" and s["var"] == -30.0
    assert s["var_pct"] == pytest.approx(1150 / 1180 - 1) and s["fuente"] == "argentinadatos"
    assert riesgo_pais.refresh() is True                 # con historia → /ultimo
    assert llamadas[-1].endswith("/ultimo")
    s = riesgo_pais.snapshot()
    assert s["valor"] == 1097.0 and s["previo"] == 1150.0 and s["var"] == -53.0 and s["fecha"] == "06/10/2026"
    assert riesgo_pais.refresh() is False                # mismo último: sin cambio
    # persistió y sobrevive al reinicio del proceso (reset + lectura del archivo)
    raw = json.loads((tmp_path / "rp.json").read_text(encoding="utf-8"))
    assert [p["fecha"] for p in raw["puntos"]] == ["2026-10-01", "2026-10-02", "2026-10-06"]
    riesgo_pais.reset_para_tests()
    s = riesgo_pais.snapshot()
    assert s["valor"] == 1097.0 and s["fuente"] == "archivo"
    # red caída: el estado guarda el error y el último dato sigue
    monkeypatch.setattr(riesgo_pais, "_fetch", lambda url: (_ for _ in ()).throw(OSError("sin red")))
    assert riesgo_pais.refresh() is False
    s = riesgo_pais.snapshot()
    assert s["valor"] == 1097.0 and "sin red" in (s["error"] or "")
    # apagado por env: start() no levanta thread
    monkeypatch.setenv("RIESGO_PAIS", "0")
    riesgo_pais.start()
    assert riesgo_pais._thread is None or not riesgo_pais._thread.is_alive()


# ── HTTP: el resumen entero en una request, cacheado por seq ────────────────
@pytest.mark.asyncio
async def test_inicio_body_muestra_los_bonos_sembrados_y_comparte_el_render() -> None:
    from backend.tools.bench_tick import _precio_para
    bond_universe.ensure_loaded()
    st = marketdata_store.get_store()
    tbl = curves.build_curve_codes()
    sembrados = []
    for key in ("globales", "cer", "lecap"):
        for c in tbl.get(key, [])[:2]:
            px = _precio_para(c, {})
            if px is None:
                continue
            st.update_from_md(syms.md_symbol(c, "24hs"), {
                "LA": {"price": round(px, 3), "size": 100, "date": "2026-10-06T14:00:00-03:00"},
                "CL": {"price": round(px * 0.995, 3), "date": "2026-10-05"},
                "NV": {"size": 5e6}, "EV": {"size": 5e6 * px / 100}})
            sembrados.append(c)
    assert sembrados
    async with _client() as ac:
        r = await ac.get("/inicio/body")
        assert r.status_code == 200
        html = r.text
        for s in ("Tipos de cambio", "Tasas", "Mercado", "Globales", "Bonares", "Panel líder", "CER",
                  "Tasa fija", "Dólar linked", "TAMAR", "Duales", "Futuros de dólar", "Riesgo país"):
            assert s in html, s
        for c in sembrados:
            assert f'href="/yas?code={c}"' in html, c
        assert "var-cell" in html and "Δ TIR" in html
        assert 'title="EMBI+ Argentina' in html                    # la fuente del riesgo país, visible
        # el segundo pedido con la misma seq sale del cache compartido
        r2 = await ac.get("/inicio/body")
        assert r2.status_code == 200 and r2.headers.get("x-seq-cache") == "hit"
        # la página completa incluye el mismo cuerpo y el contenedor live
        page = await ac.get("/inicio")
        assert page.status_code == 200
        assert 'hx-get="/inicio/body"' in page.text and 'hx-trigger="md-update from:body, every 30s"' in page.text
        assert "Panel líder" in page.text and sembrados[0] in page.text


@pytest.mark.asyncio
async def test_pies_y_subdivision_linkean_a_curvas_que_curvas_reconoce() -> None:
    """Render del partial con tarjetas que SÍ tienen ocultas (cosa que el
    universo real no da hoy): el pie habla de la sección principal y linkea a
    su curva; la subdivisión linkea a la suya; y /curves reconoce esas keys
    (ni `duales` ni `dualtamar_cer` son CurveDef: van como mix:)."""
    from backend.main import app
    bond_universe.ensure_loaded()
    muchos = {"tamar": [_row(f"TM{i:02d}", date(2027, 1, 1 + i), 1e6 * (i + 1)) for i in range(12)],
              "dualtamar_cer": [_row(f"TX{i:02d}v", date(2028, 1, 1 + i), 1e6, margen_tna=0.03) for i in range(11)],
              "dualfija": [_row(f"TD{i:02d}", date(2027, 2, 1 + i), 1e6) for i in range(12)]}
    bonos = inicio.tarjetas_bonos(muchos)
    html = app.state.templates.env.get_template("partials/inicio_body.html").render(
        tc=[], tasas=[], mercado=[], futuros=[], lideres=[], plazo="24hs", bonos=bonos)
    tam = html[html.find('id="ini-tbl-tamar"'):html.find('id="ini-tbl-duales"')]
    assert "+2 más · se muestran los 10 más operados hoy" in tam and 'href="/curves?curve=tamar"' in tam
    assert "+1 más" in tam and 'href="/curves?curve=mix:dualtamar_cer"' in tam and "ver todos" in tam
    dua = html[html.find('id="ini-tbl-duales"'):]
    assert 'href="/curves?curve=mix:dualfija,dualcer,dualdlk"' in dua and 'href="/curves?curve=duales"' not in html
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        for curva in ("tamar", "mix:dualtamar_cer", "mix:dualfija,dualcer,dualdlk"):
            r = await ac.get(f"/curves/table?curve={curva}")
            assert r.status_code == 200 and "Curva no encontrada" not in r.text, curva
        r = await ac.get("/curves/table?curve=dualtamar_cer")          # la key cruda NO sirve: por eso el mix
        assert "Curva no encontrada" in r.text


def test_resumen_nunca_lanza_con_fuentes_caidas(monkeypatch) -> None:
    import backend.services.inicio as mod
    monkeypatch.setattr(mod.dolares, "summary", lambda plazo: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(mod.equities, "panel_rows", lambda panel: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(mod.futuros, "rows", lambda canal: (_ for _ in ()).throw(RuntimeError("x")))
    monkeypatch.setattr(mod.mae, "cauciones_rows", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    res = inicio.resumen()
    assert res["lideres"] == [] and res["futuros"] == []
    assert [r["label"] for r in res["tc"]][:3] == ["Oficial · A3500", "USD MEP", "USD CCL"] or res["tc"][0]["label"].startswith("Oficial")
    assert len(res["tasas"]) == 6 and len(res["mercado"]) == 5
    assert os.environ.get("RIESGO_PAIS") == "0"          # la suite no sale a la red
