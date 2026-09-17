"""Regresiones de la segunda auditoría externa (tanda 4):

R05 · filas de Mercado/Curvas que siguen a los índices aunque el feed esté quieto
R01 · reconciliación de una respuesta perdida SIN certezas inventadas
R02 · contexto de broker re-chequeado en el envío y presente en cada hija
R03 · cancelación rechazada por el broker ≠ CANCELADA
R04 · uid por cuenta en la cookie + versión de sesión capturada ANTES de verificar
R06 · el espejo parquet vale sólo si es copia fiel del Excel (firma / mtime estricto)
R07 · historial FX ilegible → no se pisa
R08 · caución mergeada por GRUPO (plazo + TNA + VWAP + monto), no por columna
R09 · poller del add-in: timeout hasta el cuerpo (harness en test_excel_poller)
R10 · single-flight de recálculos YAS idénticos en vuelo
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import threading
import time
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import httpx
import pandas as pd
import pytest
from httpx import ASGITransport, AsyncClient

from backend.config import settings
from backend.services import auth, espejo, historico_writer as hw, oms, primary_ws


def _client() -> AsyncClient:
    from backend.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


@pytest.fixture()
def auth_on(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "app_users_path", str(tmp_path / "store.json"))
    auth.refresh()
    auth.ensure_bootstrapped()
    yield
    auth.refresh()


@pytest.fixture()
def oms_tmp(tmp_path, monkeypatch):
    from backend.services import instruments

    async def _resolve(code, symbol):
        return {"checked": False, "exists": True, "candidates": []}

    monkeypatch.setattr(oms, "_AUDIT_PATH", tmp_path / "audit.jsonl")
    monkeypatch.setattr(oms, "_tail_cache", None)
    monkeypatch.setattr(oms, "_accounts_cache", None)
    monkeypatch.setattr(oms, "_RECONCILE_DELAYS", (0.01, 0.02))
    monkeypatch.setattr(instruments, "resolve", _resolve)
    oms.kill_switch(False)
    yield
    oms.kill_switch(False)
    oms.set_live(None)


def _payload(**kw):
    p = {"code": "AL30", "symbol": "MERV - XMEV - AL30 - 24hs", "side": "buy", "qty": 100.0,
         "price": 941.0, "account": "C1", "ordtype": "limit"}
    p.update(kw)
    return p


def _orden_broker(**kw):
    o = {"instrumentId": {"symbol": "MERV - XMEV - AL30 - 24hs"}, "side": "BUY",
         "orderQty": 100, "price": 941.0, "status": "NEW", "clientId": "77"}
    o.update(kw)
    return o


def _hora_primary(dt: datetime) -> str:
    return dt.strftime("%Y%m%d-%H:%M:%S.%f")[:-3] + dt.strftime("%z")


async def _esperar_followups():
    await asyncio.gather(*list(oms._followups))


# ── R05 · las filas cacheadas siguen a los índices ───────────────────────────
def test_r05_indices_token_cambia_con_la_proyeccion_cer(monkeypatch) -> None:
    import rentafija
    from backend.services import pricing

    monkeypatch.setattr(pricing, "_last_series_value", lambda key, col: ("2026-09-16", 1234.5))
    monkeypatch.setattr(pricing, "_bench_pct", lambda idx: 30.0)
    monkeypatch.setattr(pricing, "a3500_aplicable", lambda: {"value": 1350.0})
    monkeypatch.setitem(rentafija.inputs, "cer_proyectado", pd.DataFrame({"CER": [1234.5, 1240.0]}))
    pricing._index_val_cache.clear()
    try:
        t1 = pricing.indices_token()
        assert pricing.indices_token() == t1                     # estable sin cambios
        # refresh de índices: misma última observación, proyección distinta
        monkeypatch.setitem(rentafija.inputs, "cer_proyectado", pd.DataFrame({"CER": [1234.5, 1250.0]}))
        pricing._index_val_cache.clear()
        assert pricing.indices_token() != t1
    finally:
        pricing._index_val_cache.clear()


@pytest.mark.asyncio
async def test_r05_filas_de_mercado_se_rearman_al_cambiar_los_indices(monkeypatch) -> None:
    from backend.routes import curves as cr
    from backend.services import pricing

    builds = []

    async def _rows_for(curve, plazo, only_quoting, leg, book=True, fuente="byma"):
        builds.append(1)
        return [{"code": "T30E6", "n": len(builds)}], {"n": 1}

    huella = [("a",)]
    monkeypatch.setattr(cr, "_rows_for", _rows_for)
    monkeypatch.setattr(pricing, "indices_token", lambda: huella[0])
    cr._ROWS_CACHE.clear()
    cr._ROWS_IDX.clear()
    try:
        e1 = await cr._rows_en_seq("cer", "24hs", False, "ars", "byma", "", 0)
        e2 = await cr._rows_en_seq("cer", "24hs", False, "ars", "byma", "", 0)
        assert len(builds) == 1 and e2 is e1                     # misma seq + mismos índices: cache
        huella[0] = ("b",)                                       # refresh de índices, feed quieto
        e3 = await cr._rows_en_seq("cer", "24hs", False, "ars", "byma", "", 0)
        assert len(builds) == 2 and e3 is not e1 and e3[1][0]["n"] == 2
        assert (await cr._rows_en_seq("cer", "24hs", False, "ars", "byma", "", 0)) is e3
    finally:
        cr._ROWS_CACHE.clear()
        cr._ROWS_IDX.clear()


# ── R02 · contexto de broker en el envío y en cada hija ──────────────────────
@pytest.mark.asyncio
async def test_r02_swap_de_broker_durante_el_resolve_no_envia(oms_tmp, monkeypatch) -> None:
    from backend.services import instruments

    enviados = []

    class _WS:
        async def get_json_checked(self, path, params=None):
            enviados.append(path)
            return {"status": "OK", "order": {"clientId": "1"}}

    orig = primary_ws._singleton
    tok = oms.new_token(_payload())

    async def _resolve_con_swap(code, symbol):
        primary_ws.set_ws_client(orig)          # reconexión mientras se prepara el envío
        await asyncio.sleep(0)
        return {"checked": False, "exists": True, "candidates": []}

    monkeypatch.setattr(instruments, "resolve", _resolve_con_swap)
    monkeypatch.setattr(primary_ws, "get_ws_client", lambda: _WS())
    oms.set_live(True)
    try:
        res = await oms.place(oms.pop_token(tok))
        assert res["status"] == "RECHAZADA" and "cambió" in res["motivo"] and not enviados
        assert oms.blotter(3)[0]["status"] == "RECHAZADA"
        assert any(a["event"] == "rechazada_contexto" and a.get("etapa") == "pre_envio"
                   for a in oms.audit_tail(10))
    finally:
        primary_ws.set_ws_client(orig)


@pytest.mark.asyncio
async def test_r02_multiorden_lleva_el_contexto_en_cada_hija(oms_tmp, monkeypatch) -> None:
    enviados = []

    class _WS:
        async def get_json_checked(self, path, params=None):
            enviados.append(path)
            return {"status": "OK", "order": {"clientId": "1"}}

    monkeypatch.setattr(primary_ws, "get_ws_client", lambda: _WS())
    tok = oms.new_token({"batch": [_payload(), _payload(account="C2")]})
    v = primary_ws.context_version()
    assert all(h["ctx_version"] == v for h in oms.peek_token(tok)["batch"])
    orig = primary_ws._singleton
    primary_ws.set_ws_client(orig)              # reconexión entre armar y confirmar
    oms.set_live(True)
    try:
        res = [await oms.place(h) for h in oms.pop_token(tok)["batch"]]
        assert [r["status"] for r in res] == ["RECHAZADA", "RECHAZADA"] and not enviados
    finally:
        primary_ws.set_ws_client(orig)


@pytest.mark.asyncio
async def test_r02_multiorden_por_http_rechazada_tras_reconexion(auth_on, oms_tmp, monkeypatch) -> None:
    enviados = []

    class _WS:
        async def get_json_checked(self, path, params=None):
            enviados.append(path)
            return {"status": "OK", "order": {"clientId": "1"}}

    monkeypatch.setattr(primary_ws, "get_ws_client", lambda: _WS())
    tok = oms.new_token({"batch": [_payload(), _payload(account="C2")]})
    orig = primary_ws._singleton
    primary_ws.set_ws_client(orig)
    oms.set_live(True)
    try:
        async with _client() as ac:
            await ac.post("/login", data={"username": "su_test", "password": "clave-de-test-2026!", "next": "/yas"})
            r = await ac.post("/ordenes/multi/confirmar", data={"token": tok, "confirm_live": "200"})
            assert r.status_code == 200 and "RECHAZADA" in r.text and not enviados
    finally:
        primary_ws.set_ws_client(orig)


# ── R01 · reconciliación con evidencia ───────────────────────────────────────
@pytest.mark.asyncio
async def test_r01_sin_lista_completa_sigue_desconocida(oms_tmp, monkeypatch) -> None:
    class _WS:
        modo = "caida"

        async def get_json_checked(self, path, params=None):
            if path.endswith("newSingleOrder"):
                raise httpx.ReadTimeout("respuesta perdida (sintético)")
            if self.modo == "caida":
                raise httpx.ReadTimeout("broker caído (sintético)")
            if self.modo == "solo_actives" and path.endswith("order/all"):
                raise httpx.ReadTimeout("order/all caído (sintético)")
            return {"orders": []}

    monkeypatch.setattr(primary_ws, "get_ws_client", lambda: _WS())
    oms.set_live(True)
    # a) ninguna consulta responde → no hay evidencia: DESCONOCIDA
    res = await oms.place(_payload())
    assert res["status"] == "DESCONOCIDA"
    await _esperar_followups()
    assert oms.blotter(3)[0]["status"] == "DESCONOCIDA"
    assert any(a["event"] == "live_desconocida_no_verificable" for a in oms.audit_tail(10))
    # b) sólo `actives` responde (vacío): una orden ejecutada al instante no es
    #    una activa → tampoco es prueba: DESCONOCIDA
    _WS.modo = "solo_actives"
    await oms.place(_payload(price=942.0))
    await _esperar_followups()
    assert oms.blotter(3)[0]["status"] == "DESCONOCIDA"
    # c) la lista COMPLETA del día responde y no está → NO ENTRÓ (verificado)
    _WS.modo = "completa"
    await oms.place(_payload(price=943.0))
    await _esperar_followups()
    assert oms.blotter(3)[0]["status"] == "NO ENTRÓ"
    assert any(a["event"] == "live_desconocida_sin_rastro" for a in oms.audit_tail(10))


@pytest.mark.asyncio
async def test_r01_orden_igual_anterior_no_se_atribuye(oms_tmp, monkeypatch) -> None:
    from backend.services.oms import _TZ_BA

    class _WS:
        ordenes = []

        async def get_json_checked(self, path, params=None):
            if path.endswith("newSingleOrder"):
                raise httpx.ReadTimeout("respuesta perdida (sintético)")
            return {"orders": list(self.ordenes)}

    monkeypatch.setattr(primary_ws, "get_ws_client", lambda: _WS())
    oms.set_live(True)
    # a) misma orden económica SIN hora de alta → ambigua: DESCONOCIDA (con el id para mirarla)
    _WS.ordenes = [_orden_broker(clientId="VIEJA-SIN-HORA")]
    await oms.place(_payload())
    await _esperar_followups()
    b = oms.blotter(3)[0]
    assert b["status"] == "DESCONOCIDA" and "sin hora" in (b["motivo"] or "")
    assert any(a["event"] == "live_desconocida_posible" and a.get("broker_order_id") == "VIEJA-SIN-HORA"
               for a in oms.audit_tail(10))
    # b) misma orden con alta ANTERIOR al envío → no es este intento; la lista
    #    completa está → NO ENTRÓ
    _WS.ordenes = [_orden_broker(clientId="VIEJA", transactTime=_hora_primary(datetime.now(_TZ_BA) - timedelta(minutes=10)))]
    await oms.place(_payload())
    await _esperar_followups()
    assert oms.blotter(3)[0]["status"] == "NO ENTRÓ"
    # c) alta POSTERIOR al envío → sí es este intento: estado real
    _WS.ordenes = [_orden_broker(clientId="NUEVA", status="FILLED",
                                 transactTime=_hora_primary(datetime.now(_TZ_BA) + timedelta(seconds=1)))]
    await oms.place(_payload())
    await _esperar_followups()
    assert oms.blotter(3)[0]["status"] == "EJECUTADA"
    assert any(a["event"] == "live_estado" and a.get("broker_order_id") == "NUEVA" for a in oms.audit_tail(10))


def test_r01_parseo_de_transact_time() -> None:
    from backend.services.oms import _es_nuestra, _ts_orden

    t = _ts_orden({"transactTime": "20260916-14:03:22.123-0300"})
    assert t == pytest.approx(datetime.fromisoformat("2026-09-16T14:03:22.123-03:00").timestamp())
    assert _ts_orden({"transactTime": "2026-09-16T17:03:22Z"}) == pytest.approx(
        datetime.fromisoformat("2026-09-16T17:03:22+00:00").timestamp())
    assert _ts_orden({"timestamp": 1_800_000_000_000}) == pytest.approx(1_800_000_000.0)
    assert _ts_orden({}) is None and _ts_orden({"transactTime": "ayer"}) is None
    rec = {**_payload(), "enviada_ts": t}
    o = _orden_broker(transactTime="20260916-14:03:22.123-0300")
    assert _es_nuestra(o, rec) is True                             # misma hora (dentro del margen)
    assert _es_nuestra(_orden_broker(transactTime="20260916-14:03:10.000-0300"), rec) is False
    assert _es_nuestra(_orden_broker(), rec) is None                 # sin hora: ambiguo
    assert _es_nuestra(_orden_broker(price=900.0), rec) is False     # otros términos: no es


@pytest.mark.asyncio
async def test_r01_http_5xx_y_cuerpo_invalido_son_desconocida(oms_tmp, monkeypatch) -> None:
    respuesta = {"r": None}

    async def _get(path, params=None):
        return respuesta["r"](path)

    cliente = primary_ws.PrimaryWS("https://broker.example.invalid/")
    cliente._http = SimpleNamespace(get=_get)
    monkeypatch.setattr(primary_ws, "get_ws_client", lambda: cliente)
    oms.set_live(True)

    def _resp(code, text):
        return lambda path: httpx.Response(code, text=text, request=httpx.Request("GET", "https://broker.example.invalid/" + path))

    # HTTP 500 después de mandar: el broker PUDO haberla procesado
    respuesta["r"] = _resp(500, "fallo al serializar (sintético)")
    res = await oms.place(_payload())
    assert res["status"] == "DESCONOCIDA"
    await _esperar_followups()
    assert oms.blotter(3)[0]["status"] == "DESCONOCIDA"       # la reconciliación también da 500: no verificable
    # HTTP 200 con cuerpo vacío / no-JSON: ídem
    respuesta["r"] = _resp(200, "")
    assert (await oms.place(_payload()))["status"] == "DESCONOCIDA"
    respuesta["r"] = _resp(200, "<html>proxy</html>")
    assert (await oms.place(_payload()))["status"] == "DESCONOCIDA"
    await _esperar_followups()
    # HTTP 4xx = rechazo antes de procesar → ERROR limpio
    respuesta["r"] = _resp(401, "sin sesión")
    res = await oms.place(_payload())
    assert res["status"] == "ERROR" and "401" in res["motivo"]
    assert oms.blotter(3)[0]["status"] == "ERROR"


# ── R03 · cancelación ────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_r03_cancel_rechazada_o_con_error_no_es_cancelada(oms_tmp, monkeypatch) -> None:
    class _WS:
        resp = {"status": "ERROR", "message": "orden ya ejecutada (sintético)"}

        async def get_json_checked(self, path, params=None):
            if isinstance(self.resp, Exception):
                raise self.resp
            return self.resp

    monkeypatch.setattr(primary_ws, "get_ws_client", lambda: _WS())
    oms.set_live(True)
    r = await oms.cancel("calc-abc")
    assert r["status"] == "ERROR" and "rechazó" in r["motivo"] and "ya ejecutada" in r["motivo"]
    assert oms.blotter(3)[0]["status"] == "CANCEL RECHAZADA"
    _WS.resp = {"status": "OK"}
    r = await oms.cancel("calc-abc")
    assert r["status"] == "OK" and oms.blotter(3)[0]["status"] == "CANCEL ACEPTADA"
    _WS.resp = httpx.ReadTimeout("timeout (sintético)")
    r = await oms.cancel("calc-abc")
    assert r["status"] == "ERROR" and oms.blotter(3)[0]["status"] == "CANCEL ERROR"
    assert not any(b["status"] == "CANCELADA" for b in oms.blotter(5))
    # el blotter pinta en rojo los rechazos/errores de cancel (la orden sigue viva)
    async with _client() as ac:
        html = (await ac.get("/ordenes/blotter")).text
    assert 'color:var(--red)">CANCEL RECHAZADA' in html and 'color:var(--red)">CANCEL ERROR' in html
    assert 'color:var(--text-muted)">CANCEL ACEPTADA' in html


# ── R04 · uid por cuenta + versión capturada antes de verificar ──────────────
async def _login(ac: AsyncClient, user: str, pwd: str):
    return await ac.post("/login", data={"username": user, "password": pwd, "next": "/yas"})


@pytest.mark.asyncio
async def test_r04_usuario_recreado_no_revive_la_cookie(auth_on) -> None:
    auth.create_user("ana", "clave-vieja-123", "basico")
    async with _client() as ac:
        await _login(ac, "ana", "clave-vieja-123")
        assert (await ac.get("/market/seq")).status_code == 200
        auth.delete_user("ana")
        auth.create_user("ana", "otra-clave-123", "premium")       # otra cuenta, mismo nombre
        assert (await ac.get("/market/seq")).status_code in (302, 303, 401)
        # la cuenta nueva entra con su clave y su uid
        await _login(ac, "ana", "otra-clave-123")
        assert (await ac.get("/market/seq")).status_code == 200
        # un cambio de clave conserva el uid (la cuenta es la misma)
        uid = auth.session_uid("ana")
        auth.set_password("ana", "clave-3-123")
        assert auth.session_uid("ana") == uid and uid


@pytest.mark.asyncio
async def test_r04_cookie_sin_uid_no_autentica(auth_on) -> None:
    from itsdangerous import TimestampSigner

    auth.create_user("ana", "clave-vieja-123", "basico")
    sv = auth.session_version("ana")
    signer = TimestampSigner(str(auth.get_secret_key()))
    vieja = signer.sign(base64.b64encode(json.dumps({"user": "ana", "sv": sv}).encode("utf-8"))).decode("utf-8")
    async with _client() as ac:
        ac.cookies.set("bonos_session", vieja)
        assert (await ac.get("/market/seq")).status_code in (302, 303, 401)
        ac.cookies.clear()
        completa = signer.sign(base64.b64encode(json.dumps(
            {"user": "ana", "sv": sv, "uid": auth.session_uid("ana")}).encode("utf-8"))).decode("utf-8")
        ac.cookies.set("bonos_session", completa)
        assert (await ac.get("/market/seq")).status_code == 200


@pytest.mark.asyncio
async def test_r04_login_verificado_contra_la_clave_vieja_no_recibe_la_version_nueva(auth_on, monkeypatch) -> None:
    auth.create_user("beto", "clave-vieja-123", "basico")
    verificado, soltar = threading.Event(), threading.Event()
    original = auth.verify_password

    def lenta(user, pwd):
        ok = original(user, pwd)
        verificado.set()
        assert soltar.wait(10)
        return ok

    monkeypatch.setattr(auth, "verify_password", lenta)
    async with _client() as ac:
        tarea = asyncio.create_task(_login(ac, "beto", "clave-vieja-123"))
        assert await asyncio.to_thread(verificado.wait, 5)
        try:
            auth.set_password("beto", "clave-nueva-123")          # reset mientras se verificaba la vieja
        finally:
            soltar.set()
        r = await tarea
        assert r.status_code == 401
        assert (await ac.get("/market/seq")).status_code in (302, 303, 401)
        soltar.set()
        r = await _login(ac, "beto", "clave-nueva-123")
        assert r.status_code == 303 and (await ac.get("/market/seq")).status_code == 200


def test_r04_bootstrap_completa_el_uid_de_registros_viejos(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_users_path", str(tmp_path / "store.json"))
    auth.refresh()
    try:
        auth.ensure_bootstrapped()
        auth.create_user("viejo", "clave-vieja-123", "basico")
        data = json.loads((tmp_path / "store.json").read_text(encoding="utf-8"))
        del data["users"]["viejo"]["uid"]                          # registro anterior al campo
        (tmp_path / "store.json").write_text(json.dumps(data), encoding="utf-8")
        auth.refresh()
        assert auth.session_uid("viejo") == ""
        auth.ensure_bootstrapped()
        uid = auth.session_uid("viejo")
        assert len(uid) == 16
        auth.refresh()
        assert auth.session_uid("viejo") == uid                    # persistido
    finally:
        auth.refresh()


# ── R06 · espejo con firma del Excel ─────────────────────────────────────────
def _frame(d: date, last: float) -> pd.DataFrame:
    from tests.test_historico_writer import _rows_df
    df = _rows_df(d)
    df["Last Price"] = last
    return df


def test_r06_correccion_del_excel_dentro_de_los_2_s_gana(tmp_path) -> None:
    pq, xlsx = str(tmp_path / "h.parquet"), str(tmp_path / "h.xlsx")
    _frame(date(2026, 9, 15), 100.0).to_parquet(pq, index=False)
    _frame(date(2026, 9, 15), 120.0).to_excel(xlsx, index=False)
    t = time.time()
    os.utime(pq, (t - 1, t - 1))
    os.utime(xlsx, (t, t))
    assert not espejo.espejo_valido(pq, xlsx)
    assert set(hw._leer_base(xlsx, pd)["Last Price"]) == {120.0}


def test_r06_firma_del_excel(tmp_path) -> None:
    pq, xlsx = str(tmp_path / "h.parquet"), str(tmp_path / "h.xlsx")
    _frame(date(2026, 9, 15), 100.0).to_parquet(pq, index=False)
    _frame(date(2026, 9, 15), 100.0).to_excel(xlsx, index=False)
    t = time.time()
    os.utime(xlsx, (t + 5, t + 5))                                 # reloj/mtime raro: Excel "más nuevo"
    assert not espejo.espejo_valido(pq, xlsx)
    assert espejo.marcar_espejo(pq, xlsx) and os.path.isfile(espejo.sidecar_path(pq))
    assert espejo.espejo_valido(pq, xlsx)                          # firmado: vale aunque el mtime diga otra cosa
    # OneDrive: el Excel editado en otra máquina llega con mtime VIEJO y otro tamaño
    _frame(date(2026, 9, 15), 130.0).to_excel(xlsx, index=False)
    os.utime(xlsx, (t - 3600, t - 3600))
    assert not espejo.espejo_valido(pq, xlsx)
    # sin Excel al lado el parquet suelto vale; sin parquet, no
    os.remove(xlsx)
    assert espejo.espejo_valido(pq, xlsx)
    assert not espejo.espejo_valido(str(tmp_path / "no.parquet"), xlsx)
    # firma sin Excel: se borra
    assert not espejo.marcar_espejo(pq, xlsx) and not os.path.isfile(espejo.sidecar_path(pq))


def test_r06_el_writer_firma_y_bymaapi_tambien(tmp_path) -> None:
    from backend.services import historico_byma as hb
    from tests.test_historico_writer import _rows_df

    xlsx = str(tmp_path / hw.HIST_FILENAME)
    pq = xlsx.replace(".xlsx", ".parquet")
    hw.append_and_save(_rows_df(date(2026, 9, 15)), xlsx, incluir_journal=False)
    sc = json.loads(open(espejo.sidecar_path(pq), encoding="utf-8").read())
    assert sc["xlsx_mtime_ns"] == os.stat(xlsx).st_mtime_ns and sc["xlsx_size"] == os.path.getsize(xlsx)
    assert hb._pick_source(xlsx)[1] == "parquet"
    # el lector regenera el espejo desde un Excel corregido y lo firma
    df = pd.read_excel(xlsx)
    df["Last Price"] = 999.0
    df.to_excel(xlsx, index=False, sheet_name="Sheet1")
    assert hb._pick_source(xlsx)[1] == "xlsx"
    hb._regen_parquet(xlsx, pd.read_excel(xlsx, sheet_name="Sheet1"))
    assert hb._pick_source(xlsx)[1] == "parquet"
    assert set(pd.read_parquet(pq)["Last Price"]) == {999.0}


def test_r06_fx_hist_lee_el_excel_corregido(tmp_path, monkeypatch) -> None:
    from backend.services import fx_hist

    monkeypatch.setenv("DELTA_HISTORICO_DIR", str(tmp_path))
    monkeypatch.delenv("DELTA_HISTORICO_PATH", raising=False)
    monkeypatch.delenv("DELTA_BASES_DIR", raising=False)
    fx_hist.refresh()
    try:
        xlsx = tmp_path / hw.FX_FILENAME
        pq = tmp_path / hw.FX_FILENAME.replace(".xlsx", ".parquet")
        pd.DataFrame([{"fecha_hoy": date(2026, 9, 15), "ccl": 100.0}]).to_parquet(pq, index=False)
        pd.DataFrame([{"fecha_hoy": date(2026, 9, 15), "ccl": 120.0}]).to_excel(xlsx, index=False)
        t = time.time()
        os.utime(pq, (t - 3600, t - 3600))
        os.utime(xlsx, (t, t))
        assert str(fx_hist._path()).endswith(".xlsx")
        assert fx_hist._load().iloc[0]["ccl"] == 120.0
        espejo.marcar_espejo(str(pq), str(xlsx))
        fx_hist.refresh()
        assert str(fx_hist._path()).endswith(".parquet")
    finally:
        fx_hist.refresh()


# ── R07 / R08 · historial FX ─────────────────────────────────────────────────
def test_r07_fx_ilegible_no_se_pisa(tmp_path, monkeypatch) -> None:
    pq = tmp_path / hw.FX_FILENAME.replace(".xlsx", ".parquet")
    xlsx = tmp_path / hw.FX_FILENAME
    pq.write_bytes(b"parquet corrupto (sintetico)")
    xlsx.write_bytes(b"xlsx corrupto (sintetico)")
    monkeypatch.setattr(hw, "build_fx_row", lambda: {"fecha_hoy": date(2026, 9, 16), "ccl_base": "GD30", "ccl": 1500.0})
    with pytest.raises(RuntimeError, match="no se pudo leer ninguna copia"):
        hw._guardar_fx(str(tmp_path))
    contenidos = [p.read_bytes() for p in tmp_path.iterdir() if p.is_file()]
    assert b"parquet corrupto (sintetico)" in contenidos and b"xlsx corrupto (sintetico)" in contenidos
    assert not (tmp_path / (hw.FX_FILENAME + ".tmp.xlsx")).exists()


def test_r07_fx_excel_corrupto_con_espejo_sano_se_aparta(tmp_path, monkeypatch) -> None:
    pq = tmp_path / hw.FX_FILENAME.replace(".xlsx", ".parquet")
    xlsx = tmp_path / hw.FX_FILENAME
    pd.DataFrame([{"fecha_hoy": date(2026, 9, 15), "ccl": 100.0, "ccl_base": "GD30"}]).to_parquet(pq, index=False)
    xlsx.write_bytes(b"xlsx corrupto (sintetico)")               # OneDrive a mitad de sync
    t = time.time()
    os.utime(pq, (t - 60, t - 60))
    os.utime(xlsx, (t, t))
    monkeypatch.setattr(hw, "build_fx_row", lambda: {"fecha_hoy": date(2026, 9, 16), "ccl_base": "GD30", "ccl": 150.0})
    assert hw._guardar_fx(str(tmp_path))["filas"] == 2
    corruptos = [p for p in tmp_path.iterdir() if ".corrupto-" in p.name]
    assert len(corruptos) == 1 and corruptos[0].read_bytes() == b"xlsx corrupto (sintetico)"
    back = pd.read_parquet(pq)
    assert list(back["ccl"]) == [100.0, 150.0] and len(pd.read_excel(xlsx)) == 2
    assert espejo.espejo_valido(str(pq), str(xlsx))


def test_r06_fx_usa_el_excel_mas_nuevo(tmp_path, monkeypatch) -> None:
    pq = tmp_path / hw.FX_FILENAME.replace(".xlsx", ".parquet")
    xlsx = tmp_path / hw.FX_FILENAME
    pd.DataFrame([{"fecha_hoy": date(2026, 9, 15), "ccl": 100.0}]).to_parquet(pq, index=False)
    pd.DataFrame([{"fecha_hoy": date(2026, 9, 15), "ccl": 120.0}]).to_excel(xlsx, index=False)
    t = time.time()
    os.utime(pq, (t - 3600, t - 3600))
    os.utime(xlsx, (t, t))
    monkeypatch.setattr(hw, "build_fx_row", lambda: {"fecha_hoy": date(2026, 9, 16), "ccl_base": "GD30", "ccl": 150.0})
    hw._guardar_fx(str(tmp_path))
    back = pd.read_parquet(pq)
    assert list(back["ccl"]) == [120.0, 150.0]                    # la corrección del Excel sobrevivió


def test_r08_caucion_se_mergea_por_grupo(tmp_path, monkeypatch) -> None:
    dia = date(2026, 9, 16)
    fila1 = {"fecha_hoy": dia, "ccl_base": "GD30", "ccl": 1500.0, "caucion_plazo_d": 1, "caucion_tna": 30.0,
             "caucion_tna_vwap": 29.0, "caucion_monto": 100.0, "caucion_usd_plazo_d": 1, "caucion_usd_tna": 5.0,
             "caucion_usd_tna_vwap": 4.9, "caucion_usd_monto": 10.0}
    monkeypatch.setattr(hw, "build_fx_row", lambda: dict(fila1))
    hw._guardar_fx(str(tmp_path))
    # recaptura: la caución $ ahora es a 3 días SIN vwap; la US$ no vino; el CCL sí
    fila2 = {"fecha_hoy": dia, "ccl_base": "GD30", "ccl": 1510.0, "caucion_plazo_d": 3, "caucion_tna": 40.0,
             "caucion_tna_vwap": None, "caucion_monto": 200.0, "caucion_usd_plazo_d": None, "caucion_usd_tna": None,
             "caucion_usd_tna_vwap": None, "caucion_usd_monto": None}
    monkeypatch.setattr(hw, "build_fx_row", lambda: dict(fila2))
    hw._guardar_fx(str(tmp_path))
    pq = tmp_path / hw.FX_FILENAME.replace(".xlsx", ".parquet")
    row = pd.read_parquet(pq).iloc[0]
    assert row["ccl"] == 1510.0
    assert row["caucion_plazo_d"] == 3 and row["caucion_tna"] == 40.0 and row["caucion_monto"] == 200.0
    assert pd.isna(row["caucion_tna_vwap"])                       # el VWAP de la de 1 día NO se pegó a la de 3
    assert row["caucion_usd_plazo_d"] == 1 and row["caucion_usd_tna"] == 5.0 and row["caucion_usd_tna_vwap"] == 4.9
    assert len(pd.read_excel(tmp_path / hw.FX_FILENAME)) == 1
    # merge unitario: caución parcial (sin plazo) no pisa la guardada
    m = hw._merge_fila_fx({"caucion_plazo_d": 1, "caucion_tna": 30.0, "caucion_tna_vwap": 29.0, "caucion_monto": 1.0},
                          {"caucion_plazo_d": None, "caucion_tna": 35.0, "ccl": 1.0})
    assert m["caucion_tna"] == 30.0 and m["caucion_tna_vwap"] == 29.0 and m["ccl"] == 1.0


# ── R10 · single-flight de YAS ───────────────────────────────────────────────
@pytest.mark.asyncio
async def test_r10_recalculos_identicos_simultaneos_comparten_el_calculo(monkeypatch) -> None:
    from backend.routes import yas as yas_routes
    from backend.services import bond_universe, pricing

    codes = bond_universe.all_codes()
    code = "AL30" if "AL30" in codes else codes[0]
    calculos = []
    real = pricing.compute_metrics

    def lento(**kw):
        calculos.append(kw["value"])
        time.sleep(0.08)
        return real(**kw)

    monkeypatch.setattr(pricing, "compute_metrics", lento)
    yas_routes._INFLIGHT.clear()
    base = {"code": code, "mode": "precio", "value": "60,5", "nominales": "1000000", "plazo": "24hs"}
    async with _client() as ac:
        rs = await asyncio.gather(*[ac.post("/yas/recompute", data=base) for _ in range(4)])
        assert all(r.status_code == 200 and "TIREA" in r.text for r in rs)
        assert calculos == [60.5]                                  # 4 requests idénticos → 1 cálculo
        assert not yas_routes._INFLIGHT                            # se limpia al terminar
        r1, r2 = await asyncio.gather(ac.post("/yas/recompute", data={**base, "value": "61"}),
                                      ac.post("/yas/recompute", data={**base, "nominales": "2000000"}))
        assert r1.status_code == 200 and r2.status_code == 200
        assert sorted(calculos) == [60.5, 60.5, 61.0]              # distinto valor / VN: cálculo propio
