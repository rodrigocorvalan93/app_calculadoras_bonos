"""probar_conexion.py (raíz): diagnóstico paso a paso de la conexión al broker.

Sin red en la suite: se prueba que el script importa sin efectos, que contra
un host que no escucha termina SIN excepción y con el paso TCP en FALLO, y
que `diagnostico()` (pura) mapea cada tipo de fallo a su causa probable."""
from __future__ import annotations

import asyncio
import importlib
import socket


def _mod():
    return importlib.import_module("probar_conexion")


def test_importa_sin_correr_nada() -> None:
    m = _mod()
    assert m.HOST.startswith("https://") and m.SIMBOLOS and m.RES == {}
    assert callable(m.probar) and callable(m.escuchar) and callable(m.login)


def test_host_que_no_escucha_termina_en_tcp_fallo() -> None:
    m = _mod()
    # puerto libre de loopback: DNS resuelve, el TCP se rechaza al instante
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        puerto = s.getsockname()[1]
    res = asyncio.run(m.correr(host=f"http://127.0.0.1:{puerto}/", usuario="u", clave="c",
                               simbolos=["MERV - XMEV - AL30 - 24hs"], escuchar_s=0))
    assert res["entorno"]["ok"] and res["dns"]["ok"] and res["dns"]["ips"] == ["127.0.0.1"]
    assert res["tcp"]["ok"] is False and "login" not in res          # cortó antes del login
    assert any("firewall" in l for l in m.diagnostico(res))


def test_diagnostico_mapea_cada_fallo() -> None:
    d = _mod().diagnostico
    assert "no resuelve" in d({"dns": {"ok": False}})[0]
    assert "firewall" in d({"dns": {"ok": True}, "tcp": {"ok": False}})[0]
    assert "TLS" in d({"dns": {"ok": True}, "tcp": {"ok": True}, "tls": {"ok": False}})[0]
    base = {"dns": {"ok": True}, "tcp": {"ok": True}, "tls": {"ok": True}}
    assert "HTTP 403" in d({**base, "http": {"ok": True, "status": 403}})[0]
    assert "usuario/clave" in d({**base, "http": {"ok": True, "status": 200},
                                  "login": {"ok": False, "error": "login: credenciales rechazadas (redirect a login)"}})[0]
    ok_login = {**base, "http": {"ok": True, "status": 200}, "login": {"ok": True}, "rest": {"ok": True}}
    assert "handshake del WS vuelve 4xx" in d({**ok_login, "ws": {"ok": False, "detalle": "InvalidStatus: HTTP 403"}})[0]
    assert "WebSockets" in d({**ok_login, "ws": {"ok": False, "detalle": "TimeoutError: timed out"}})[0]
    sin_md = {**ok_login, "ws": {"ok": True}, "ws_md": {"md_total": 0, "errores": [], "cerrado": ""}}
    assert "fuera de rueda" in d(sin_md, en_rueda=False)[0]
    assert "market data habilitado" in d(sin_md, en_rueda=True)[0]
    con_err = {**ok_login, "ws": {"ok": True}, "ws_md": {"md_total": 0, "errores": ["Invalid symbol"], "cerrado": ""}}
    assert "ERROR al smd" in d(con_err, en_rueda=True)[0]
    todo_ok = {**ok_login, "ws": {"ok": True}, "ws_md": {"md_total": 12, "errores": [], "cerrado": ""}}
    assert "Todo funciona" in d(todo_ok)[0]
