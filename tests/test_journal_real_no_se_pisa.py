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
