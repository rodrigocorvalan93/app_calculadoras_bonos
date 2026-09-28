"""Consola de arranque (backend/consola.py): banner de bienvenida y formato
uniforme de logs (hora · glifo · módulo · mensaje) para backend y uvicorn."""
from __future__ import annotations

import io
import logging
import re
from pathlib import Path

from backend import consola

ROOT = Path(__file__).resolve().parents[1]
_LINEA = re.compile(r"^\d\d:\d\d:\d\d  (·|!|x)  (\S+)\s+(.*)$")


def _rec(name: str, level: int, msg: str, args=()) -> logging.LogRecord:
    return logging.LogRecord(name, level, __file__, 1, msg, args, None)


def test_formato_compacto_modulo_corto_y_sin_tag_repetido() -> None:
    f = consola.Formato()
    m = _LINEA.match(f.format(_rec("backend.main", logging.INFO, "[main] starting up")))
    assert m and m.group(1) == "·" and m.group(2) == "main" and m.group(3) == "starting up"
    m = _LINEA.match(f.format(_rec("backend.services.historico_writer", logging.WARNING, "[historico_writer] FX lockeado")))
    assert m and m.group(1) == "!" and m.group(2) == "historico_writer" and m.group(3) == "FX lockeado"
    # un tag que NO es el módulo se conserva (es información)
    m = _LINEA.match(f.format(_rec("backend.services.historico_writer", logging.ERROR, "[BCRA 7] error de red")))
    assert m and m.group(1) == "x" and m.group(3) == "[BCRA 7] error de red"
    # uvicorn: módulo 'uvicorn'; access log compacto 'GET /ruta → status · cliente'
    m = _LINEA.match(f.format(_rec("uvicorn.error", logging.INFO, "Uvicorn running on http://127.0.0.1:8000")))
    assert m and m.group(2) == "uvicorn"
    acc = f.format(_rec("uvicorn.access", logging.INFO, '%s - "%s %s HTTP/%s" %d',
                        ("127.0.0.1:50000", "GET", "/yas", "1.1", 200)))
    assert acc.endswith("http             GET /yas → 200 · 127.0.0.1:50000")
    # salida que no puede con · / → (archivo cp1252 del servicio): ASCII, sin → en el log
    f_ascii = consola.Formato(encoding="ascii")
    acc = f_ascii.format(_rec("uvicorn.access", logging.INFO, '%s - "%s %s HTTP/%s" %d',
                              ("127.0.0.1:50000", "GET", "/yas", "1.1", 200)))
    assert acc.isascii() and acc.endswith("GET /yas -> 200 - 127.0.0.1:50000")
    assert "  -  main" in f_ascii.format(_rec("backend.main", logging.INFO, "[main] hola"))
    # traceback pegado abajo
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        r = _rec("backend.main", logging.ERROR, "[main] falló")
        r.exc_info = sys.exc_info()
    out = f.format(r)
    assert "falló\nTraceback" in out and "ValueError: boom" in out


def test_instalar_formatea_consola_y_uvicorn_sin_tocar_otros_handlers() -> None:
    root = logging.getLogger()
    otros = [h for h in root.handlers if not consola._es_consola(h)]
    uv = logging.getLogger("uvicorn")
    uv_access = logging.getLogger("uvicorn.access")
    h_uv, h_acc = logging.StreamHandler(), logging.StreamHandler()
    h_uv.setFormatter(logging.Formatter("%(message)s uvicorn-default"))
    h_acc.setFormatter(logging.Formatter("%(message)s uvicorn-access"))
    ajeno = logging.StreamHandler(io.StringIO())      # p. ej. caplog / ring de /admin
    ajeno.setFormatter(logging.Formatter("%(message)s ajeno"))
    uv.addHandler(h_uv); uv_access.addHandler(h_acc); root.addHandler(ajeno)
    try:
        consola.instalar(logging.INFO)
        assert isinstance(h_uv.formatter, consola.Formato) and isinstance(h_acc.formatter, consola.Formato)
        assert ajeno.formatter._fmt == "%(message)s ajeno"           # no se toca
        assert any(consola._es_consola(h) and isinstance(h.formatter, consola.Formato) for h in root.handlers)
        for h in otros:
            assert h in root.handlers
    finally:
        uv.removeHandler(h_uv); uv_access.removeHandler(h_acc); root.removeHandler(ajeno)


def test_banner_bienvenida_autor_y_para_quien() -> None:
    lineas = consola.banner("http://127.0.0.1:8000", "https://localhost:8443", encoding="utf-8")
    txt = "\n".join(lineas)
    assert lineas[0].startswith("╭") and lineas[-1].startswith("╰")
    assert "ΔYieldVertex" in txt and "Rodrigo Corvalán" in txt
    assert "Delta Asset Management" in txt and "Galileo" in txt and "Latin Securities" in txt
    assert "http://127.0.0.1:8000" in txt and "https://localhost:8443" in txt and "Python" in txt
    assert len({len(l) for l in lineas}) == 1                           # recuadro parejo
    # salida que no puede con Unicode (stdout redirigido con cp1252 / ascii): cae a ASCII
    asc = consola.banner("http://127.0.0.1:8000", "", encoding="ascii")
    j = "\n".join(asc)
    assert asc[0].startswith("+") and j.isascii() and "Rodrigo Corvalan" in j and "YieldVertex" in j
    assert "Add-in" not in j                                            # sin puente: sin la línea
    assert consola.version() == "" or "@" in consola.version() or len(consola.version()) >= 7


def test_url_app_desde_env(monkeypatch) -> None:
    monkeypatch.delenv("APP_HOST", raising=False); monkeypatch.delenv("PORT", raising=False)
    monkeypatch.delenv("APP_PORT", raising=False)
    assert consola.url_app() == "http://127.0.0.1:8000"
    monkeypatch.setenv("APP_HOST", "0.0.0.0"); monkeypatch.setenv("PORT", "8001")
    assert consola.url_app().startswith("http://127.0.0.1:8001") and "0.0.0.0" in consola.url_app()


def test_app_ya_corriendo_sonda_http(monkeypatch) -> None:
    """Segunda instancia: sólo una respuesta HTTP real cuenta. Un socket que
    acepta y no contesta (supervisor de --reload) da False; puerto cerrado,
    False. PORT/APP_PORT inválidos → None (no se chequea)."""
    import socket
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class _H(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(200); self.end_headers(); self.wfile.write(b"ok")

        def log_message(self, *a):  # noqa: D102
            pass

    srv = HTTPServer(("127.0.0.1", 0), _H)
    t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
    try:
        assert consola.app_ya_corriendo(srv.server_address[1], timeout=2.0) is True
    finally:
        srv.shutdown(); srv.server_close()
    mudo = socket.socket(); mudo.bind(("127.0.0.1", 0)); mudo.listen(1)
    try:
        assert consola.app_ya_corriendo(mudo.getsockname()[1], timeout=0.3) is False
    finally:
        mudo.close()
    libre = socket.socket(); libre.bind(("127.0.0.1", 0)); puerto_libre = libre.getsockname()[1]; libre.close()
    assert consola.app_ya_corriendo(puerto_libre, timeout=0.3) is False
    monkeypatch.delenv("PORT", raising=False); monkeypatch.delenv("APP_PORT", raising=False)
    assert consola.puerto_configurado() is None
    monkeypatch.setenv("PORT", "8000"); assert consola.puerto_configurado() == 8000
    monkeypatch.setenv("PORT", "abc"); assert consola.puerto_configurado() is None
    monkeypatch.setenv("PORT", "0"); assert consola.puerto_configurado() is None


def test_version_en_mac_sin_command_line_tools_no_invoca_el_stub_de_git(monkeypatch) -> None:
    """macOS sin Command Line Tools: /usr/bin/git es un stub de Apple que abre
    el diálogo de instalación. `xcode-select -p` ≠ 0 → no se llama a git (el
    banner lee .git a mano); con las CLT, git como siempre. Una sonda por
    proceso."""
    llamadas = []
    clt = {"rc": 2}

    class _R:
        def __init__(self, rc, out=""):
            self.returncode, self.stdout, self.stderr = rc, out, ""

    def fake_run(argv, **kw):
        llamadas.append(argv[0])
        if argv[0] == "xcode-select":
            return _R(clt["rc"])
        if argv[0] == "git":
            return _R(0, "abc1234 2026-09-28\n") if argv[3] == "log" else _R(0, "main\n")
        raise AssertionError(argv)

    monkeypatch.setattr(consola, "_DARWIN", True)
    monkeypatch.setattr(consola, "_clt_ok", None)
    monkeypatch.setattr(consola.subprocess, "run", fake_run)
    v = consola.version()
    assert "git" not in llamadas and llamadas.count("xcode-select") == 1
    assert isinstance(v, str)                       # .git a mano (o '' sin repo)
    consola.version()
    assert llamadas.count("xcode-select") == 1      # cacheado
    clt["rc"] = 0
    monkeypatch.setattr(consola, "_clt_ok", None)
    assert consola.version() == "main @ abc1234 · 2026-09-28"
    assert "git" in llamadas


def test_main_usa_consola_y_los_launchers_estan_ordenados() -> None:
    main = (ROOT / "backend" / "main.py").read_text(encoding="utf-8")
    assert "consola.instalar(" in main and "consola.imprimir_banner(" in main and "logging.basicConfig" not in main
    assert "listo en %.1f s" in main
    bat = (ROOT / "run_backend (CORRER APP).bat").read_text(encoding="utf-8")
    cmd = (ROOT / "correr_app.command").read_text(encoding="utf-8")
    for launcher in (bat, cmd):
        assert "arranque local" in launcher and "Carpeta :" in launcher and "Python  :" in launcher
        assert "Add-in  :" in launcher and "Ctrl+C para detener" in launcher
        assert "/healthz" in launcher and "OMS_RELOAD=1" in launcher     # 2ª instancia → sólo el navegador; dev sin chequeo
    assert bat.isascii()                                                # cmd.exe sin sorpresas de code page
    assert "consola.app_ya_corriendo(" in main and 'os.environ.get("OMS_RELOAD") != "1"' in main
    # macOS: FDs por proceso (tope 256 en una terminal), el puente apunta al
    # puerto real y certifi sólo si contesta (SSL_CERT_FILE vacío = sin CAs)
    assert cmd.startswith("#!/bin/zsh") and "ulimit -S -n 4096" in cmd
    assert 'export TLS_TARGET_PORT="${TLS_TARGET_PORT:-$PORT}"' in cmd
    assert '[ -n "$CERTIFI" ] && export SSL_CERT_FILE="$CERTIFI"' in cmd
    assert "\r" not in cmd                                              # CRLF rompe el shebang en zsh
