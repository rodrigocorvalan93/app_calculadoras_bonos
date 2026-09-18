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


def test_main_usa_consola_y_los_launchers_estan_ordenados() -> None:
    main = (ROOT / "backend" / "main.py").read_text(encoding="utf-8")
    assert "consola.instalar(" in main and "consola.imprimir_banner(" in main and "logging.basicConfig" not in main
    assert "listo en %.1f s" in main
    bat = (ROOT / "run_backend (CORRER APP).bat").read_text(encoding="utf-8")
    cmd = (ROOT / "correr_app.command").read_text(encoding="utf-8")
    for launcher in (bat, cmd):
        assert "arranque local" in launcher and "Carpeta :" in launcher and "Python  :" in launcher
        assert "Add-in  :" in launcher and "Ctrl+C para detener" in launcher
    assert bat.isascii()                                                # cmd.exe sin sorpresas de code page
