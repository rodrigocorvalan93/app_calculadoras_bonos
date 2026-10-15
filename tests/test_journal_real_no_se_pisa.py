"""Sin perder historiales (15/10): un día que una PC capturó con precios REALES
en su journal local, sin ser writer ese día (sólo premium / básico la usó, o
falló la base), nunca se reconstruye con RC encima.

Lo encontró la revisión del cambio "sólo el superuser escribe la base" (#254):
el día siguiente, al entrar el superuser, `reconstruir_faltantes` veía el día
como hueco (no mira el journal), lo rearmaba desde los cierres del feed,
pisaba el journal real con filas RC y escribía RC en la base. Además el
catch-up del arranque (`consolidar_journal`) corre antes de que entre nadie y,
con el muro de login, nunca hacía nada."""
from __future__ import annotations

import asyncio

import pandas as pd

from backend.config import settings
from backend.services import auth, historico_writer as hw
from tests.test_cierre_reconstruccion import (D, D_ANT, _ba, _base_parquet, _codigos_calculables,  # noqa: F401
                                              _df_base, _sembrar_cierres, env)
from tests.test_historico_writer import auth_on  # noqa: F401

# ruff: noqa: F811 — los fixtures importados se piden por nombre como parámetro (patrón pytest)


def _dia_capturado_sin_writer(env, monkeypatch) -> tuple:
    """Base con D-1; D sólo en el journal local con filas LA (como lo deja
    save_today en una instancia que ese día no era writer). Devuelve (codes, xlsx)."""
    auth._VISTOS.clear()
    monkeypatch.setattr(hw, "_WRITER_HEADLESS", False)
    monkeypatch.setattr(settings, "historico_base_writer", True)
    codes = _codigos_calculables(3)
    xlsx = str(env / hw.HIST_FILENAME)
    hw.append_and_save(_df_base(D_ANT, [(c, 100.0 + i, 99.0) for i, c in enumerate(codes)]), xlsx,
                       incluir_journal=False)
    hw.write_journal(_df_base(D, [(c, 111.0 + i, 100.0 + i) for i, c in enumerate(codes)]), D)
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 9, 24, 10, 0))
    return codes, xlsx


def _dia_en_base(env, dia) -> pd.DataFrame:
    b = _base_parquet(env)
    b["fecha_hoy"] = pd.to_datetime(b["fecha_hoy"]).dt.date
    return b[b["fecha_hoy"] == dia]


def test_reconstruir_faltantes_consolida_el_journal_real_y_no_lo_pisa(env, auth_on, monkeypatch) -> None:
    codes, _xlsx = _dia_capturado_sin_writer(env, monkeypatch)
    assert hw.consolidar_journal() is None                    # arranque: todavía no entró nadie
    _sembrar_cierres(codes, D)                                # el feed trae los CL de D (101, 102, 103)
    auth.marcar_visto("su_test")                              # entra el superuser
    assert hw.es_writer()
    r = hw.reconstruir_faltantes()
    d = _dia_en_base(env, D)
    assert set(d["Price Source"]) == {"LA"}                   # la base tiene el cierre REAL, no RC
    assert sorted(d["Last Price"]) == [111.0, 112.0, 113.0]
    j = pd.read_parquet(hw._journal_days()[D])
    assert set(j["Price Source"]) == {"LA"} and sorted(j["Last Price"]) == [111.0, 112.0, 113.0]
    res = next(x for x in r["resultados"] if x["dia"] == D.isoformat())
    assert res["ok"] and res["fuente"] == "journal" and D.isoformat() in r["reconstruidos"]


def test_reconstruir_cierre_forzado_reemplaza_rc_con_el_journal_real(env, auth_on, monkeypatch) -> None:
    """Botón "Reconstruir" (force) sobre un día que la base ya tiene como RC:
    si el journal local lo tiene real, entran las filas reales."""
    codes, xlsx = _dia_capturado_sin_writer(env, monkeypatch)
    hw.append_and_save(_df_base(D, [(c, 101.0 + i, 100.0 + i) for i, c in enumerate(codes)], source="RC"),
                       xlsx, incluir_journal=False)
    assert set(_dia_en_base(env, D)["Price Source"]) == {"RC"}
    auth.marcar_visto("su_test")
    r = hw.reconstruir_cierre(D, force=True)
    assert r["ok"] and r["fuente"] == "journal" and r["rows"] == 3
    d = _dia_en_base(env, D)
    assert set(d["Price Source"]) == {"LA"} and sorted(d["Last Price"]) == [111.0, 112.0, 113.0]


def test_sin_journal_real_sigue_la_reconstruccion_de_siempre(env, auth_on, monkeypatch) -> None:
    """Un journal de D que sólo tiene RC (una reconstrucción anterior) no
    frena nada: se rearma desde el feed como siempre."""
    codes, xlsx = _dia_capturado_sin_writer(env, monkeypatch)
    hw.write_journal(_df_base(D, [(c, 90.0, 89.0) for c in codes], source="RC"), D)
    _sembrar_cierres(codes, D)
    auth.marcar_visto("su_test")
    r = hw.reconstruir_cierre(D)
    assert r["ok"] and r["fuente"] == "feed"
    assert set(_dia_en_base(env, D)["Price Source"]) == {"RC"}


def test_el_arranque_consolida_el_journal_cuando_entra_el_superuser(env, auth_on, monkeypatch) -> None:
    """El catch-up del principio de `_run` corre sin nadie logueado; el de
    `_reconstruir_al_arrancar` corre DESPUÉS de esperar al superuser: el día
    entra desde el journal aunque el feed no traiga nada."""
    _dia_capturado_sin_writer(env, monkeypatch)
    auth.marcar_visto("su_test")
    monkeypatch.setattr(settings, "primary_user", "")         # sin broker: no espera snapshot

    async def correr() -> None:
        await hw.HistoricoAutosave()._reconstruir_al_arrancar(asyncio.get_running_loop())

    asyncio.run(correr())
    d = _dia_en_base(env, D)
    assert set(d["Price Source"]) == {"LA"} and len(d) == 3


def test_fx_desde_journal_toma_mep_de_bonares_y_ccl_de_globales(monkeypatch) -> None:
    from backend.services import patas
    sob = {"AL30": patas.Pata("AL30", "AL30D", patas.ARS, False, "USB"),
           "GD30": patas.Pata("GD30", "GD30C", patas.ARS, False, "USD"),
           "AL30C": patas.Pata("AL30C", "AL30D", patas.CABLE, True, "USB")}
    monkeypatch.setattr(patas, "soberanas", lambda: sob)
    jf = pd.DataFrame({"Código": ["AL30D", "AL30", "GD30", "AL30C"],
                       "Pata": [None, "ARS", "ARS", "CABLE"],
                       "FX": [None, 1450.0, 1500.0, None]})
    fx = hw._fx_desde_journal(jf)
    assert fx.usb == 1450.0 and fx.ccl == 1500.0 and fx.ccl_base == "journal"
    assert hw._fx_desde_journal(jf.drop(columns=["Pata"])) is None        # journal de antes del 13/10
    assert hw._fx_desde_journal(pd.DataFrame()) is None


# ── poda y catch-up sin perder historiales (15/10) ───────────────────────────
def _particion(dia, last: float, *, vivos: bool):
    df = pd.DataFrame([{"fecha_hoy": dia, "symbol": "MERV - XMEV - TX26 - 24hs", "code": "TX26", "plazo": "24hs",
                        "last": last, "close": last - 1, "volume": (1_000_000.0 if vivos else None),
                        "bid": (last - 0.5 if vivos else None), "opero": True}])
    for col in ("symbol", "code", "plazo"):
        df[col] = df[col].astype("string")
    return df


def test_la_poda_no_borra_un_journal_que_es_la_unica_copia(env, monkeypatch) -> None:
    """Antes `_prune_journal` borraba por edad (90 días) aunque la base no
    tuviera la rueda o la tuviera sólo como RC."""
    from datetime import date as _date
    codes = _codigos_calculables(3)
    xlsx = str(env / hw.HIST_FILENAME)
    a, b, c = _date(2026, 5, 4), _date(2026, 5, 5), _date(2026, 5, 6)
    hw.append_and_save(_df_base(a, [(x, 100.0, 99.0) for x in codes]), xlsx, incluir_journal=False)
    hw.append_and_save(_df_base(b, [(x, 100.0, 99.0) for x in codes], source="RC"), xlsx, incluir_journal=False)
    for d in (a, b, c):                                       # journal real de las tres
        hw.write_journal(_df_base(d, [(x, 101.0, 100.0) for x in codes]), d)
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 9, 24, 17, 5))
    hw._prune_journal(hist_dir=str(env))
    dias = hw._journal_days()
    assert a not in dias                                      # la base la tiene real: se poda
    assert b in dias and c in dias                            # RC en la base / falta en la base: quedan
    # cierre completo: sin partición, o con una armada desde la base y el journal con datos vivos → queda
    hw.write_cierre_journal(_particion(a, 101.0, vivos=True), a)
    hw.write_cierre_journal(_particion(b, 101.0, vivos=True), b)
    hw.write_cierre_journal(_particion(c, 101.0, vivos=False), c)
    hw.escribir_particion(_particion(a, 101.0, vivos=True), str(env), a)     # la real
    hw.escribir_particion(_particion(b, 101.0, vivos=False), str(env), b)    # armada desde la base
    hw.escribir_particion(_particion(c, 101.0, vivos=False), str(env), c)    # el journal tampoco tiene vivos
    hw._prune_journal(hist_dir=str(env))
    cj = hw._cierre_journal_days()
    assert a not in cj and c not in cj and b in cj


def test_consolidar_sube_a_real_un_dia_que_la_base_tiene_solo_como_rc(env, monkeypatch) -> None:
    codes = _codigos_calculables(3)
    xlsx = str(env / hw.HIST_FILENAME)
    hw.append_and_save(_df_base(D_ANT, [(x, 100.0, 99.0) for x in codes]), xlsx, incluir_journal=False)
    hw.append_and_save(_df_base(D, [(x, 90.0, 89.0) for x in codes], source="RC"), xlsx, incluir_journal=False)
    hw.write_journal(_df_base(D, [(x, 111.0 + i, 100.0) for i, x in enumerate(codes)]), D)
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 9, 24, 10, 0))
    assert hw.es_writer()
    r = hw.consolidar_journal()
    assert r and r.get("consolidados") == 1
    d = _dia_en_base(env, D)
    assert set(d["Price Source"]) == {"LA"} and sorted(d["Last Price"]) == [111.0, 112.0, 113.0]
    assert hw.consolidar_journal() is None                    # ya está: no-op


def test_catch_up_reemplaza_una_particion_armada_desde_la_base(env, monkeypatch) -> None:
    from backend.services import cierres
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 9, 24, 10, 0))
    hw.escribir_particion(_particion(D, 101.0, vivos=False), str(env), D)    # importar_base: sin volumen
    hw.write_cierre_journal(_particion(D, 101.0, vivos=True), D)            # la captura real
    r = hw.consolidar_cierres_journal()
    assert r == {"consolidados": 1, "dias": [D.isoformat()], "errores": {}}
    part = pd.read_parquet(hw.cierre_path(str(env), D))
    assert float(part["volume"].iloc[0]) == 1_000_000.0
    assert hw.consolidar_cierres_journal() is None            # ya tiene la real: no-op
    # una partición REAL nunca se pisa con el journal
    hw.write_cierre_journal(_particion(D, 999.0, vivos=True), D)
    assert hw.consolidar_cierres_journal() is None
    assert float(pd.read_parquet(hw.cierre_path(str(env), D))["last"].iloc[0]) == 101.0
    cierres.refresh()


def test_la_poda_compara_claves_no_conteos(env, monkeypatch) -> None:
    """Revisión 15/10: con IGUALES conteos la base y el journal pueden tener
    símbolos distintos (permisos de market data por cuenta). La poda compara
    claves (symbol, Código): un journal con un símbolo que la base no tiene
    queda; un cierre_ con un símbolo que la partición no tiene, también."""
    from datetime import date as _date
    codes = _codigos_calculables(4)
    xlsx = str(env / hw.HIST_FILENAME)
    d = _date(2026, 5, 4)
    hw.append_and_save(_df_base(d, [(x, 100.0, 99.0) for x in codes[:3]]), xlsx, incluir_journal=False)
    hw.write_journal(_df_base(d, [(x, 100.0, 99.0) for x in codes[1:4]]), d)   # 3 y 3, distinto set
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 9, 24, 17, 5))
    hw._prune_journal(hist_dir=str(env))
    assert d in hw._journal_days()
    # cierre_: la partición existe con datos vivos pero sin uno de los símbolos del journal
    j = pd.concat([_particion(d, 101.0, vivos=True),
                   _particion(d, 50.0, vivos=True).assign(symbol=pd.array(["MERV - XMEV - GD30 - 24hs"], dtype="string"))])
    hw.write_cierre_journal(j, d)
    hw.escribir_particion(_particion(d, 101.0, vivos=True), str(env), d)
    hw._prune_journal(hist_dir=str(env))
    assert d in hw._cierre_journal_days()
    hw.escribir_particion(j, str(env), d)                     # ahora sí la contiene
    hw._prune_journal(hist_dir=str(env))
    assert d not in hw._cierre_journal_days()


def test_el_catch_up_escribe_la_fila_fx_del_dia_que_entra(env, monkeypatch) -> None:
    """Revisión 15/10: un día que entra a la base desde el journal por el
    catch-up (no por el botón) también recibe su fila FX (CCL/MEP de la
    columna FX de las patas en pesos)."""
    from backend.services import patas
    codes = _codigos_calculables(3)
    xlsx = str(env / hw.HIST_FILENAME)
    hw.append_and_save(_df_base(D_ANT, [(x, 100.0, 99.0) for x in codes]), xlsx, incluir_journal=False)
    sob = {"AL30": patas.Pata("AL30", "AL30D", patas.ARS, False, "USB"),
           "GD30": patas.Pata("GD30", "GD30C", patas.ARS, False, "USD")}
    monkeypatch.setattr(patas, "soberanas", lambda: sob)
    jf = _df_base(D, [(x, 111.0, 100.0) for x in codes] + [("AL30", 90000.0, 89000.0), ("GD30", 95000.0, 94000.0)])
    jf["Pata"] = [None] * len(codes) + ["ARS", "ARS"]
    jf["FX"] = [None] * len(codes) + [1450.0, 1500.0]
    hw.write_journal(jf, D)
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 9, 24, 10, 0))
    assert hw.consolidar_journal()["consolidados"] == 1
    fx = pd.read_excel(str(env / hw.FX_FILENAME))
    fila = fx[pd.to_datetime(fx["fecha_hoy"]).dt.date == D].iloc[0]
    assert float(fila["mep"]) == 1450.0 and float(fila["ccl"]) == 1500.0


def test_el_banner_dice_filas_reales_cuando_viene_del_journal() -> None:
    from backend.routes.historico import _msg_reconstruccion
    m = _msg_reconstruccion({"ok": True, "fuente": "journal", "dia_fmt": "23/09/2026", "rows": 480,
                             "total_rows": 9000})
    assert "consolidado desde el journal local" in m and "480 filas reales (no RC)" in m and "RC desde" not in m
    m2 = _msg_reconstruccion({"ok": True, "fuente": "feed", "dia_fmt": "23/09/2026", "rows": 480, "total_rows": 9000})
    assert "reconstruido desde los cierres del feed" in m2 and "filas RC" in m2
