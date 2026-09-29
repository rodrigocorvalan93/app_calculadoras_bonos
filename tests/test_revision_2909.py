"""Revisión de eficiencia y bugs (29/09) — regresiones de lo que se arregló:

- /graficos NO arma el SVG server-side (pricing + NSS con scipy en el event
  loop, para tirarlo: la página dibuja con charts.js) y /graficos/svg lo hace
  en el pool de filas.
- append_acciones no pisa la historia cuando el parquet es ilegible y no se
  pudo apartar (antes seguía con prev=None y escribía sólo las filas de hoy).
- instruments.detail: cache acotado (el símbolo lo arma el usuario) y por
  contexto de broker (host + versión de sesión).
- cierres.importar_base no importa si no pudo LISTAR las particiones (con []
  daba por faltante cada fecha y pisaba las reales con filas sólo-base).
- escenario_prefs / alertas: un archivo que existe pero no se puede leer
  aborta el guardado (no se reescribe con sólo la entrada del que guardó).
- auth: el PBKDF2 de alta / cambio / reset de clave corre FUERA del lock que
  toma cada request.
- build_curve_codes / curve_key_for usan la fecha de Buenos Aires.
"""
from __future__ import annotations

import os
import threading
from datetime import date, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_graficos_no_arma_svg_en_la_pagina_y_svg_va_al_pool(monkeypatch) -> None:
    from backend.main import app
    from backend.routes import curves as rc

    hilos: list = []
    real = rc._chart_data

    def espia(rows, *a, **k):
        hilos.append(threading.current_thread().name)
        return real(rows, *a, **k)

    monkeypatch.setattr(rc, "_chart_data", espia)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/graficos")
        assert r.status_code == 200 and hilos == []          # la página no lo computa
        r = await ac.get("/graficos/svg", params={"curve": "cer"})
        assert r.status_code == 200 and len(hilos) == 1
        assert hilos[0].startswith("curve-rows")             # _row_pool, no el hilo del loop


def test_append_acciones_no_pisa_la_historia_si_no_puede_apartar(tmp_path, monkeypatch) -> None:
    import pandas as pd
    from backend.services import historico_writer as hw

    pq = tmp_path / hw.ACCIONES_FILENAME
    pq.write_bytes(b"esto no es un parquet")
    monkeypatch.setattr(hw.time, "sleep", lambda s: None)      # sin esperar el reintento
    real_replace = os.replace

    def replace_falla(src, dst, *a, **k):
        if str(src) == str(pq):
            raise PermissionError(13, "lock")
        return real_replace(src, dst, *a, **k)

    monkeypatch.setattr(os, "replace", replace_falla)
    fila = {"fecha_hoy": date(2026, 9, 29), "ticker": "GGAL", "panel": "L", "ultimo": 5100.0,
            "apertura": 5000.0, "maximo": 5150.0, "minimo": 4990.0, "cierre_ant": None,
            "vwap": 5050.0, "volumen": 1e9, "nominal": 1e5}
    with pytest.raises(RuntimeError, match="no guardo"):
        hw.append_acciones(pd.DataFrame([fila]), str(pq))
    assert pq.read_bytes() == b"esto no es un parquet"        # intacto
    # si SÍ se puede apartar: .corrupto-* y la serie arranca de nuevo (como siempre)
    monkeypatch.setattr(os, "replace", real_replace)
    r = hw.append_acciones(pd.DataFrame([fila]), str(pq))
    assert r["filas"] == 1 and list(tmp_path.glob(hw.ACCIONES_FILENAME + ".corrupto-*"))
    assert pd.read_parquet(pq)["ticker"].tolist() == ["GGAL"]


@pytest.mark.asyncio
async def test_instruments_cache_acotado_y_por_contexto_de_broker(monkeypatch) -> None:
    from backend.services import instruments, primary_ws

    class FakeClient:
        base_url = "https://broker.invalid/"

        async def get_json(self, path, params=None):
            return {"instrument": {"minTradeVol": 1, "tickSize": 0.01}}

    monkeypatch.setattr(primary_ws, "get_ws_client", lambda *a, **k: FakeClient())
    monkeypatch.setattr(instruments, "_MAX_CACHE", 8)
    with instruments._lock:
        instruments._cache.clear()
    instruments._cache_ctx = None
    for i in range(20):
        assert (await instruments.detail(f"MERV - XMEV - X{i} - CI"))["lamina"] == 1.0
    assert 0 < len(instruments._cache) <= 8
    # swap de broker / re-login (sube context_version) → el cache se vacía
    monkeypatch.setattr(primary_ws, "_context_version", primary_ws.context_version() + 1)
    await instruments.detail("MERV - XMEV - NUEVO - CI")
    assert set(instruments._cache) == {"MERV - XMEV - NUEVO - CI"}
    with instruments._lock:
        instruments._cache.clear()
    instruments._cache_ctx = None


def test_importar_base_no_pisa_particiones_si_no_puede_listar(tmp_path, monkeypatch) -> None:
    import pandas as pd
    from backend.services import cierres, historico_writer as hw

    monkeypatch.setenv("DELTA_HISTORICO_DIR", str(tmp_path))
    monkeypatch.delenv("DELTA_HISTORICO_PATH", raising=False)
    monkeypatch.delenv("DELTA_BASES_DIR", raising=False)
    d1, d2 = date(2026, 9, 24), date(2026, 9, 25)
    sym = "MERV - XMEV - TX26 - 24hs"
    part = pd.DataFrame([{"fecha_hoy": d1, "symbol": sym, "code": "TX26", "plazo": "24hs",
                          "last": 1000.0, "close": 990.0, "opero": True, "volume": 5e9, "tirea": 0.3}])
    for col in ("symbol", "code", "plazo"):
        part[col] = part[col].astype("string")
    hw.escribir_particion(part, str(tmp_path), d1)               # partición REAL (con volumen)
    p24 = tmp_path / "cierres" / "2026" / "2026-09-24.parquet"
    p25 = tmp_path / "cierres" / "2026" / "2026-09-25.parquet"
    antes = p24.read_bytes()
    base = pd.DataFrame([{"symbol": sym, "fecha_hoy": d, "Código": "TX26", "Price Source": "LA",
                          "Last Price": 1000.0, "Price Date": d.isoformat(), "Close Price": 990.0,
                          "TIREA": 0.3, "TNA": 0.28, "TEM": 0.02, "Paridad": 0.9, "Duration": 1.2}
                         for d in (d1, d2)])
    base.to_parquet(os.path.splitext(str(tmp_path / hw.HIST_FILENAME))[0] + ".parquet", index=False)
    real_listdir = os.listdir
    root = os.path.abspath(cierres.dir_path())

    def listdir_falla(p="."):
        if os.path.abspath(str(p)) == root:
            raise OSError(5, "EIO (OneDrive a medias)")
        return real_listdir(p)

    monkeypatch.setattr(os, "listdir", listdir_falla)
    r = cierres.importar_base(force=True)
    assert "error" in r and "listar" in r["error"]
    assert p24.read_bytes() == antes and not p25.exists()      # nada pisado, nada escrito
    try:
        monkeypatch.setattr(os, "listdir", real_listdir)
        r = cierres.importar_base(force=True)
        assert r == {"importadas": 1, "existentes": 1}
        assert p24.read_bytes() == antes and p25.exists()       # sólo la que faltaba
    finally:
        cierres.refresh()


def _read_text_falla(monkeypatch, objetivo: Path):
    """Path.read_text falla SÓLO para `objetivo`. Devuelve el original para
    restaurarlo con setattr (monkeypatch.undo() tiraría también el setenv)."""
    real = Path.read_text

    def falla(self, *a, **k):
        if self == objetivo:
            raise OSError(5, "EIO")
        return real(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", falla)
    return real


def test_prefs_de_escenario_ilegibles_no_se_pisan(tmp_path, monkeypatch) -> None:
    from backend.services import escenario_prefs as ep

    p = tmp_path / "escenario_prefs.json"
    monkeypatch.setenv("ESCENARIO_PREFS_PATH", str(p))
    ep.save({"a3500_path": "1,5"}, None, user="ana")
    ep.save({"a3500_path": "2,5"}, None, user="beto")
    assert ep.preset_save("base", user="ana")
    original = p.read_text(encoding="utf-8")
    real = _read_text_falla(monkeypatch, p)
    with pytest.raises(OSError):
        ep.save({"a3500_path": "9"}, None, user="ana")
    with pytest.raises(OSError):
        ep.preset_save("otro", user="ana")
    with pytest.raises(OSError):
        ep.reset(user="beto")
    assert ep.load_user("beto")["senderos"] == {}              # lectura: defaults, sin tirar
    monkeypatch.setattr(Path, "read_text", real)
    assert p.read_text(encoding="utf-8") == original           # nada pisado
    assert ep.load_user("beto")["senderos"] == {"a3500_path": "2,5"} and ep.preset_names() == ["base"]


def test_alertas_ilegibles_no_se_pisan(tmp_path, monkeypatch) -> None:
    from backend.services import alertas, bond_universe

    bond_universe.ensure_loaded()
    p = tmp_path / "alertas.json"
    monkeypatch.setenv("ALERTAS_PATH", str(p))
    assert alertas.add("TX26", "precio", ">=", 100.0) is None
    original = p.read_text(encoding="utf-8")
    real = _read_text_falla(monkeypatch, p)
    with pytest.raises(OSError):
        alertas.add("TX26", "precio", "<=", 50.0)
    assert alertas.list_alertas() == []                        # lectura: vacío, sin tirar
    monkeypatch.setattr(Path, "read_text", real)
    assert p.read_text(encoding="utf-8") == original
    assert [a["valor"] for a in alertas.list_alertas()] == [100.0]


def test_hash_de_clave_corre_fuera_del_lock() -> None:
    from backend.services import auth

    libre: list = []
    real = auth._make_record

    def espia(password, role, email=""):
        def sonda():
            ok = auth._lock.acquire(timeout=0.5)               # otro hilo: ¿el lock está libre?
            if ok:
                auth._lock.release()
            libre.append(ok)

        t = threading.Thread(target=sonda)
        t.start()
        t.join()
        return real(password, role, email)

    auth._make_record, orig = espia, auth._make_record
    user = "rev2909_u"
    try:
        auth.create_user(user, "clave-123456", "basico", "rev2909@example.com")
        auth.set_password(user, "otra-clave-789")
        assert auth.verify_password(user, "otra-clave-789")
        tok = auth.make_reset_token(user)
        assert auth.reset_with_token(tok, "clave-final-000") == user
        assert auth.verify_password(user, "clave-final-000")
        # el token es de un solo uso (la huella cambió)
        with pytest.raises(auth.AuthError):
            auth.reset_with_token(tok, "clave-final-111")
        assert len(libre) == 3 and all(libre)                  # 3 hashes, ninguno con el lock tomado
    finally:
        auth._make_record = orig
        try:
            auth.delete_user(user)
        except Exception:  # noqa: BLE001
            pass


def test_curvas_usan_fecha_de_buenos_aires(monkeypatch) -> None:
    from backend.services import bond_universe, curves

    bond_universe.ensure_loaded()
    tabla = curves.build_curve_codes()
    code = next(c for c in tabla.get("lecap", []) if getattr(bond_universe.get(c), "vencimiento", None) is not None)
    v = bond_universe.get(code).vencimiento
    vd = v.date() if hasattr(v, "hour") else v
    try:
        monkeypatch.setattr(curves, "hoy_ba", lambda: vd + timedelta(days=1))
        curves._codes_cache = None
        assert code not in curves.build_curve_codes().get("lecap", [])     # "vencido" en fecha BA
        assert curves.curve_key_for(code) is None
    finally:
        monkeypatch.undo()
        curves._codes_cache = None
        curves._rev_cache = None
    assert code in curves.build_curve_codes().get("lecap", []) and curves.curve_key_for(code) == "lecap"
