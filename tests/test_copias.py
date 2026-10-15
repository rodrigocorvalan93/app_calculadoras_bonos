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
    # un .tmp tampoco se da por borrable sin leerlo (15/10: uno legible puede
    # ser la única copia de una escritura que no llegó al replace)
    assert sin[os.path.basename(s["tmp"])]["aporta"] is None
    # Revisar: lee y compara con la principal
    rev = {e["nombre"]: e for e in copias.analizar()}
    cx = rev[os.path.basename(s["copia_xlsx"])]
    assert cx["aporta"] is True and cx["ruedas_extra"] == [D_SIG.isoformat()] and cx["incorporable"]
    assert cx["stats"]["ruedas"] == 3 and cx["principal_stats"]["ruedas"] == 2 and cx["mas_filas"]
    assert "aporta 1 rueda" in cx["veredicto"] and D_SIG.strftime("%d/%m") in cx["veredicto"]
    cp = rev[os.path.basename(s["copia_pq"])]
    assert cp["aporta"] is False and "no aporta" in cp["veredicto"] and "y 1 más" in cp["veredicto"]
    # apartado ilegible: puede tener datos recuperables a mano → NO en lote
    assert rev[os.path.basename(s["corrupto"])]["aporta"] is None
    assert "NO se borra en lote" in rev[os.path.basename(s["corrupto"])]["veredicto"]
    # el .tmp (10 bytes basura: escritura cortada) sí: no tiene nada recuperable
    assert rev[os.path.basename(s["tmp"])]["aporta"] is False
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
    # ahora la copia xlsx tampoco aporta (cada fila está en la base) → "Borrar
    # las que no aportan" se la lleva con la otra; el apartado ilegible queda
    r = copias.borrar_inutiles(quien="su_test")
    assert sorted(r["borradas"]) == sorted(os.path.basename(p) for p in (s["copia_xlsx"], s["copia_pq"]))
    assert not r["errores"] and os.path.isfile(s["json_copia"]) and os.path.isfile(s["xlsx"])
    assert os.path.isfile(s["corrupto"])
    assert {e["nombre"] for e in copias.escanear()} == {"auth_store-NOTEBOOK.json", os.path.basename(s["corrupto"])}


def test_copia_mismas_fechas_mas_filas_no_se_borra_en_lote(carpetas) -> None:
    """A01: una copia con las MISMAS ruedas que la principal pero con una fila
    que la principal no tiene (instrumento nuevo o corrección dentro de esas
    fechas) NO debe quedar como 'no aporta' (borrable en lote): queda para
    revisar/incorporar a mano. Una fila repetida idéntica, en cambio, no trae
    nada (15/10: contención fila por fila, no por totales)."""
    bases = carpetas["bases"]
    xlsx = str(bases / hw.HIST_FILENAME)
    hw.append_and_save(_filas(D_ANT), xlsx)
    hw.append_and_save(_filas(D), xlsx)                      # base: ruedas D_ANT + D
    stem = os.path.splitext(hw.HIST_FILENAME)[0]
    copia = str(bases / f"{stem} (2).xlsx")                  # mismas ruedas + 1 fila corregida
    corregida = _filas(D).head(1).copy()
    corregida["Last Price"] = corregida["Last Price"] + 0.5
    pd.concat([_filas(D_ANT), _filas(D), corregida]).to_excel(copia, index=False)
    rev = {e["nombre"]: e for e in copias.analizar()}
    c = rev[os.path.basename(copia)]
    assert c["aporta"] is None                               # NO False → "Borrar las que no aportan" la saltea
    assert c["mas_filas"] and not c["ruedas_extra"] and "revisar a mano" in c["veredicto"].lower()
    assert "1 fila" in c["veredicto"]
    assert os.path.basename(copia) not in copias.borrar_inutiles(quien="su_test")["borradas"]
    assert os.path.isfile(copia)
    # la misma copia con la fila repetida IDÉNTICA: todo está en la principal
    dup = str(bases / f"{stem} (3).xlsx")
    pd.concat([_filas(D_ANT), _filas(D), _filas(D).head(1)]).to_excel(dup, index=False)
    d = {e["nombre"]: e for e in copias.analizar()}[os.path.basename(dup)]
    assert d["aporta"] is False and "todas sus filas ya están" in d["veredicto"]


def test_contencion_estricta_rc_y_celdas_fx(carpetas) -> None:
    """15/10, "sin perder historiales": casos que el veredicto por fechas daba
    por borrables y tenían historia única."""
    bases = carpetas["bases"]
    xlsx = str(bases / hw.HIST_FILENAME)
    stem = os.path.splitext(hw.HIST_FILENAME)[0]
    # (1) la base tiene D sólo como RC; la copia lo tiene con precios reales
    hw.append_and_save(_filas(D_ANT), xlsx)
    rc = _filas(D).copy()
    rc["Price Source"] = hw.PRICE_SOURCE_RC
    hw.append_and_save(rc, xlsx)
    copia = str(bases / f"{stem}-NOTEBOOK.parquet")
    _filas(D).to_parquet(copia, index=False)                 # reales, misma rueda
    e = {x["nombre"]: x for x in copias.analizar()}[os.path.basename(copia)]
    assert e["aporta"] is None and not e["ruedas_extra"]
    # (2) FX: misma fecha, la copia trae una celda de caución que la principal no
    fx = str(bases / hw.FX_FILENAME)
    d1 = date(2026, 9, 22)
    hw.escribir_fx(pd.DataFrame({"fecha_hoy": [d1], "ccl": [1400.0], "mep": [1380.0]}), fx)
    cfx = str(bases / f"{os.path.splitext(hw.FX_FILENAME)[0]}-NOTEBOOK.xlsx")
    pd.DataFrame({"fecha_hoy": [d1], "ccl": [1400.0], "mep": [1380.0], "caucion_tna": [0.31]}).to_excel(cfx, index=False)
    f = {x["nombre"]: x for x in copias.analizar()}[os.path.basename(cfx)]
    assert f["aporta"] is None and "1 fila/celda" in f["veredicto"]
    # (3) un temporal LEGIBLE con datos que la principal no tiene no se borra en lote
    tmp = str(bases / f"{stem}.parquet.777-1.tmp")
    _filas(D_SIG).to_parquet(tmp, index=False)
    os.utime(tmp, (time.time() - 3600, time.time() - 3600))
    t = {x["nombre"]: x for x in copias.analizar()}[os.path.basename(tmp)]
    assert t["aporta"] is True and t["ruedas_extra"] == [D_SIG.isoformat()]
    borradas = copias.borrar_inutiles(quien="su_test")["borradas"]
    assert not {os.path.basename(copia), os.path.basename(cfx), os.path.basename(tmp)} & set(borradas)


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
        assert "Borrar las que no aportan (2)" in r.text          # el apartado ilegible no entra
        r = await su.post("/admin/copias/borrar", data={"path": s["xlsx"]})
        assert r.status_code == 200 and "No se borró" in r.text and os.path.isfile(s["xlsx"])
        r = await su.post("/admin/copias/incorporar", data={"path": s["copia_xlsx"]})
        assert r.status_code == 200 and "Incorporado a la base px_tasas" in r.text
        assert set(hw._resumen_base(s["xlsx"])) == {D_ANT, D, D_SIG}
        r = await su.post("/admin/copias/borrar", data={"path": s["tmp"]})
        assert r.status_code == 200 and "✓ Borrado" in r.text and not os.path.exists(s["tmp"])
        r = await su.post("/admin/copias/borrar-inutiles")
        assert r.status_code == 200 and "Borradas 2 copias" in r.text
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


def test_revision_1510_multihoja_metricas_y_una_lectura_de_la_principal(carpetas, monkeypatch) -> None:
    """Revisión del 15/10 sobre la contención estricta:
    (1) un libro de VARIAS hojas (Delta - Especies) con la edición en la
        segunda hoja no puede salir 'no aporta' mirando sólo la primera;
    (2) una copia px/tasas con una MÉTRICA corregida (TIREA) no está contenida;
    (3) la principal se lee UNA vez para todas sus copias, y desde el espejo
        parquet fiel cuando es un xlsx."""
    bases = carpetas["bases"]
    # (1) multi-hoja
    especies = bases / "Delta - Especies.xlsx"
    with pd.ExcelWriter(especies) as w:
        pd.DataFrame({"a": [1, 2]}).to_excel(w, sheet_name="Hoja1", index=False)
        pd.DataFrame({"Ticker": ["AL30"]}).to_excel(w, sheet_name="Base RF", index=False)
    copia_esp = bases / "Delta - Especies-NOTEBOOK.xlsx"
    with pd.ExcelWriter(copia_esp) as w:
        pd.DataFrame({"a": [1, 2]}).to_excel(w, sheet_name="Hoja1", index=False)
        pd.DataFrame({"Ticker": ["AL30", "GD30"]}).to_excel(w, sheet_name="Base RF", index=False)
    # (2) métrica corregida
    xlsx = str(bases / hw.HIST_FILENAME)
    hw.append_and_save(_filas(D_ANT), xlsx)
    stem = os.path.splitext(hw.HIST_FILENAME)[0]
    corr = _filas(D_ANT).copy()
    corr.loc[corr.index[0], "TIREA"] = 0.0359
    copia_tir = bases / f"{stem}-NB-TIR.parquet"
    corr.to_parquet(copia_tir, index=False)
    igual = bases / f"{stem}-NB-IGUAL.parquet"
    _filas(D_ANT).to_parquet(igual, index=False)
    lecturas: list[str] = []
    real = copias._leer_copia
    monkeypatch.setattr(copias, "_leer_copia", lambda p: (lecturas.append(os.path.basename(p)), real(p))[1])
    copias._PRINC_MEMO.clear()
    copias._CONT_MEMO.clear()
    rev = {e["nombre"]: e for e in copias.analizar()}
    assert rev[copia_esp.name]["aporta"] is None                         # (1) no se borra en lote
    assert rev[copia_tir.name]["aporta"] is None and "1 fila" in rev[copia_tir.name]["veredicto"]   # (2)
    assert rev[igual.name]["aporta"] is False                            # idéntica: sí
    # (3) la base se leyó UNA vez (y por su espejo parquet), no una por copia
    assert lecturas.count(f"{stem}.parquet") == 1 and f"{stem}.xlsx" not in lecturas
    borradas = copias.borrar_inutiles(quien="su_test")["borradas"]
    assert igual.name in borradas and copia_esp.name not in borradas and copia_tir.name not in borradas
