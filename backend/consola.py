"""Consola de arranque: banner de bienvenida + logs prolijos.

Lo que ve quien levanta la app en una terminal ("run_backend (CORRER APP).bat",
"correr_app.command" o el servicio): un recuadro con qué es la app, de quién
es y para quién, dónde escucha y qué versión corre; y después TODAS las
líneas del arranque y de la rueda en un formato uniforme

    HH:MM:SS  ·  módulo        mensaje

también las de uvicorn (que trae su propio formato) y el access log, que
queda como `GET /ruta → 200 · cliente` (el filtro de polling de main.py sigue
igual). Nada de esto toca un request: se configura una vez al importar
backend.main. Si stdout está redirigido a un archivo con un encoding pobre
(servicio Windows con cp1252), el banner cae a ASCII en vez de romper el
arranque.
"""
from __future__ import annotations

import logging
import os
import platform
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from typing import List, Optional

APP = "ΔYieldVertex"
AUTOR = "Rodrigo Corvalán"
PARA = "Delta Asset Management · Galileo · Latin Securities"
_ROOT = Path(__file__).resolve().parents[1]

_GLIFO = {logging.DEBUG: "·", logging.INFO: "·", logging.WARNING: "!",
          logging.ERROR: "x", logging.CRITICAL: "x"}
_PREFIJOS = ("backend.services.", "backend.routes.", "backend.tools.", "backend.")
_TAG = re.compile(r"^\[([\w.\-]+)\]\s+")


# ── Formato de log ────────────────────────────────────────────────────────────
class Formato(logging.Formatter):
    """`HH:MM:SS  glifo  módulo  mensaje` (+ traceback). El módulo sale corto
    (`backend.services.historico_writer` → `historico_writer`, uvicorn.access →
    `http`) y se quita el `[tag]` inicial cuando repite el módulo. Si la
    salida no puede escribir `·` / `→` (stderr redirigido a un archivo cp1252
    por el servicio de Windows), usa `-` / `->` en vez de ensuciar el log."""

    def __init__(self, encoding: Optional[str] = None) -> None:
        super().__init__()
        enc = encoding if encoding is not None else getattr(sys.stderr, "encoding", None)
        self._uni = _puede(enc, "·→")

    def modulo(self, name: str) -> str:
        if name == "uvicorn.access":
            return "http"
        if name.startswith("uvicorn"):
            return "uvicorn"
        for p in _PREFIJOS:
            if name.startswith(p):
                return name[len(p):] or "app"
        return name or "app"

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003 — API de logging
        mod = self.modulo(record.name)
        args = record.args
        punto, flecha = ("·", "→") if self._uni else ("-", "->")
        if record.name == "uvicorn.access" and isinstance(args, tuple) and len(args) == 5:
            cli, met, ruta, _ver, st = args
            msg = f"{met} {ruta} {flecha} {st} {punto} {cli}"
        else:
            msg = record.getMessage()
            m = _TAG.match(msg)
            if m and (m.group(1) == mod or mod.endswith(m.group(1))):
                msg = msg[m.end():]
        hora = time.strftime("%H:%M:%S", self.converter(record.created))
        glifo = _GLIFO.get(record.levelno, "·")
        if not self._uni and glifo == "·":
            glifo = "-"
        linea = f"{hora}  {glifo}  {mod:<16} {msg}"
        if record.exc_info:
            linea += "\n" + self.formatException(record.exc_info)
        if record.stack_info:
            linea += "\n" + record.stack_info
        return linea


def _es_consola(h: logging.Handler) -> bool:
    """Sólo los handlers que escriben a la terminal: no se toca el de pytest
    (caplog) ni el ring de /admin (errores.install)."""
    return isinstance(h, logging.StreamHandler) and getattr(h, "stream", None) in (sys.stderr, sys.stdout)


def instalar(level: int = logging.INFO) -> None:
    """Formato uniforme para el root (backend.*) y para los handlers que
    uvicorn ya configuró (los suyos no propagan al root)."""
    fmt = Formato()
    root = logging.getLogger()
    if not any(_es_consola(h) for h in root.handlers):
        root.addHandler(logging.StreamHandler())          # stderr, como basicConfig
    root.setLevel(level)
    for h in root.handlers:
        if _es_consola(h):
            h.setFormatter(fmt)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        for h in logging.getLogger(name).handlers:
            if _es_consola(h):
                h.setFormatter(fmt)


# ── Banner ────────────────────────────────────────────────────────────────────
def version() -> str:
    """'rama @ sha7 · AAAA-MM-DD' desde git (si está en el PATH) o leyendo
    .git a mano; '' si no hay repo. Nunca tira."""
    try:
        log = subprocess.run(["git", "-C", str(_ROOT), "log", "-1", "--format=%h %cs", "HEAD"],
                             capture_output=True, text=True, timeout=2.0)
        if log.returncode == 0 and log.stdout.strip():
            sha, fecha = (log.stdout.split() + [""])[:2]
            rama = subprocess.run(["git", "-C", str(_ROOT), "rev-parse", "--abbrev-ref", "HEAD"],
                                  capture_output=True, text=True, timeout=2.0)
            r = rama.stdout.strip() if rama.returncode == 0 else ""
            r = r if len(r) <= 24 else ""            # una rama de trabajo larga no ensancha el recuadro
            return (f"{r} @ " if r and r != "HEAD" else "") + sha + (f" · {fecha}" if fecha else "")
    except Exception:  # noqa: BLE001
        pass
    try:
        head = (_ROOT / ".git" / "HEAD").read_text(encoding="utf-8").strip()
        if not head.startswith("ref: "):
            return head[:7]
        ref = head[5:]
        p = _ROOT / ".git" / ref
        sha = p.read_text(encoding="utf-8").strip() if p.exists() else ""
        if not sha:
            for line in (_ROOT / ".git" / "packed-refs").read_text(encoding="utf-8").splitlines():
                if line.endswith(" " + ref):
                    sha = line.split()[0]
                    break
        rama = ref.rsplit("/", 1)[-1]
        return f"{rama} @ {sha[:7]}" if sha else rama
    except Exception:  # noqa: BLE001
        return ""


def _puede(enc: Optional[str], texto: str) -> bool:
    try:
        texto.encode(enc or "utf-8")
        return True
    except (UnicodeEncodeError, LookupError):
        return False


def _ascii(texto: str) -> str:
    """Sin acentos ni símbolos: para una salida que no los puede escribir."""
    t = texto.replace("·", "-").replace("Δ", "").replace("→", "->")
    t = unicodedata.normalize("NFKD", t)
    return "".join(c for c in t if not unicodedata.combining(c)).encode("ascii", "replace").decode("ascii")


def puerto_configurado() -> Optional[int]:
    """Puerto que exportan los launchers (PORT / APP_PORT); None si nadie lo
    fijó (uvicorn a mano, servicio) — en ese caso no se chequea nada."""
    raw = (os.environ.get("PORT") or os.environ.get("APP_PORT") or "").strip()
    try:
        p = int(raw)
        return p if 0 < p < 65536 else None
    except ValueError:
        return None


def app_ya_corriendo(port: int, host: str = "127.0.0.1", timeout: float = 0.8) -> bool:
    """¿Hay OTRA instancia de la app respondiendo en host:port? Sonda HTTP a
    /healthz (stdlib): sólo cuenta una respuesta HTTP real. Un socket que
    acepta pero no contesta (el supervisor de `--reload` ya tiene el puerto
    bindeado cuando arranca el worker) da timeout → False, no falso positivo.
    Sin servidor → False. Nunca tira."""
    import http.client
    try:
        c = http.client.HTTPConnection(host, port, timeout=timeout)
        try:
            c.request("GET", "/healthz")
            r = c.getresponse()
            return 100 <= r.status < 600
        finally:
            c.close()
    except Exception:  # noqa: BLE001 — ConnectionRefused, timeout, reset…
        return False


def url_app() -> str:
    """Dónde escucha, según APP_HOST / PORT de secrets.txt (los launchers usan
    127.0.0.1:8000). uvicorn imprime la URL exacta justo después."""
    host = (os.environ.get("APP_HOST") or "127.0.0.1").strip()
    port = (os.environ.get("PORT") or os.environ.get("APP_PORT") or "8000").strip()
    if host in ("0.0.0.0", "::", ""):
        return f"http://127.0.0.1:{port}  (también en la red: {host or '0.0.0.0'})"
    return f"http://{host}:{port}"


def banner(url: str, url_addin: str = "", encoding: Optional[str] = None) -> List[str]:
    """Líneas del recuadro de bienvenida. `encoding` = el de la salida (para
    caer a ASCII cuando no puede con el box-drawing o la Δ)."""
    enc = encoding if encoding is not None else getattr(sys.stdout, "encoding", None)
    unicode_ok = _puede(enc, "╭─╮│╰╯├┤Δ·áó")
    so = {"Darwin": "macOS", "Windows": "Windows", "Linux": "Linux"}.get(platform.system(), platform.system())
    ver = version()
    filas: List[Optional[str]] = [
        f"{APP} · renta fija, mercado y OMS",
        f"Desarrollada por {AUTOR}",
        f"al servicio de {PARA}",
        None,                                                  # separador
        f"App       {url}",
    ]
    if url_addin:
        filas.append(f"Add-in    {url_addin}  (Excel: funciones =OMS.*)")
    filas.append(f"Versión   {ver + ' · ' if ver else ''}Python {platform.python_version()} · {so}")
    if not unicode_ok:
        filas = [_ascii(f) if f else f for f in filas]
    ancho = max(len(f) for f in filas if f) + 4
    if unicode_ok:
        tl, tr, bl, br, h, v, ml, mr = "╭", "╮", "╰", "╯", "─", "│", "├", "┤"
    else:
        tl, tr, bl, br, h, v, ml, mr = "+", "+", "+", "+", "-", "|", "+", "+"
    out = [tl + h * ancho + tr]
    for f in filas:
        out.append(ml + h * ancho + mr if f is None else f"{v}  {f:<{ancho - 2}}{v}")
    out.append(bl + h * ancho + br)
    return out


def imprimir_banner(url: str, url_addin: str = "") -> None:
    """Imprime el recuadro en stdout. Failure-silent: una consola rara nunca
    frena el arranque."""
    try:
        print("\n" + "\n".join(banner(url, url_addin)) + "\n", flush=True)
    except Exception:  # noqa: BLE001
        try:
            print("\n" + "\n".join(banner(url, url_addin, encoding="ascii")) + "\n", flush=True)
        except Exception:  # noqa: BLE001
            pass
