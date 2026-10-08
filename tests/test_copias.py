"""Copias en conflicto y archivos viejos (tarjeta de /admin, superuser).

`services/copias.py`: clasificación por nombre (OneDrive -HOST, "(conflicted
copy)", "- copia", "(2)", .corrupto-*, .bak-*, .tmp), escaneo (listdir +
stat), análisis a pedido (filas / ruedas de la copia vs su principal → qué
aporta), borrado re-validado (sólo copias, sólo adentro de las carpetas) e
incorporación a la base px/tasas / FX de las ruedas que sólo tiene la copia."""
from __future__ import annotations

import os
import time
from datetime import date

import pandas as pd
import pytest

from backend.services import copias, historico_writer as hw
from tests.test_base_regresion import _filas
from tests.test_cierre_reconstruccion import D, D_ANT, D_SIG, _ba, env  # noqa: F401 — fixture + helpers
from tests.test_historico_writer import _client, auth_on  # noqa: F401

# ruff: noqa: F811 — fixtures importados pedidos por nombre como parámetro (patrón pytest)


@pytest.fixture()
def carpetas(env, monkeypatch):
    """Carpeta de la app y de las bases de MENTIRA (tmp): el escaneo nunca mira
    el repo real desde la suite. `env` ya apunta DELTA_HISTORICO_DIR al tmp."""
    app = env / "app"
    app.mkdir()
    (env / "cierres" / "2026").mkdir(parents=True)
    lista = [{"label": "app", "path": str(app), "recursivo": False, "local": False},
             {"label": "bases", "path": str(env), "recursivo": False, "local": False},
             {"label": "cierres", "path": str(env / "cierres"), "recursivo": True, "local": False}]
    monkeypatch.setattr(copias, "carpetas", lambda: [dict(c) for c in lista])
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 9, 25, 10, 0))
    copias._STATS.clear()
    return {"app": app, "bases": env}


def test_clasificar_por_nombre() -> None:
    vecinos = {"Delta - historico_fx.xlsx", "Delta - historico_fx.parquet", "Delta - historico_fx.parquet.src.json",
               "Delta - historico_byma_px_tasas.xlsx", "auth_store.json", "2026-10-02.parquet", "especies.py"}
    casos = {
        "Delta - historico_fx-NOTEBOOK-RC.xlsx": ("conflicto", "Delta - historico_fx.xlsx"),
        "Delta - historico_fx-DESKTOP-ABC12-2.xlsx": ("conflicto", "Delta - historico_fx.xlsx"),
        "Delta - historico_fx (conflicted copy 2026-10-05).xlsx": ("conflicto", "Delta - historico_fx.xlsx"),
        "Delta - historico_fx - copia.xlsx": ("copia", "Delta - historico_fx.xlsx"),
        "Delta - historico_fx (2).xlsx": ("copia", "Delta - historico_fx.xlsx"),
        "Delta - historico_fx.parquet.src-NB.json": ("conflicto", "Delta - historico_fx.parquet.src.json"),
        "Delta - historico_fx.xlsx.corrupto-20261001-170000": ("corrupto", "Delta - historico_fx.xlsx"),
        "Delta - historico_fx.xlsx.corrupto-20261001-170000-2": ("corrupto", "Delta - historico_fx.xlsx"),
        "Delta - historico_fx.xlsx.bak-20260923-1705": ("backup", "Delta - historico_fx.xlsx"),
        "Delta - historico_fx.parquet.12345-7.tmp": ("temporal", "Delta - historico_fx.parquet"),
        "Delta - historico_fx.xlsx.tmp.xlsx": ("temporal", "Delta - historico_fx.xlsx"),
        "Delta - historico_fx.parquet.tmp": ("temporal", "Delta - historico_fx.parquet"),
        "huerfano.parquet.tmp": ("temporal", None),
        "auth_store-NOTEBOOK.json": ("conflicto", "auth_store.json"),
        "2026-10-02-NOTEBOOK.parquet": ("conflicto", "2026-10-02.parquet"),
        "especies-NB-RC.py": ("conflicto", "especies.py"),
    }
    for nombre, (tipo, principal) in casos.items():
        c = copias.clasificar(nombre, vecinos | {nombre})
        assert c is not None, nombre
        assert (c["tipo"], c["principal"]) == (tipo, principal), nombre
    # archivos propios: no son copias (ni el lock de un Excel abierto)
    for nombre in sorted(vecinos) + ["~$Delta - historico_fx.xlsx", "Delta - historico_fx_2025.xlsx",
                                     "Delta - Especies.xlsx", "base_manifest.json"]:
        assert copias.clasificar(nombre, vecinos | {nombre}) is None, nombre


def _sembrar(carpetas) -> dict:
    """Base px/tasas con 2 ruedas + 5 copias de distinto tipo + un conflicto en app/."""
    bases, app = carpetas["bases"], carpetas["app"]
    xlsx = str(bases / hw.HIST_FILENAME)
    hw.append_and_save(_filas(D_ANT), xlsx)
    hw.append_and_save(_filas(D), xlsx)
    stem = os.path.splitext(hw.HIST_FILENAME)[0]
    copia_xlsx = str(bases / f"{stem}-NOTEBOOK-RC.xlsx")          # tiene la rueda D_SIG que la base no
    pd.concat([_filas(D_ANT), _filas(D), _filas(D_SIG)]).to_excel(copia_xlsx, index=False)
    copia_pq = str(bases / f"{stem} (2).parquet")                   # ⊆ base
    _filas(D_ANT).to_parquet(copia_pq, index=False)
    corrupto = str(bases / f"{hw.HIST_FILENAME}.corrupto-20260924-170101")
    with open(corrupto, "wb") as f:
        f.write(b"no soy un zip")
    tmp = str(bases / f"{stem}.parquet.4242-3.tmp")
    with open(tmp, "wb") as f:
        f.write(b"x" * 10)
    os.utime(tmp, (time.time() - 3600, time.time() - 3600))   # huérfano viejo: borrable (A07 sólo frena los recientes)
    (app / "auth_store.json").write_text('{"users": {}}', encoding="utf-8")
    json_copia = str(app / "auth_store-NOTEBOOK.json")
    with open(json_copia, "w", encoding="utf-8") as f:
        f.write('{"users": {"a": 1}}')
    (bases / "~$Delta - historico_byma_px_tasas.xlsx").write_bytes(b"lock")
    return {"xlsx": xlsx, "copia_xlsx": copia_xlsx, "copia_pq": copia_pq, "corrupto": corrupto,
            "tmp": tmp, "json_copia": json_copia}


def test_escanear_analizar_incorporar_y_borrar(carpetas) -> None:
    s = _sembrar(carpetas)
    ent = {e["nombre"]: e for e in copias.escanear()}
    assert set(ent) == {os.path.basename(p) for k, p in s.items() if k != "xlsx"}
    assert ent[os.path.basename(s["copia_xlsx"])]["tipo"] == "conflicto"
    assert ent[os.path.basename(s["copia_xlsx"])]["principal"] == s["xlsx"]
    assert ent[os.path.basename(s["copia_pq"])]["tipo"] == "copia"
    assert ent[os.path.basename(s["corrupto"])]["tipo"] == "corrupto"
    assert ent[os.path.basename(s["tmp"])]["tipo"] == "temporal"
    assert ent["auth_store-NOTEBOOK.json"]["carpeta"] == "app" and ent["auth_store-NOTEBOOK.json"]["tam"] == "19 B"
    # GET de la tarjeta: nada revisado todavía → sin veredicto (y sin leer archivos)
    sin = {e["nombre"]: e for e in copias.analizar(solo_cache=True)}
    assert sin[os.path.basename(s["copia_xlsx"])]["veredicto"] is None
    assert sin[os.path.basename(s["tmp"])]["aporta"] is False          # un .tmp no hace falta leerlo
    # Revisar: lee y compara con la principal
    rev = {e["nombre"]: e for e in copias.analizar()}
    cx = rev[os.path.basename(s["copia_xlsx"])]
    assert cx["aporta"] is True and cx["ruedas_extra"] == [D_SIG.isoformat()] and cx["incorporable"]
    assert cx["stats"]["ruedas"] == 3 and cx["principal_stats"]["ruedas"] == 2 and cx["mas_filas"]
    assert "aporta 1 rueda" in cx["veredicto"] and D_SIG.strftime("%d/%m") in cx["veredicto"]
    cp = rev[os.path.basename(s["copia_pq"])]
    assert cp["aporta"] is False and "no aporta" in cp["veredicto"] and "y 1 más" in cp["veredicto"]
    assert rev[os.path.basename(s["corrupto"])]["aporta"] is False
    assert rev["auth_store-NOTEBOOK.json"]["aporta"] is None and rev["auth_store-NOTEBOOK.json"]["stats"]["entradas"] == 1
    # ya revisado → el GET siguiente lo muestra sin releer
    otra = {e["nombre"]: e for e in copias.analizar(solo_cache=True)}
    assert otra[os.path.basename(s["copia_xlsx"])]["aporta"] is True
    grupos = copias.agrupar(rev.values())
    assert [g["carpeta"] for g in grupos][0] == "app" and any(g["principal_nombre"] == hw.HIST_FILENAME for g in grupos)
    # borrar: nunca un principal ni algo fuera de las carpetas
    assert "no es una copia" in copias.borrar(s["xlsx"])["error"] and os.path.isfile(s["xlsx"])
    assert "no está en una carpeta" in copias.borrar(__file__)["error"]
    r = copias.borrar(s["tmp"], quien="su_test")
    assert r["ok"] and not os.path.exists(s["tmp"])
    # incorporar: la rueda que sólo tiene la copia entra a la base; la copia queda
    r = copias.incorporar(s["copia_xlsx"], quien="su_test")
    assert r["ok"] and r["ruedas"] == [D_SIG.isoformat()] and r["filas"] == 3 and r["tipo"] == "px_tasas"
    assert set(hw._resumen_base(s["xlsx"])) == {D_ANT, D, D_SIG} and os.path.isfile(s["copia_xlsx"])
    assert hw.regresion_detalle(s["xlsx"])["ruedas"] == []
    assert "no tiene ruedas que le falten" in copias.incorporar(s["copia_xlsx"])["error"]
    # ahora la copia xlsx tampoco aporta → "Borrar las que no aportan" se la lleva con las otras
    r = copias.borrar_inutiles(quien="su_test")
    assert sorted(r["borradas"]) == sorted(os.path.basename(p) for p in (s["copia_xlsx"], s["copia_pq"], s["corrupto"]))
    assert not r["errores"] and os.path.isfile(s["json_copia"]) and os.path.isfile(s["xlsx"])
    assert copias.escanear() and {e["nombre"] for e in copias.escanear()} == {"auth_store-NOTEBOOK.json"}


def test_copia_mismas_fechas_mas_filas_no_se_borra_en_lote(carpetas) -> None:
    """A01: una copia con las MISMAS ruedas que la principal pero MÁS filas
    (instrumentos o correcciones dentro de esas fechas) NO debe quedar como
    'no aporta' (borrable en lote): queda para revisar/incorporar a mano."""
    bases = carpetas["bases"]
    xlsx = str(bases / hw.HIST_FILENAME)
    hw.append_and_save(_filas(D_ANT), xlsx)
    hw.append_and_save(_filas(D), xlsx)                      # base: ruedas D_ANT + D
    stem = os.path.splitext(hw.HIST_FILENAME)[0]
    copia = str(bases / f"{stem} (2).xlsx")                  # copia con las mismas ruedas + 1 fila
    pd.concat([_filas(D_ANT), _filas(D), _filas(D).head(1)]).to_excel(copia, index=False)
    rev = {e["nombre"]: e for e in copias.analizar()}
    c = rev[os.path.basename(copia)]
    assert c["aporta"] is None                               # NO False → "Borrar las que no aportan" la saltea
    assert c["mas_filas"] and not c["ruedas_extra"] and "revisar a mano" in c["veredicto"].lower()
    assert os.path.basename(copia) not in copias.borrar_inutiles(quien="su_test")["borradas"]
    assert os.path.isfile(copia)


def test_tmp_reciente_no_se_borra(carpetas) -> None:
    """A07: un .tmp recién escrito puede ser una escritura EN CURSO (el writer
    cerró el archivo pero todavía no hizo os.replace) → ni el análisis lo da
    por borrable ni `borrar` lo elimina; uno viejo sí."""
    bases = carpetas["bases"]
    stem = os.path.splitext(hw.HIST_FILENAME)[0]
    reciente = str(bases / f"{stem}.parquet.9999-1.tmp")
    with open(reciente, "wb") as f:
        f.write(b"x" * 10)                                   # mtime = ahora
    rev = {e["nombre"]: e for e in copias.analizar()}
    r = rev[os.path.basename(reciente)]
    assert r["tipo"] == "temporal" and r["aporta"] is None and "escritura en curso" in r["veredicto"]
    assert "reciente" in copias.borrar(reciente, quien="su_test")["error"] and os.path.isfile(reciente)
    assert os.path.basename(reciente) not in copias.borrar_inutiles(quien="su_test")["borradas"]
    # el mismo .tmp, ya viejo, sí es borrable
    os.utime(reciente, (time.time() - 3600, time.time() - 3600))
    copias._STATS.clear()
    assert {e["nombre"]: e for e in copias.analizar()}[os.path.basename(reciente)]["aporta"] is False
    assert copias.borrar(reciente, quien="su_test")["ok"] and not os.path.exists(reciente)


def test_incorporar_fx_desde_copia(carpetas) -> None:
    bases = carpetas["bases"]
    fx = str(bases / hw.FX_FILENAME)
    d1, d2, d3 = date(2026, 9, 22), date(2026, 9, 23), date(2026, 9, 24)
    hw.escribir_fx(pd.DataFrame({"fecha_hoy": [d1, d2], "ccl": [1400.0, 1410.0], "mep": [1380.0, 1390.0]}), fx)
    copia = str(bases / f"{os.path.splitext(hw.FX_FILENAME)[0]}-NOTEBOOK.xlsx")
    pd.DataFrame({"fecha_hoy": [d1, d2, d3], "ccl": [1400.0, 1410.0, 1420.0], "mep": [1380.0, 1390.0, 1400.0]}).to_excel(copia, index=False)
    e = {x["nombre"]: x for x in copias.analizar()}[os.path.basename(copia)]
    assert e["aporta"] is True and e["ruedas_extra"] == [d3.isoformat()] and e["incorporable"]
    r = copias.incorporar(copia)
    assert r["ok"] and r["tipo"] == "fx" and r["ruedas"] == [d3.isoformat()] and r["total_rows"] == 3
    back = pd.read_excel(fx)
    assert sorted(pd.to_datetime(back["fecha_hoy"]).dt.date) == [d1, d2, d3] and float(back["ccl"].iloc[-1]) == 1420.0


@pytest.mark.asyncio
async def test_http_tarjeta_copias_solo_superuser(carpetas, auth_on, monkeypatch) -> None:
    s = _sembrar(carpetas)
    async with _client() as ac:
        r = await ac.get("/admin/copias")
        assert r.status_code in (302, 401, 403)                       # sin sesión → al login
    async with _client() as su:
        r = await su.post("/login", data={"username": "su_test", "password": "clave-de-test-2026!", "next": "/yas"})
        assert r.status_code in (200, 303)
        r = await su.get("/admin/copias")
        assert r.status_code == 200 and os.path.basename(s["copia_xlsx"]) in r.text and "sin revisar" in r.text
        assert "Borrar las que no aportan" not in r.text
        r = await su.post("/admin/copias/revisar")
        assert r.status_code == 200 and "aporta 1 rueda" in r.text and "⤵ Incorporar" in r.text
        assert "Borrar las que no aportan (3)" in r.text
        r = await su.post("/admin/copias/borrar", data={"path": s["xlsx"]})
        assert r.status_code == 200 and "No se borró" in r.text and os.path.isfile(s["xlsx"])
        r = await su.post("/admin/copias/incorporar", data={"path": s["copia_xlsx"]})
        assert r.status_code == 200 and "Incorporado a la base px_tasas" in r.text
        assert set(hw._resumen_base(s["xlsx"])) == {D_ANT, D, D_SIG}
        r = await su.post("/admin/copias/borrar", data={"path": s["tmp"]})
        assert r.status_code == 200 and "✓ Borrado" in r.text and not os.path.exists(s["tmp"])
        r = await su.post("/admin/copias/borrar-inutiles")
        assert r.status_code == 200 and "Borradas 3 copias" in r.text
        r = await su.post("/admin/users", data={"username": "juan", "password": "clave123", "role": "basico", "email": ""})
        assert r.status_code < 400
    async with _client() as ac:
        r = await ac.post("/login", data={"username": "juan", "password": "clave123", "next": "/yas"})
        assert r.status_code in (200, 303)
        for metodo, ruta in (("get", "/admin/copias"), ("post", "/admin/copias/revisar"),
                             ("post", "/admin/copias/borrar"), ("post", "/admin/copias/incorporar")):
            r = await (ac.get(ruta) if metodo == "get" else ac.post(ruta, data={"path": s["json_copia"]}))
            assert r.status_code == 403, ruta
    assert os.path.isfile(s["json_copia"])
