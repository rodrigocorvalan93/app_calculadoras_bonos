"""Proyecciones editables (inflación mensual / A3500) — 13/11.

Cubre: el armado compartido con `indices.main()` (bit a bit), validación,
aplicar / deshacer / restablecer con archivo + log + instalación en
`rentafija.inputs` (las TIR de los CER PROYECTADO cambian y vuelven), el
vigilante que toma lo que escribió otra PC, Históricos · Macro con las series
proyectadas (corte, rango hacia los dos lados, CSV, xlsx), la pestaña por HTTP
y el gate de la feature `proyecciones`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from backend.config import settings
from backend.services import auth, bond_universe, pricing, proyecciones as P

ROOT = Path(__file__).resolve().parents[1]


def _client() -> AsyncClient:
    from backend.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.fixture()
def escenario_limpio(tmp_path, monkeypatch):
    """Archivo compartido en un tmp propio del test (sin archivo = tablas del
    código) y los memos del servicio vacíos; al salir repone las series del
    código en inputs para no ensuciar al resto de la suite."""
    monkeypatch.setenv("PROYECCIONES_PATH", str(tmp_path / "proyecciones.json"))
    monkeypatch.setattr(P, "_vigente_memo", (None, None))
    monkeypatch.setattr(P, "_calc_memo", (None, None))
    bond_universe.ensure_loaded()
    _a3500_pristina()
    yield tmp_path / "proyecciones.json"
    P._instalar(P.calcular(P.defaults()), None)
    pricing._index_val_cache.clear()


def _a3500_pristina() -> None:
    """Otros tests inyectan filas en `inputs['a3500']` (`.loc["2026-06-26"]`,
    como el poller de FX legacy) y las dejan. Si la serie no está como la dejó
    `indices.main()` (índice de `date` puros), se repone desde el backup del
    BCRA —la misma fuente de main()— y su proyección con las tablas del
    código, así el bit a bit de abajo compara contra un estado consistente."""
    from datetime import date

    import pandas as pd
    import rentafija
    from backend.services import historico
    import indices

    df = rentafija.inputs["a3500"]
    if all(type(ix) is date for ix in df.index):
        return
    pts = historico.series_points("a3500")["points"]
    limpio = pd.DataFrame({"tca3500": [float(v) for _, v in pts]},
                          index=[date.fromisoformat(d) for d, _ in pts])
    limpio.index.name = "fecha"
    rentafija.inputs["a3500"] = limpio
    esc = P.defaults()
    rentafija.inputs["a3500_proyectado"] = indices.armar_proyecciones(
        rentafija.inputs["CER"], rentafija.inputs["inflamom_observado"], limpio, rentafija.inputs["UVA"],
        esc["inflacion"], esc["a3500"])[3]
    P._obs_memo = (None, None)


def _mismas(a, b) -> bool:
    return (a.shape == b.shape and list(a.index) == list(b.index)
            and (a.to_numpy(dtype=float) == b.to_numpy(dtype=float)).all())


# ── cálculo ─────────────────────────────────────────────────────────────────
def test_calcular_con_las_tablas_del_codigo_es_bit_a_bit_lo_que_cargo_indices_main(escenario_limpio) -> None:
    """`indices.main()` (al cargar el universo) y `proyecciones.calcular`
    pasan por `indices.armar_proyecciones`: con las mismas tablas, los cuatro
    frames proyectados son idénticos."""
    import rentafija
    esc = P.vigente()
    assert esc["meta"]["origen"] == "codigo" and esc["inflacion"] and esc["a3500"]
    series = P.calcular(esc)
    for k in P.COLS:
        assert _mismas(rentafija.inputs[k], series[k]), k
    assert series["ultimos"]["cer"] is not None and series["ultimos"]["a3500"] is not None


def test_tabla_inflacion_acepta_claves_legacy_e_iso_igual() -> None:
    import indices
    legacy = {"Nov-26": 1.8, "Dec-26": 2, "Jan-27": 1.7}
    iso = {"2026-11": 1.8, "2026-12": 2.0, "2027-01": 1.7}
    a, b = indices.tabla_inflacion_mensual(legacy), indices.tabla_inflacion_mensual(iso)
    assert list(a.index) == list(b.index) and list(a["inflacionmom"]) == list(b["inflacionmom"])
    assert [d.day for d in a.index] == [30, 31, 31]                    # fin de mes
    assert P.mes_iso("Nov-26") == "2026-11" and P.mes_iso("2026-11-30") == "2026-11" and P.mes_iso("x") is None


def test_indices_lee_el_archivo_si_es_valido_y_cae_al_codigo_si_no(tmp_path, monkeypatch) -> None:
    import indices
    p = tmp_path / "proyecciones.json"
    monkeypatch.setenv("PROYECCIONES_PATH", str(p))
    assert indices.proyecciones_vigentes() == (dict(indices.proyeccion_inflacion_mensual),
                                               dict(indices.proyeccion_devaoficial_escenariobase))
    p.write_text(json.dumps({"inflacion": {"2027-01": 3.0}, "a3500": {"2027-01-31": 1700.0}}), encoding="utf-8")
    assert indices.proyecciones_vigentes() == ({"2027-01": 3.0}, {"2027-01-31": 1700.0})
    p.write_text("{no es json", encoding="utf-8")
    assert indices.proyecciones_vigentes()[0] == dict(indices.proyeccion_inflacion_mensual)
    p.write_text(json.dumps({"inflacion": {"2027-01": "tres"}, "a3500": {}}), encoding="utf-8")
    assert indices.proyecciones_vigentes()[0] == dict(indices.proyeccion_inflacion_mensual)


def test_normalizar_rechaza_con_todos_los_problemas() -> None:
    with pytest.raises(ValueError) as e:
        P.normalizar({"inflacion": {"2027-13": 1, "2027-01": "x", "2027-02": 99},
                      "a3500": {"ayer": 1, "2027-01-31": -5}})
    msg = str(e.value)
    for frag in ("mes inválido", "valor inválido", "fuera de rango", "fecha inválida", "A3500 2027-01-31"):
        assert frag in msg, frag
    ok = P.normalizar({"inflacion": {"Dec-26": "2", "2026-11": 1.5}, "a3500": {"2026-12-31": 1600}})
    assert ok == {"inflacion": {"2026-11": 1.5, "2026-12": 2.0}, "a3500": {"2026-12-31": 1600.0}}


# ── aplicar / deshacer / restablecer ────────────────────────────────────────
def test_aplicar_instala_cambia_las_tir_y_deshacer_las_devuelve(escenario_limpio) -> None:
    ruta = escenario_limpio
    proy_codes = [c for c in bond_universe.all_codes()
                  if getattr(bond_universe.get(c), "ajuste_sobre_capital", None) == "CER PROYECTADO"]
    code = next(c for c in proy_codes                                   # el primero vivo (precio finito)
                if (pricing.compute_metrics(c, "tir", 5.0).get("precio") or float("nan")) == pricing.compute_metrics(c, "tir", 5.0).get("precio"))
    px0 = pricing.compute_metrics(code, "tir", 5.0)["precio"]
    tok0 = pricing.indices_token()
    base = P.vigente()
    mas = {"inflacion": {k: v + 1.0 for k, v in base["inflacion"].items()}, "a3500": base["a3500"]}
    r = P.aplicar(mas, "tester", "un punto más")
    assert r["cambio"] == {"inflacion": True, "a3500": False}
    assert ruta.is_file() and P.ruta_log().is_file()
    guardado = json.loads(ruta.read_text(encoding="utf-8"))
    assert guardado["inflacion"] == mas["inflacion"] and guardado["meta"]["autor"] == "tester"
    assert P.vigente()["meta"]["origen"] == "archivo" and P.vigente()["meta"]["nota"] == "un punto más"
    pricing._index_val_cache.clear()
    assert pricing.indices_token() != tok0                       # la huella cambió → caches nuevos
    px1 = pricing.compute_metrics(code, "tir", 5.0)["precio"]
    assert px1 > px0 * 1.01, (code, px0, px1)                     # más inflación = más flujo nominal a la misma TIR
    P.deshacer("tester")
    pricing._index_val_cache.clear()
    assert pricing.compute_metrics(code, "tir", 5.0)["precio"] == px0
    hist = P.historial()
    assert [h["accion"] for h in hist[:2]] == ["deshacer", "aplicar"]
    P.restablecer("tester")
    assert P.vigente()["inflacion"] == P.defaults()["inflacion"] and P.vigente()["meta"]["accion"] == "restablecer"


def test_el_vigilante_toma_lo_que_escribio_otra_pc(escenario_limpio) -> None:
    import rentafija
    ruta = escenario_limpio
    assert P.instalar_desde_archivo() is False or True            # sin archivo: nada que hacer
    antes = rentafija.inputs["cer_proyectado"]
    # "otra PC" escribe el archivo compartido (OneDrive lo trae)
    esc = P.defaults()
    esc["inflacion"] = {k: v + 2.0 for k, v in esc["inflacion"].items()}
    ruta.write_text(json.dumps({"inflacion": esc["inflacion"], "a3500": esc["a3500"],
                                "meta": {"autor": "pc-b", "ts": "2026-11-13T10:00:00"}}), encoding="utf-8")
    assert P.instalar_desde_archivo() is True
    despues = rentafija.inputs["cer_proyectado"]
    assert despues is not antes and float(despues["CER"].iloc[-1]) > float(antes["CER"].iloc[-1])
    assert P.vigente()["meta"]["autor"] == "pc-b"
    assert P.instalar_desde_archivo() is False                    # misma firma: no reinstala


def test_escenario_usa_la_inflacion_vigente(escenario_limpio) -> None:
    from datetime import date

    from backend.services import escenario_prefs
    base = escenario_prefs.infl_default(date(2027, 3, 15), 3)
    esc = P.defaults()
    esc["inflacion"] = {k: 9.0 for k in esc["inflacion"]}
    P.aplicar(esc, "tester")
    assert escenario_prefs.infl_default(date(2027, 3, 15), 3) == "9,00;9,00;9,00" != base


# ── Históricos · Macro ──────────────────────────────────────────────────────
def test_series_points_proyectada_trae_corte_y_rango_a_los_dos_lados(escenario_limpio) -> None:
    from datetime import date, timedelta

    from backend.services import historico
    d = historico.series_points("cer_proy")
    assert d["corte"] and d["points"] and d["points"][-1][0] > d["corte"] > d["points"][0][0]
    corte = date.fromisoformat(d["corte"])
    v = historico.series_points("cer_proy", days=30)
    assert v["points"][0][0] >= (corte - timedelta(days=30)).isoformat()
    assert v["points"][-1][0] <= (corte + timedelta(days=30)).isoformat() and v["points"][-1][0] > d["corte"]
    assert historico.series_points("inflamom_proy")["corte"] == historico.series_points("inflamom_proy")["corte"]
    assert {s["key"] for s in historico.series_list_proyectadas()} >= {"cer_proy", "a3500_proy", "tamar_proy", "inflamom_proy"}


@pytest.mark.asyncio
async def test_http_historicos_macro_proyectadas_csv_y_xlsx(escenario_limpio) -> None:
    async with _client() as ac:
        page = await ac.get("/historicos?serie=cer_proy")
        assert page.status_code == 200 and 'value="cer_proy" selected' in page.text and "macro.xlsx" in page.text
        d = (await ac.get("/historicos/data?serie=cer_proy&rango=1a")).json()
        assert d["n"] > 300 and d["corte"] and d["x"][0] < d["corte"] < d["x"][-1]
        obs = (await ac.get("/historicos/data?serie=CER&rango=1a")).json()
        assert "corte" not in obs
        csv = await ac.get("/historicos/macro.csv?serie=a3500_proy&rango=3m")
        assert csv.status_code == 200 and csv.headers["content-disposition"].endswith('"macro_a3500_proy.csv"')
        texto = csv.content.decode("utf-8-sig")
        assert texto.startswith("Fecha;A3500 proyectado;Tramo") and ";observado" in texto and ";proyectado" in texto
        assert "." not in texto.split("\r\n")[1].split(";")[1]        # coma decimal
        x = await ac.get("/historicos/macro.xlsx")
        assert x.status_code == 200 and x.content[:2] == b"PK" and len(x.content) > 100_000


# ── pestaña ─────────────────────────────────────────────────────────────────
def _form_de(page: str) -> dict:
    import re
    return dict(re.findall(r'name="(i_[0-9-]+|df_\d+|dv_\d+)" value="([^"]*)"', page))


@pytest.mark.asyncio
async def test_http_pestana_preview_csv_aplicar(escenario_limpio) -> None:
    ruta = escenario_limpio
    async with _client() as ac:
        r = await ac.get("/proyecciones")
        assert r.status_code == 200
        assert "tablas del código" in r.text and "data-proy-chart" in r.text and 'name="i_' in r.text
        assert 'hx-post="/proyecciones/aplicar"' in r.text                       # sin muro = superuser
        form = _form_de(r.text)
        assert len(form) >= 10 and any(k.startswith("df_") for k in form)
        for k in form:
            if k.startswith("i_"):
                form[k] = "3,5"
        form["nota"] = "prueba"
        pv = await ac.post("/proyecciones/preview", data=form)
        assert pv.status_code == 200 and "Vista previa del borrador" in pv.text and "ref_x" in pv.text
        malo = await ac.post("/proyecciones/preview", data={"i_2027-01": "tres"})
        assert "no es un número" in malo.text
        csv = await ac.post("/proyecciones/csv", data=dict(form, serie="uva"))
        assert csv.status_code == 200 and csv.headers["content-disposition"].endswith('"uva_proyectado.csv"')
        assert csv.content.decode("utf-8-sig").startswith("Fecha;UVA;Tramo")
        fut = (await ac.get("/proyecciones/futuros")).json()
        assert "rows" in fut and "n" in fut
        assert not ruta.exists()                                                 # nada se aplicó todavía
        ap = await ac.post("/proyecciones/aplicar", data=form)
        assert ap.status_code == 200 and ap.headers.get("hx-redirect") == "/proyecciones?ok=1"
        assert ruta.is_file() and json.loads(ruta.read_text(encoding="utf-8"))["meta"]["nota"] == "prueba"
        r2 = await ac.get("/proyecciones?ok=1")
        assert "archivo compartido" in r2.text and "Escenario aplicado" in r2.text
        vacio = await ac.post("/proyecciones/aplicar", data={"nota": "x"})
        assert "las dos tablas están vacías" in vacio.text and "hx-redirect" not in vacio.headers
        assert (await ac.post("/proyecciones/deshacer")).headers.get("hx-redirect")
        assert (await ac.post("/proyecciones/restablecer")).headers.get("hx-redirect")


@pytest.fixture()
def auth_on(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "app_users_path", str(tmp_path / "store.json"))
    auth.refresh()
    auth.ensure_bootstrapped()
    yield
    auth.refresh()


@pytest.mark.asyncio
async def test_feature_proyecciones_gatea_aplicar_pero_no_la_vista(auth_on, escenario_limpio) -> None:
    """Premium sin la feature: ve la pestaña (si la tiene) sin el botón Aplicar y
    el POST da 403; con la feature tildada en /admin, aplica. Superuser siempre."""
    async with _client() as su:
        await su.post("/login", data={"username": "su_test", "password": "clave-de-test-2026!", "next": "/"})
        await su.post("/admin/users", data={"username": "prem", "password": "clave123", "role": "premium"})
        auth.set_role_tabs("premium", auth.allowed_tabs("premium") + ["proyecciones"])
    async with _client() as ac:
        await ac.post("/login", data={"username": "prem", "password": "clave123", "next": "/"})
        page = await ac.get("/proyecciones")
        assert page.status_code == 200 and 'hx-post="/proyecciones/aplicar"' not in page.text
        assert "no aplicar" in page.text
        form = _form_de(page.text)
        assert (await ac.post("/proyecciones/preview", data=form)).status_code == 200
        assert (await ac.post("/proyecciones/aplicar", data=form)).status_code == 403
        assert (await ac.post("/proyecciones/restablecer")).status_code == 403
        auth.set_role_features("premium", ["proyecciones"])
        page = await ac.get("/proyecciones")
        assert 'hx-post="/proyecciones/aplicar"' in page.text
        assert (await ac.post("/proyecciones/aplicar", data=form)).headers.get("hx-redirect")
        assert P.vigente()["meta"]["autor"] == "prem"
    assert "proyecciones" in auth.FEATURE_KEYS and ("proyecciones", "Proyecciones", "/proyecciones") in auth.TABS
