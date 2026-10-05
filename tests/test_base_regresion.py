"""La base histórica NUNCA pierde ruedas (backend/services/historico_writer, 05/10/2026).

Caso real: la notebook arrancó con una réplica de OneDrive atrasada y escribió
la base compartida → se perdieron 5 ruedas; al rato el chip las acusaba como
"huecos" y Reconstruir las rearmaba con filas RC… que la siguiente escritura
de la otra máquina volvía a pisar.

- `_resumen_base`: fuente FIEL (espejo si es copia del Excel, si no el Excel;
  la firma del espejo cubre también el tamaño del parquet).
- memoria local (`base_vista.json`) + manifiesto compartido (`base_manifest.json`)
  → `regresion_detalle`: ruedas perdidas / degradadas, recuperables (journal
  propio con filas reales) y bloqueantes.
- `append_and_save` lanza `BaseEnRegresion` con bloqueantes; con sólo
  recuperables repone del journal (también filas reales pisadas por RC).
- `save_today` → skipped+retry (el journal local sí se escribe);
  `consolidar_journal` frenado salvo `reponer`; `reconstruir_cierre` /
  `reconstruir_faltantes` frenados; Reconstruir nunca pisa filas reales.
- `aceptar_base_actual`; banner `regresion` con Reponer / Aceptar (superuser).
- `_disparo_vencido`: el temporizador del autosave que saltó al despertar.
"""
from __future__ import annotations

import os
import shutil
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
from httpx import ASGITransport, AsyncClient

from backend.config import settings
from backend.services import espejo, historico_writer as hw
from tests.test_cierre_reconstruccion import D, D_ANT, D_SIG, _ba, _df_base, env  # noqa: F401 — fixture + helpers
from tests.test_historico_writer import _client, auth_on  # noqa: F401

# ruff: noqa: F811 — los fixtures importados (`env`, `auth_on`) se piden por
# nombre como parámetro de cada test: patrón pytest, no una redefinición.

_TZ = ZoneInfo("America/Argentina/Buenos_Aires")
CODES = ["T30E6", "S31L6", "TZX26"]            # la base no valida tickers


def _xlsx(env) -> str:
    return str(env / hw.HIST_FILENAME)


def _pq(env) -> str:
    return _xlsx(env).replace(".xlsx", ".parquet")


def _filas(fecha, source: str = "LA", precio: float = 100.0) -> pd.DataFrame:
    return _df_base(fecha, [(c, precio + i, precio - 1 + i) for i, c in enumerate(CODES)], source=source)


def _version_ajena(env, frames) -> None:
    """Lo que OneDrive deja cuando trae la base de OTRA máquina: xlsx + parquet
    + firma consistentes entre sí (espejo fiel) pero con otras ruedas; el
    manifiesto compartido y la memoria local no cambian."""
    df = pd.concat(frames, ignore_index=True)
    df.to_parquet(_pq(env), index=False)
    df.to_excel(_xlsx(env), index=False)
    espejo.marcar_espejo(_pq(env), _xlsx(env))
    hw._fechas_cache = ()


def _ruedas_excel(env) -> list:
    back = pd.read_excel(_xlsx(env), parse_dates=["fecha_hoy"])
    return sorted(set(back["fecha_hoy"].dt.date))


def test_fuente_fiel_cuando_el_espejo_no_es_copia_del_excel(env, monkeypatch) -> None:
    """Parquet viejo al lado de un Excel nuevo (OneDrive trajo uno y no el otro):
    manda el Excel — ni hueco falso ni Reconstruir pisando filas reales."""
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 9, 25, 10, 0))
    hw.append_and_save(_filas(D_ANT), _xlsx(env))
    viejo = str(env / "viejo.parquet")
    shutil.copy(_pq(env), viejo)
    hw.append_and_save(_filas(D), _xlsx(env))
    assert hw._fechas_base(_xlsx(env)) == {D_ANT, D}
    shutil.copy(viejo, _pq(env))                             # el espejo vuelve a ser el viejo (otro tamaño)
    hw._fechas_cache = ()
    assert not espejo.espejo_valido(_pq(env), _xlsx(env))      # la firma también cubre el tamaño del parquet
    assert hw._fechas_base(_xlsx(env)) == {D_ANT, D}           # fuente fiel: el Excel
    assert hw.huecos_base() == [D_SIG]                         # el 24/09 falta de verdad; el 23/09 NO es hueco
    res = hw.reconstruir_cierre(D, force=True)
    assert res["ok"] is False and "filas reales" in res["skipped"], res
    assert _ruedas_excel(env) == [D_ANT, D]


def test_regresion_frena_escrituras_y_el_journal_la_repone(env, monkeypatch) -> None:
    xlsx = _xlsx(env)
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 9, 24, 17, 5))          # jueves 24/09, al cierre
    hw.append_and_save(_filas(D_ANT), xlsx)
    hw.append_and_save(_filas(D), xlsx)
    m = hw._manifest_leer(xlsx)
    assert m["host"] == hw._host() and sorted(m["fechas"]) == [D_ANT, D] and m["fechas"][D] == (3, 3)
    assert hw._vista_de(xlsx)[D] == (3, 3)
    assert hw.regresion_detalle(xlsx)["ruedas"] == []
    # OneDrive trae la base de otra máquina SIN el 23/09
    _version_ajena(env, [_filas(D_ANT)])
    reg = hw.regresion_detalle(xlsx)
    assert reg["ruedas"] == [D] and reg["bloqueantes"] == [D] and reg["recuperables"] == []
    assert reg["detalle"][D]["motivo"] == "falta" and reg["manifest"]["host"] == hw._host()
    e = hw.estado_cierre()
    assert e["estado"] == "regresion" and e["regresion"] == [D.isoformat()] and "perdió 1 rueda" in e["texto"]
    assert "23/09" in e["detalle"] and "No se escribe encima" in e["detalle"]
    # ninguna escritura compartida pasa: autosave (el journal local sí), catch-up, reconstrucción
    monkeypatch.setattr(settings, "historico_autosave_min_operados", 1)
    monkeypatch.setattr(hw, "build_rows", lambda plazo="24hs": _filas(D_SIG))
    res = hw.save_today()
    assert res["ok"] is False and res["retry"] is True and res["regresion"] == [D.isoformat()], res
    assert "perdió ruedas" in res["skipped"] and D_SIG in hw._journal_days()
    assert _ruedas_excel(env) == [D_ANT]                                       # la base no se tocó
    with pytest.raises(hw.BaseEnRegresion):
        hw.append_and_save(_filas(D_SIG), xlsx)
    r = hw.consolidar_journal()
    assert r["skipped"] == "base en regresión" and r["bloqueantes"] == [D.isoformat()]
    assert "regresión" in hw.reconstruir_cierre(D)["skipped"]
    assert "regresión" in hw.reconstruir_faltantes()["skipped"]
    # el journal de ESTA máquina tiene el 23/09 con precios reales → el próximo guardado lo repone
    hw.write_journal(_filas(D), D)
    reg = hw.regresion_detalle(xlsx)
    assert reg["recuperables"] == [D] and reg["bloqueantes"] == []
    res = hw.save_today()
    assert res["ok"] is True, res
    assert _ruedas_excel(env) == [D_ANT, D, D_SIG]
    assert hw.regresion_detalle(xlsx)["ruedas"] == [] and hw.estado_cierre()["estado"] == "ok"
    assert sorted(hw._manifest_leer(xlsx)["fechas"]) == [D_ANT, D, D_SIG]


def test_filas_reales_pisadas_por_rc_es_regresion_y_se_reponen(env, monkeypatch) -> None:
    xlsx = _xlsx(env)
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 9, 25, 10, 0))
    hw.append_and_save(_filas(D_ANT), xlsx)
    hw.append_and_save(_filas(D), xlsx)
    hw.write_journal(_filas(D), D)                                 # esta máquina capturó el 23/09 real
    _version_ajena(env, [_filas(D_ANT), _filas(D, source="RC")])  # otra máquina lo rearmó con RC
    reg = hw.regresion_detalle(xlsx)
    assert reg["ruedas"] == [D] and reg["detalle"][D]["motivo"] == "sus filas reales pasaron a RC"
    assert reg["recuperables"] == [D] and reg["bloqueantes"] == []
    r = hw.consolidar_journal()                                    # catch-up al arrancar: repone las reales
    assert r and r["consolidados"] == 1, r
    back = pd.read_parquet(_pq(env))
    back["fecha_hoy"] = pd.to_datetime(back["fecha_hoy"]).dt.date
    assert set(back[back["fecha_hoy"] == D]["Price Source"].astype(str)) == {"LA"}
    assert hw.regresion_detalle(xlsx)["ruedas"] == []


def test_manifiesto_detecta_sin_memoria_local_y_aceptar_base(env, monkeypatch) -> None:
    xlsx = _xlsx(env)
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 9, 25, 10, 0))
    hw.append_and_save(_filas(D_ANT), xlsx)
    hw.append_and_save(_filas(D), xlsx)
    # máquina nueva (sin memoria local): el manifiesto compartido alcanza
    os.remove(hw._vista_path())
    hw._vista_mem = ()
    _version_ajena(env, [_filas(D_ANT)])
    reg = hw.regresion_detalle(xlsx)
    assert reg["ruedas"] == [D] and reg["bloqueantes"] == [D]
    with pytest.raises(hw.BaseEnRegresion) as ei:
        hw.append_and_save(_filas(D_SIG), xlsx)
    assert "última escritura" in str(ei.value) and hw._host() in str(ei.value)
    # el superuser da por buena la base tal como está
    r = hw.aceptar_base_actual()
    assert r["ok"] is True and r["ruedas"] == 1 and r["ultima"] == D_ANT.isoformat()
    assert hw.regresion_detalle(xlsx)["ruedas"] == [] and hw.estado_cierre()["estado"] != "regresion"
    assert sorted(hw._manifest_leer(xlsx)["fechas"]) == [D_ANT] and sorted(hw._vista_de(xlsx)) == [D_ANT]
    hw.append_and_save(_filas(D_SIG), xlsx)                        # vuelve a escribir
    assert _ruedas_excel(env) == [D_ANT, D_SIG]


def test_journal_del_dia_que_se_escribe_no_se_consolida_dos_veces(env, monkeypatch) -> None:
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 9, 25, 10, 0))
    hw.write_journal(_filas(D), D)                  # la reconstrucción journalea y después escribe la base
    r = hw.append_and_save(_filas(D), _xlsx(env))
    assert r["consolidados"] == 0 and r["total_rows"] == 3


def test_disparo_vencido_al_despertar() -> None:
    sab = _ba(2026, 10, 3, 17, 1)
    assert hw._disparo_vencido(sab, _ba(2026, 10, 5, 11, 14)) is True        # saltó el lunes, al despertar
    assert hw._disparo_vencido(sab, _ba(2026, 10, 3, 17, 2)) is False
    assert hw._disparo_vencido(sab, _ba(2026, 10, 3, 18, 36)) is False       # dentro de la ventana de reintentos
    assert hw._disparo_vencido(sab, _ba(2026, 10, 3, 18, 37)) is True


def test_firma_del_espejo_cubre_el_tamano_del_parquet(tmp_path) -> None:
    pq, xlsx = str(tmp_path / "h.parquet"), str(tmp_path / "h.xlsx")
    _filas(D).to_parquet(pq, index=False)
    _filas(D).to_excel(xlsx, index=False)
    assert espejo.marcar_espejo(pq, xlsx) and espejo.espejo_valido(pq, xlsx)
    pd.concat([_filas(D), _filas(D_SIG)]).to_parquet(pq, index=False)        # OneDrive trajo OTRO parquet
    assert not espejo.espejo_valido(pq, xlsx)


@pytest.mark.asyncio
async def test_http_banner_regresion_reponer_y_aceptar(env, monkeypatch) -> None:
    from backend.main import app

    xlsx = _xlsx(env)
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 9, 25, 10, 0))
    hw.append_and_save(_filas(D_ANT), xlsx)
    hw.append_and_save(_filas(D), xlsx)
    hw.append_and_save(_filas(D_SIG), xlsx)
    _version_ajena(env, [_filas(D_ANT), _filas(D_SIG)])              # perdió el 23/09
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/cierre/chip")
        assert 'data-state="regresion"' in r.text and "perdió 1 rueda" in r.text
        assert "Aceptar la base como está" in r.text and "Reponer del journal" not in r.text
        assert hw._host() in r.text                                     # última escritura
        hw.write_journal(_filas(D), D)
        r = await ac.get("/cierre/chip")
        assert "Reponer del journal (1)" in r.text
        r = await ac.post("/historicos/reponer-journal")
        assert r.status_code == 200 and "Repuestas 1" in r.text and r.headers.get("hx-trigger") == "cierre-refresh"
        r = await ac.get("/cierre/chip")
        assert 'data-state="ok"' in r.text and 'data-state="regresion"' not in r.text
        # otra regresión → el superuser acepta la base tal como está
        _version_ajena(env, [_filas(D_ANT), _filas(D_SIG)])
        r = await ac.get("/cierre/chip")
        assert 'data-state="regresion"' in r.text
        r = await ac.post("/historicos/aceptar-base")
        assert r.status_code == 200 and "aceptada" in r.text and r.headers.get("hx-trigger") == "cierre-refresh"
        r = await ac.get("/cierre/chip")
        assert 'data-state="ok"' in r.text


@pytest.mark.asyncio
async def test_aceptar_y_reponer_solo_superuser(auth_on, monkeypatch) -> None:  # noqa: F811
    llamadas = []
    monkeypatch.setattr(hw, "aceptar_base_actual",
                        lambda: llamadas.append("aceptar") or {"ok": True, "ruedas": 3, "ultima": "2026-09-24"})
    monkeypatch.setattr(hw, "consolidar_journal",
                        lambda reponer=False: llamadas.append(("reponer", reponer)) or {"consolidados": 1, "total_rows": 9})
    async with _client() as ac:
        for ruta in ("/historicos/aceptar-base", "/historicos/reponer-journal"):
            r = await ac.post(ruta)
            assert r.status_code in (302, 401)                        # sin sesión → al login
    async with _client() as su:
        r = await su.post("/login", data={"username": "su_test", "password": "clave-de-test-2026!",
                                          "next": "/yas"})
        assert r.status_code in (200, 303)
        r = await su.post("/admin/users", data={"username": "juan", "password": "clave123",
                                                "role": "basico", "email": ""})
        assert r.status_code < 400, r.text[:200]
        r = await su.post("/historicos/aceptar-base")
        assert r.status_code == 200 and "3 ruedas, última 24/09/2026" in r.text
        r = await su.post("/historicos/reponer-journal")
        assert r.status_code == 200 and "Repuestas 1" in r.text
        assert llamadas == ["aceptar", ("reponer", True)]
    async with _client() as ac:
        r = await ac.post("/login", data={"username": "juan", "password": "clave123", "next": "/yas"})
        assert r.status_code in (200, 303)
        for ruta in ("/historicos/aceptar-base", "/historicos/reponer-journal"):
            assert (await ac.post(ruta)).status_code == 403
        assert llamadas == ["aceptar", ("reponer", True)]


def test_base_check_informa_la_regresion_sin_escribir(env, monkeypatch, capsys) -> None:
    """`python -m backend.tools.base_check`: sólo lectura — cuenta la regresión
    (qué repone el journal propio, qué frena la escritura), el estado de cada
    rueda y sale con 1; aceptada la base, sale con 0."""
    from backend.tools import base_check

    xlsx = _xlsx(env)
    monkeypatch.setattr(hw, "_now", lambda: _ba(2026, 9, 25, 10, 0))
    for d in (D_ANT, D, D_SIG):
        hw.append_and_save(_filas(d), xlsx)
    hw.write_journal(_filas(D), D)                  # el 23/09 lo tiene esta máquina; el 24/09 no
    _version_ajena(env, [_filas(D_ANT)])            # OneDrive: la base perdió el 23/09 y el 24/09
    antes = (hw._firmas_base(xlsx), hw._firma_archivo(hw._manifest_path(xlsx)))
    inf = base_check.informe(ruedas=5)
    assert inf["regresion"]["recuperables"] == [D.isoformat()]
    assert inf["regresion"]["bloqueantes"] == [D_SIG.isoformat()]
    estados = {f["fecha"]: f["estado"] for f in inf["ruedas"]}
    assert estados[D_SIG.isoformat()] == "FALTA" and estados[D.isoformat()] == "sólo journal"
    assert estados[D_ANT.isoformat()] == "ok" and list(estados.values()).count("anterior a la base") == 2
    assert inf["espejo_fiel"] and inf["manifiesto"]["ruedas"] == 3 and inf["ruedas_en_base"] == 1
    assert (hw._firmas_base(xlsx), hw._firma_archivo(hw._manifest_path(xlsx))) == antes   # no escribió nada
    assert base_check.main(["--ruedas", "5"]) == 1
    out = capsys.readouterr().out
    assert "REGRESIÓN" in out and f"frenan la escritura: {D_SIG.isoformat()}" in out
    assert "sólo journal" in out and "anterior a la base" in out
    assert base_check.main(["--json"]) == 1 and '"bloqueantes"' in capsys.readouterr().out
    hw.aceptar_base_actual()
    assert base_check.main([]) == 0
    assert "regresión  ninguna" in capsys.readouterr().out
