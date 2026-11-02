"""probar_conexion.py (raíz): diagnóstico paso a paso de la conexión al broker.

Sin red en la suite: se prueba que el script importa sin efectos, que contra
un host que no escucha termina SIN excepción y con el paso TCP en FALLO, que
el paso de login muestra crudo lo que contesta un Spring Security de mentira
(302 a login.html?error=true = clave rechazada; 302 a / = aceptada), que el
paso 'credenciales' avisa cuando el loader de secrets.txt tocaría la clave, y
que `diagnostico()` (pura) mapea cada tipo de fallo a su causa probable."""
from __future__ import annotations

import asyncio
import importlib
import socket

import pytest


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


# ── Spring Security de mentira: contesta como matrizoms ──────────────────────
async def _spring(clave_ok: str):
    """Servidor HTTP mínimo: POST j_spring_security_check → 302 a '/' si la
    clave coincide, 302 a /login.html?error=true si no; GET → 200 html."""
    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = await reader.readuntil(b"\r\n\r\n")
            linea = head.split(b"\r\n", 1)[0].decode()
            metodo, path, _ = linea.split(" ", 2)
            n = 0
            for h in head.decode().split("\r\n"):
                if h.lower().startswith("content-length:"):
                    n = int(h.split(":", 1)[1])
            cuerpo = (await reader.readexactly(n)).decode() if n else ""
            if metodo == "POST" and path.endswith("j_spring_security_check"):
                ok = f"j_password={clave_ok}" in cuerpo
                loc = "/" if ok else "/login.html?error=true"
                resp = (f"HTTP/1.1 302 Found\r\nLocation: {loc}\r\nSet-Cookie: JSESSIONID=abc; Path=/\r\n"
                        "Content-Length: 0\r\nConnection: close\r\n\r\n")
            else:
                html = "<html><head><title>Login OMS</title></head><body>login</body></html>"
                resp = (f"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: {len(html)}\r\n"
                        f"Connection: close\r\n\r\n{html}")
            writer.write(resp.encode())
            await writer.drain()
        finally:
            writer.close()

    return await asyncio.start_server(handler, "127.0.0.1", 0)


def test_login_muestra_crudo_lo_que_contesta_spring(capsys) -> None:
    m = _mod()

    async def go():
        srv = await _spring("buena")
        port = srv.sockets[0].getsockname()[1]
        host = f"http://127.0.0.1:{port}/"
        try:
            m.RES.clear()
            cli = await m.paso_login(host, "rc", "mala")
            assert cli is None
            rech = dict(m.RES["login"])
            cli = await m.paso_login(host, "rc", "buena")
            assert cli is not None and cli._cookies is not None
            assert [c.name for c in cli._cookies.jar] == ["JSESSIONID"]
            await cli._http.aclose()
            return rech, dict(m.RES["login"])
        finally:
            srv.close()
            await srv.wait_closed()

    rech, acept = asyncio.run(go())
    out = capsys.readouterr().out
    assert rech["ok"] is False and "RECHAZÓ" in rech["detalle"] and "login.html?error=true" in rech["detalle"]
    assert "credenciales rechazadas" in rech["error"]
    assert "→ HTTP 302   Location: /login.html?error=true   Set-Cookie: ['JSESSIONID']" in out
    assert "título: Login OMS" in out                       # el salto siguiente, con su página
    assert acept["ok"] is True and acept["cookies"] == ["JSESSIONID"]
    assert "j_password=***" in out and "mala" not in out and "buena" not in out   # la clave nunca se imprime
    # el diagnóstico explica que es Spring diciendo "incorrectos", no un 4xx
    base = {"dns": {"ok": True}, "tcp": {"ok": True}, "tls": {"ok": True}, "http": {"ok": True, "status": 200}}
    d = m.diagnostico({**base, "login": rech})
    assert "INCORRECTOS" in d[0] and "no manda 401/403" in d[0]


def test_credenciales_avisa_si_el_loader_toca_la_clave(tmp_path, monkeypatch, capsys) -> None:
    m = _mod()
    import OMSsecrets
    f = tmp_path / "secrets.txt"
    f.write_text("OMS_USER=rc\nOMS_PASS=\"cla$ve\"  \n", encoding="utf-8")
    monkeypatch.setattr(OMSsecrets, "_resolve_secrets_path", lambda: str(f))
    monkeypatch.setattr(OMSsecrets, "_last_load", {"OMS_USER": "rc", "OMS_PASS": "clave"})
    monkeypatch.setattr(m, "USUARIO", "")
    monkeypatch.setattr(m, "CLAVE", "")
    m.RES.clear()
    m.paso_credenciales("rc", "cla")                        # la que se usa tiene 3 car., el archivo 6
    out = capsys.readouterr().out
    assert m.RES["credenciales"]["ok"] is False
    assert "entre comillas" in out and "espacios" in out and "['$']" in out
    assert "tiene 6 caracteres y se está usando uno de 3" in out
    assert "cla$ve" not in out                               # nunca el valor
    # tal cual: sin avisos
    f.write_text("OMS_USER=rc\nOMS_PASS=clave\n", encoding="utf-8")
    monkeypatch.setenv("OMS_PASS", "clave")
    m.paso_credenciales("rc", "clave")
    assert m.RES["credenciales"]["ok"] is True
    # viene del entorno de Windows, no del archivo
    monkeypatch.setattr(OMSsecrets, "_last_load", {"OMS_USER": "rc"})
    m.paso_credenciales("rc", "clave")
    assert m.RES["credenciales"]["ok"] is False and "ENTORNO" in capsys.readouterr().out


@pytest.mark.parametrize("res, esperado", [
    ({"dns": {"ok": False}}, "no resuelve"),
    ({"dns": {"ok": True}, "tcp": {"ok": False}}, "firewall"),
    ({"dns": {"ok": True}, "tcp": {"ok": True}, "tls": {"ok": False}}, "TLS"),
])
def test_diagnostico_red(res, esperado) -> None:
    assert esperado in _mod().diagnostico(res)[0]


def test_diagnostico_mapea_cada_fallo() -> None:
    d = _mod().diagnostico
    base = {"dns": {"ok": True}, "tcp": {"ok": True}, "tls": {"ok": True}}
    assert "HTTP 403" in d({**base, "http": {"ok": True, "status": 403}})[0]
    assert "INCORRECTOS" in d({**base, "http": {"ok": True, "status": 200},
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
