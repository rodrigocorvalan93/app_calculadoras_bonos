# -*- coding: utf-8 -*-
"""probar_conexion.py — ¿por qué no conecta el feed del broker (Latin / LBO / Cocos)?

Repite, UNO POR UNO y con el mismo código que usa la app (`backend.services.
primary_ws`), los pasos que la app da para conectarse al broker, y dice en cuál
se rompe y por qué:

    1. entorno        Python, librerías, proxy del sistema, certificados
    2. DNS            el host resuelve a una IP
    3. TCP            se puede abrir el puerto 443 (firewall / proxy)
    4. TLS            handshake https con el bundle de certifi (y con el default
                      del intérprete: en Mac el de python.org viene vacío)
    5. HTTP           GET a la raíz del broker (un 403 acá = WAF / proxy / IP bloqueada)
    6. LOGIN          POST j_spring_security_check — igual que PrimaryWS.login
                      (Spring responde 200 con redirect a /login?error cuando
                      la clave es mala: se mira la URL final, no el status)
    7. REST           rest/accounts con las cookies de la sesión (¿la sesión sirve?)
    8. WS             wss://… con las cookies, `smd` de los SIMBOLOS y escucha
                      ESCUCHAR_S segundos: cuántos Md llegaron por símbolo y qué
                      contestó el broker que NO era market data (ERROR + motivo)
    9. diagnóstico    lectura de los resultados → causa probable + qué hacer

CÓMO SE CORRE
    - Doble click en `probar_conexion.bat` (usa el venv de la app si existe), o
    - python -i probar_conexion.py          ← queda el prompt interactivo
    - python probar_conexion.py             ← sólo imprime y termina

En el interactivo quedan en memoria:
    RES            dict con el resultado de cada paso (ok / detalle / ms)
    MD             {símbolo: último marketData recibido}
    NO_MD          [mensajes del broker que no fueron Md (errores, confirmaciones)]
    LOG            ruta del archivo con todo lo impreso (para mandarlo)
    probar()       vuelve a correr todo (con lo que haya en el bloque CONFIG)
    escuchar(["MERV - XMEV - AL30 - 24hs"], 30)   ← sólo el paso WS, otros símbolos
    login(host, usuario, clave)                   ← sólo el login, otro broker

QUÉ TOCAR
    Sólo el bloque CONFIG de abajo. La clave NUNCA se imprime ni se guarda en el log.
"""
from __future__ import annotations

# ═══════════════════════════════ CONFIG ══════════════════════════════════════
# Vacío ("") = toma el valor de secrets.txt (OMS_USER / OMS_PASS / PRIMARY_*).
HOST = "https://api.latinsecurities.matrizoms.com.ar/"     # Latin Securities
# HOST = "https://api.lbo.xoms.com.ar/"                     # LBO
# HOST = "https://api.cocos.xoms.com.ar/"                   # Cocos
USUARIO = ""
CLAVE = ""

# Símbolos a suscribir en el paso WS (pocos y líquidos: la idea es ver que
# LLEGUE algo, no bajar el universo). Formato Primary: "MERV - XMEV - <ticker> - <plazo>".
SIMBOLOS = [
    "MERV - XMEV - AL30 - 24hs",
    "MERV - XMEV - GD30 - 24hs",
    "MERV - XMEV - AL30 - CI",
    "MERV - XMEV - GGAL - 24hs",
    "MERV - XMEV - PESOS - 1D",       # caución overnight (puede no existir un viernes)
    "DLR/DIC26M",                     # futuro de dólar (lote aparte, con OI)
]

ESCUCHAR_S = 20          # segundos escuchando el WS (fuera de rueda puede llegar 0 Md y está bien)
TIMEOUT_S = 10           # timeout por paso (DNS / TCP / TLS / HTTP)
PROFUNDIDAD = 2          # niveles del libro que se piden en el smd
# ═════════════════════════════════════════════════════════════════════════════

import asyncio
import json
import os
import platform
import socket
import ssl
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

RES: Dict[str, Dict[str, Any]] = {}
MD: Dict[str, Dict[str, Any]] = {}
NO_MD: List[str] = []
LOG: Optional[str] = None
_LOG_FH = None


# ── salida (pantalla + archivo) ──────────────────────────────────────────────
def _p(*args: Any) -> None:
    txt = " ".join(str(a) for a in args)
    try:
        print(txt)
    except UnicodeEncodeError:                       # consola cp850 sin ✔/→
        print(txt.encode("ascii", "replace").decode("ascii"))
    if _LOG_FH is not None:
        try:
            _LOG_FH.write(txt + "\n")
            _LOG_FH.flush()
        except OSError:
            pass


def _abrir_log() -> None:
    """Un archivo por corrida, FUERA de la carpeta del código (OneDrive)."""
    global LOG, _LOG_FH
    try:
        from backend.services.estado_local import dir_local
        d = dir_local()
    except Exception:  # noqa: BLE001
        d = Path.home()
    try:
        d.mkdir(parents=True, exist_ok=True)
        LOG = str(d / f"probar_conexion_{datetime.now():%Y%m%d_%H%M%S}.txt")
        _LOG_FH = open(LOG, "w", encoding="utf-8")
    except OSError:
        LOG, _LOG_FH = None, None


def _paso(nombre: str, ok: Optional[bool], detalle: str, ms: Optional[float] = None, **extra: Any) -> None:
    RES[nombre] = {"ok": ok, "detalle": detalle, "ms": ms, **extra}
    tag = "OK   " if ok else ("FALLO" if ok is False else "----")
    t = f"  ({ms:.0f} ms)" if ms is not None else ""
    _p(f"[{tag}] {nombre:<12} {detalle}{t}")


def _cred() -> tuple[str, str]:
    """Usuario / clave: el bloque CONFIG manda; vacío → secrets.txt vía backend.config."""
    u, c = USUARIO, CLAVE
    if not u or not c:
        try:
            from backend.config import settings
            u = u or settings.primary_user
            c = c or settings.primary_pass
        except Exception as e:  # noqa: BLE001
            _p(f"       (no pude leer secrets.txt vía backend.config: {type(e).__name__}: {e})")
    return u or "", c or ""


def _host_port(host: str) -> tuple[str, int]:
    u = urlsplit(host)
    return (u.hostname or host), (u.port or (443 if u.scheme == "https" else 80))


# ── pasos ────────────────────────────────────────────────────────────────────
def paso_entorno(host: str) -> None:
    import certifi
    import httpx
    import websockets
    hn, port = _host_port(host)
    _p(f"Host            {host}   →  {hn}:{port}")
    _p(f"Python          {platform.python_version()}  {platform.system()} {platform.release()}  ({sys.executable})")
    _p(f"Librerías       httpx {httpx.__version__} · websockets {getattr(websockets, '__version__', '?')} · certifi {certifi.__version__}")
    proxies = {k: v for k, v in os.environ.items()
               if k.upper() in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "NO_PROXY", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE")}
    _p(f"Proxy / certs   {proxies if proxies else 'sin variables de proxy en el entorno'}")
    try:
        import urllib.request
        sysp = {k: v for k, v in urllib.request.getproxies().items() if k in ("http", "https", "no")}
        if sysp:
            _p(f"Proxy sistema   {sysp}   ← lo usa httpx si no hay variable; el WS NO lo usa")
    except Exception:  # noqa: BLE001
        pass
    u, c = _cred()
    _p(f"Usuario         {u!r}   clave: {'*' * len(c) if c else 'VACÍA — poné CLAVE en CONFIG o OMS_PASS en secrets.txt'}")
    _paso("entorno", True, "listo")


def paso_dns(host: str) -> Optional[str]:
    hn, port = _host_port(host)
    t0 = time.perf_counter()
    try:
        infos = socket.getaddrinfo(hn, port, type=socket.SOCK_STREAM)
        ips = sorted({i[4][0] for i in infos})
        _paso("dns", True, f"{hn} → {', '.join(ips)}", (time.perf_counter() - t0) * 1000, ips=ips)
        return ips[0]
    except socket.gaierror as e:
        _paso("dns", False, f"{hn} no resuelve: {e}", (time.perf_counter() - t0) * 1000)
        return None


def paso_tcp(host: str) -> bool:
    hn, port = _host_port(host)
    t0 = time.perf_counter()
    try:
        with socket.create_connection((hn, port), timeout=TIMEOUT_S) as s:
            peer = s.getpeername()
        _paso("tcp", True, f"puerto {port} abierto ({peer[0]})", (time.perf_counter() - t0) * 1000)
        return True
    except (OSError, socket.timeout) as e:
        _paso("tcp", False, f"no abre {hn}:{port}: {e}", (time.perf_counter() - t0) * 1000)
        return False


def paso_tls(host: str) -> bool:
    """Handshake con certifi (lo que usa la app) y con el default del intérprete."""
    import certifi
    hn, port = _host_port(host)
    if not host.startswith("https://"):
        _paso("tls", None, "host http:// — sin TLS")
        return True
    ok_certifi = False
    for nombre, ctx in (("certifi", ssl.create_default_context(cafile=certifi.where())),
                        ("default", ssl.create_default_context())):
        t0 = time.perf_counter()
        try:
            with socket.create_connection((hn, port), timeout=TIMEOUT_S) as raw:
                with ctx.wrap_socket(raw, server_hostname=hn) as s:
                    cert = s.getpeercert() or {}
                    subj = dict(x[0] for x in cert.get("subject", ())).get("commonName", "?")
                    hasta = cert.get("notAfter", "?")
                    det = f"{s.version()} · {s.cipher()[0]} · cert CN={subj} vence {hasta}"
            if nombre == "certifi":
                ok_certifi = True
                _paso("tls", True, det, (time.perf_counter() - t0) * 1000)
            else:
                _p("       TLS con las CAs default del intérprete: OK")
        except ssl.SSLError as e:
            if nombre == "certifi":
                _paso("tls", False, f"SSL: {e}", (time.perf_counter() - t0) * 1000)
            else:
                _p(f"       TLS con las CAs default del intérprete: FALLA ({e.reason or e}) — "
                   "no afecta a la app (usa certifi) pero sí a scripts que no lo usen")
        except (OSError, socket.timeout) as e:
            if nombre == "certifi":
                _paso("tls", False, f"{type(e).__name__}: {e}", (time.perf_counter() - t0) * 1000)
    return ok_certifi


async def paso_http(host: str) -> Optional[int]:
    import httpx
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(base_url=host, timeout=httpx.Timeout(TIMEOUT_S, connect=5.0),
                                     follow_redirects=True) as c:
            r = await c.get("")
        ms = (time.perf_counter() - t0) * 1000
        det = f"GET {host} → HTTP {r.status_code} (url final {r.url}) · server={r.headers.get('server', '?')}"
        _paso("http", r.status_code < 500, det, ms, status=r.status_code, url_final=str(r.url))
        if r.status_code in (401, 403):
            _p(f"       cuerpo: {r.text[:200]!r}")
        return r.status_code
    except httpx.HTTPError as e:
        _paso("http", False, f"{type(e).__name__}: {e}", (time.perf_counter() - t0) * 1000)
        return None


def paso_credenciales(usuario: str, clave: str) -> None:
    """De dónde salieron usuario y clave y si el loader de secrets.txt los tocó.

    `OMSsecrets` NO pisa una variable que ya exista en el entorno de Windows
    (una OMS_PASS vieja en "Variables de entorno" gana al archivo) y EXPANDE
    `%VAR%`, `$VAR` y `~` adentro del valor (una clave con `$` o `%` llega
    cambiada). Acá se compara el valor crudo del archivo con el que se usa,
    sin imprimir ninguno."""
    if USUARIO and CLAVE:
        _paso("credenciales", True, "usuario y clave del bloque CONFIG (secrets.txt no interviene)")
        return
    try:
        import OMSsecrets
        ruta = OMSsecrets._resolve_secrets_path()
    except Exception as e:  # noqa: BLE001
        _paso("credenciales", None, f"no pude leer secrets.txt ({type(e).__name__}: {e})")
        return
    if not ruta:
        _paso("credenciales", False, "no hay secrets.txt (ni SECRETS_FILE): sin usuario/clave")
        return
    crudo: Dict[str, str] = {}
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            for linea in f:
                if "=" in linea and not linea.lstrip().startswith("#"):
                    k, _, v = linea.partition("=")
                    crudo[k.strip()] = v.rstrip("\r\n")
    except OSError as e:
        _paso("credenciales", False, f"{ruta}: {e}")
        return
    aplicadas = set(getattr(OMSsecrets, "_last_load", {}) or {})
    avisos: List[str] = []
    for nombre, usado, claves in (("usuario", usuario, ("PRIMARY_USER", "OMS_USER")),
                                  ("clave", clave, ("PRIMARY_PASS", "OMS_PASS"))):
        k = next((c for c in claves if c in crudo), None)
        if k is None:
            avisos.append(f"{nombre}: ninguna de {claves} está en el archivo")
            continue
        raw = crudo[k]
        if k in os.environ and k not in aplicadas:
            avisos.append(f"{nombre}: {k} viene del ENTORNO de Windows, no del archivo "
                          "(revisar Variables de entorno del sistema / usuario)")
        v = raw.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
            avisos.append(f"{nombre}: {k} está entre comillas en el archivo — el loader las saca")
            v = v[1:-1]
        if raw != raw.strip():
            avisos.append(f"{nombre}: {k} tiene espacios al principio o al final en el archivo — el loader los saca")
        raros = [c for c in ("%", "$", "~", "#") if c in v]
        if raros:
            avisos.append(f"{nombre}: {k} contiene {raros} — el loader expande %VAR% / $VAR / ~ "
                          "(si la clave real los tiene, ponela en el bloque CONFIG del script)")
        if len(v) != len(usado):
            avisos.append(f"{nombre}: en el archivo tiene {len(v)} caracteres y se está usando uno de {len(usado)}: "
                          "el valor en uso NO es el del archivo")
    det = f"secrets.txt = {ruta} · usuario {len(usuario)} car. · clave {len(clave)} car."
    if avisos:
        _paso("credenciales", False, det)
        for a in avisos:
            _p(f"       ⚠ {a}")
    else:
        _paso("credenciales", True, det + " · tal cual están en el archivo")


async def paso_login(host: str, usuario: str, clave: str):
    """El mismo POST que manda la app (`PrimaryWS.login`: j_spring_security_check
    con j_username / j_password), pero SIN seguir redirects, para ver crudo qué
    contestó el broker en cada salto. Devuelve un PrimaryWS con la sesión o None.

    Cómo responde Spring Security (lo que hace matrizoms):
        302 → /                 (o marketdata.html)   usuario y clave aceptados
        302 → /login.html?error=true                  usuario o clave INCORRECTOS
        200 con la página de login                    el POST no llegó al filtro de login
    Nunca manda un 401 / 403 / 402 por clave mala: el "error" viaja en la URL."""
    import httpx
    from backend.services.primary_ws import PrimaryWS
    if not usuario or not clave:
        _paso("login", False, "faltan usuario o clave (CONFIG o secrets.txt)")
        return None
    http = httpx.AsyncClient(base_url=host, timeout=httpx.Timeout(TIMEOUT_S, connect=5.0),
                             follow_redirects=False)
    t0 = time.perf_counter()
    try:
        r = await http.post("j_spring_security_check", data={"j_username": usuario, "j_password": clave})
    except httpx.HTTPError as e:
        _paso("login", False, f"el POST no se completó: {type(e).__name__}: {e}",
              (time.perf_counter() - t0) * 1000, error=f"login: {e}")
        await http.aclose()
        return None
    ms = (time.perf_counter() - t0) * 1000
    loc = r.headers.get("location", "")
    set_cookie = [c.split("=", 1)[0] for c in r.headers.get_list("set-cookie")]
    _p(f"       POST {host}j_spring_security_check  (j_username={usuario!r}, j_password=***)")
    _p(f"       → HTTP {r.status_code}   Location: {loc or '-'}   Set-Cookie: {set_cookie or '-'}")
    if r.status_code in (301, 302, 303, 307, 308) and loc:
        # un salto más, para ver dónde cae (igual que follow_redirects=True en la app)
        try:
            r2 = await http.get(loc)
            _p(f"       GET  {loc}  → HTTP {r2.status_code}   ({len(r2.content)} bytes"
               f"{', título: ' + _titulo(r2.text) if r2.text else ''})")
        except httpx.HTTPError as e:
            _p(f"       GET  {loc}  → {type(e).__name__}: {e}")
    else:
        _p(f"       cuerpo ({len(r.content)} bytes): {r.text[:200]!r}")

    final = loc.lower()
    if r.status_code in (301, 302, 303, 307, 308) and not any(k in final for k in ("login", "error", "authentication")):
        cli = PrimaryWS(host)
        cli._http, cli._cookies = http, http.cookies          # la sesión que acabamos de abrir
        cli._username, cli._password = usuario, clave
        http.follow_redirects = True
        nombres = [ck.name for ck in http.cookies.jar]
        _paso("login", True, f"aceptado: redirige a {loc} · cookies {nombres}", ms, cookies=nombres)
        return cli
    await http.aclose()
    if r.status_code in (301, 302, 303, 307, 308):
        err = f"el broker RECHAZÓ usuario/clave: 302 → {loc}"
    elif r.status_code == 200:
        err = "HTTP 200 sin redirect: el POST no pasó por el login de Spring (¿path distinto en este broker?)"
    else:
        err = f"HTTP {r.status_code}: {r.text[:150]!r}"
    _paso("login", False, err, ms, error=f"login: credenciales rechazadas ({err})" if "RECHAZ" in err else f"login: {err}")
    return None


def _titulo(html: str) -> str:
    import re
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    return m.group(1).strip()[:60] if m else "sin <title>"


async def paso_rest(cli) -> bool:
    from backend.services.primary_ws import BrokerHTTPError, BrokerRespuestaInvalida
    t0 = time.perf_counter()
    try:
        d = await cli.get_json_checked("rest/accounts")
        ms = (time.perf_counter() - t0) * 1000
        cuentas = d.get("accounts") if isinstance(d, dict) else None
        if isinstance(cuentas, list):
            ids = [str(a.get("name") or a.get("id") or "?") for a in cuentas][:8]
            _paso("rest", True, f"rest/accounts → {len(cuentas)} comitente(s): {ids}", ms, cuentas=ids)
        else:
            _paso("rest", True, f"rest/accounts → status={d.get('status') if isinstance(d, dict) else type(d).__name__}", ms)
        return True
    except (BrokerHTTPError, BrokerRespuestaInvalida, RuntimeError) as e:
        _paso("rest", False, str(e), (time.perf_counter() - t0) * 1000)
        return False
    except Exception as e:  # noqa: BLE001
        _paso("rest", False, f"{type(e).__name__}: {e}", (time.perf_counter() - t0) * 1000)
        return False


async def paso_ws(cli, simbolos: List[str], segundos: float) -> Dict[str, Any]:
    """Handshake wss con las cookies + smd + escucha. Mismo payload y mismos
    headers que `PrimaryWS._connect_and_read`, pero sin reconexión ni backoff:
    acá queremos ver el PRIMER error tal cual."""
    import websockets
    from backend.services import primary_ws as pw

    MD.clear()
    NO_MD.clear()
    cookie_hdr = pw._cookie_header(cli._cookies)
    kw: Dict[str, Any] = {"ping_interval": pw.KEEPALIVE_SECS, "ping_timeout": pw.KEEPALIVE_SECS,
                          "max_size": 4 * 1024 * 1024, "close_timeout": 2.0, "open_timeout": TIMEOUT_S}
    if cookie_hdr:
        kw[pw._WS_HEADER_KW] = {"Cookie": cookie_hdr}
    ctx = pw._ssl_context_for(cli.ws_url)
    if ctx is not None:
        kw["ssl"] = ctx
    _p(f"       wss: {cli.ws_url}   headers kwarg: {pw._WS_HEADER_KW}   cookies: {'sí' if cookie_hdr else 'NO'}")

    t0 = time.perf_counter()
    conteo: Dict[str, int] = {s: 0 for s in simbolos}
    errores: List[str] = []
    cerrado = ""
    try:
        async with websockets.connect(cli.ws_url, **kw) as ws:
            _paso("ws", True, "handshake OK (socket abierto)", (time.perf_counter() - t0) * 1000)
            # mismo armado de lotes que la app: resto / futuros (con OI) / cauciones de a uno
            rest = [s for s in simbolos if not pw._is_futuro(s) and not pw._es_diario(s)]
            futs = [s for s in simbolos if pw._is_futuro(s)]
            diarios = [s for s in simbolos if pw._es_diario(s)]
            for grupo, entries in ((rest, None), (futs, pw.ENTRIES_FUT)):
                if grupo:
                    await ws.send(pw._subscribe_payload(grupo, depth=PROFUNDIDAD, entries=entries))
            for s in diarios:
                await ws.send(pw._subscribe_payload([s], depth=PROFUNDIDAD))
            _p(f"       smd enviado: {len(rest)} símbolos + {len(futs)} futuros + {len(diarios)} plazos de caución · "
               f"escuchando {segundos:.0f} s…")
            fin = time.monotonic() + segundos
            primero = None
            while True:
                restante = fin - time.monotonic()
                if restante <= 0:
                    break
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=restante)
                except asyncio.TimeoutError:
                    break
                txt = raw if isinstance(raw, str) else raw.decode("utf-8", "replace")
                try:
                    obj = json.loads(txt)
                except ValueError:
                    NO_MD.append(txt[:300])
                    continue
                if isinstance(obj, dict) and obj.get("type") in ("Md", "md"):
                    sym = (obj.get("instrumentId") or {}).get("symbol") or "?"
                    md = obj.get("marketData") or {}
                    MD[sym] = md
                    conteo[sym] = conteo.get(sym, 0) + 1
                    if primero is None:
                        primero = (time.perf_counter() - t0) * 1000
                        _p(f"       primer Md a los {primero:.0f} ms: {sym}")
                else:
                    NO_MD.append(txt[:600])
                    if isinstance(obj, dict) and obj.get("status") == "ERROR":
                        desc = obj.get("description") or obj.get("error") or obj.get("message")
                        errores.append(str(desc)[:200])
                        _p(f"       broker ERROR: {str(desc)[:200]}")
                    else:
                        _p(f"       mensaje no-Md: {txt[:200]}")
    except Exception as e:  # noqa: BLE001 — handshake / cierre: mostrar tal cual
        det = f"{type(e).__name__}: {e}"
        resp = getattr(e, "response", None)
        if resp is not None and getattr(resp, "status_code", None):
            det += f" (HTTP {resp.status_code} en el handshake)"
        if RES.get("ws", {}).get("ok"):
            cerrado = det
            _p(f"       conexión cortada: {det}")
        else:
            _paso("ws", False, det, (time.perf_counter() - t0) * 1000)
            return {"handshake": False, "error": det}

    total = sum(conteo.values())
    _p("       Md por símbolo:")
    for s in simbolos:
        md = MD.get(s) or {}
        la = (md.get("LA") or {}).get("price") if isinstance(md.get("LA"), dict) else None
        bi = md.get("BI"); of = md.get("OF")
        bi = bi[0].get("price") if isinstance(bi, list) and bi else None
        of = of[0].get("price") if isinstance(of, list) and of else None
        _p(f"         {s:<34} {conteo.get(s, 0):>4} Md   last={la}  bid={bi}  offer={of}")
    extra = [s for s in conteo if s not in simbolos]
    if extra:
        _p(f"       (también llegaron Md de {len(extra)} símbolo(s) no pedidos: {extra[:5]})")
    res = {"handshake": True, "md_total": total, "conteo": conteo, "errores": errores, "cerrado": cerrado}
    RES["ws_md"] = {"ok": total > 0, "detalle": f"{total} Md en {segundos:.0f} s · {len(errores)} error(es) del broker"
                    + (f" · se cortó: {cerrado}" if cerrado else ""), "ms": None, **res}
    _p(f"[{'OK   ' if total > 0 else '----'}] {'ws_md':<12} {RES['ws_md']['detalle']}")
    return res


# ── diagnóstico ──────────────────────────────────────────────────────────────
def diagnostico(res: Dict[str, Dict[str, Any]], en_rueda: Optional[bool] = None) -> List[str]:
    """Lee RES y devuelve líneas con la causa probable. Pura (testeable)."""
    out: List[str] = []
    g = lambda k: res.get(k, {})  # noqa: E731
    if g("dns").get("ok") is False:
        out.append("El host no resuelve: sin red, DNS de la empresa bloqueando el dominio, o proxy "
                   "obligatorio. Probar `nslookup` del host y abrir la URL en el navegador de esa PC.")
        return out
    if g("tcp").get("ok") is False:
        out.append("Resuelve pero el puerto 443 no abre: firewall / proxy corporativo cortando la salida "
                   "directa. Si el navegador SÍ abre la URL, esa PC sale por un proxy que Python no usa: "
                   "pedir a IT que permita el host, o setear HTTPS_PROXY (el WS igual necesita salida directa).")
        return out
    if g("tls").get("ok") is False:
        out.append("TCP abre pero el TLS falla: inspección SSL del proxy (certificado propio de la empresa) "
                   "o reloj de la PC desfasado. Revisar fecha/hora y si IT hace intercepción TLS.")
        return out
    st = g("http").get("status")
    if g("http").get("ok") is False or st in (403, 429):
        out.append(f"El broker responde HTTP {st}: WAF / IP bloqueada / rate limit del lado del broker, o un "
                   "proxy que responde en su lugar. Comparar con otra PC de la misma red y con el celular.")
        return out
    if g("login").get("ok") is False:
        err = (g("login").get("error") or "").lower()
        if "rechazad" in err or "redirect" in err:
            out.append("El broker recibió el POST y contestó que usuario o clave son INCORRECTOS (302 a "
                       "login.html?error=true: así lo dice Spring, no manda 401/403). No es red ni proxy. "
                       "Causas: clave vencida o cambiada, usuario bloqueado por intentos, credenciales de "
                       "OTRO broker en secrets.txt, o la clave llegó cambiada desde el archivo (ver el paso "
                       "'credenciales'). Probá entrar con el mismo usuario/clave en la web del broker "
                       "(login.html) y, si ahí entra, en el interactivo: login(HOST, 'usuario', 'clave tipeada').")
            if g("credenciales").get("ok") is False:
                out.append("El paso 'credenciales' marcó avisos: lo más probable es que la clave en uso no "
                           "sea la que está escrita en secrets.txt.")
        else:
            out.append(f"El login no llegó a completarse: {g('login').get('error')}. Suele ser timeout / "
                       "proxy (los pasos anteriores pasaron, así que es específico del POST).")
        return out
    if g("rest").get("ok") is False:
        out.append("Login OK pero el REST autenticado falla: la cookie no se está mandando o el usuario no "
                   "tiene permisos de cuenta. Mirar el detalle (un redirect a login.html = sesión no aceptada).")
    if g("ws").get("ok") is False:
        det = (g("ws").get("detalle") or "")
        if "HTTP 4" in det or "InvalidStatus" in det:
            out.append("Login OK pero el handshake del WS vuelve 4xx: el broker no acepta la cookie en el WS "
                       "(sesión de otro nodo / cookie de nombre distinto) o un proxy no deja pasar Upgrade. "
                       "Ver en /conexion de la app si pasa lo mismo tras Reconectar.")
        elif "timeout" in det.lower():
            out.append("El handshake del WS no contesta: proxy / firewall que corta WebSockets (el REST pasa, "
                       "el wss no). Pedir a IT que permita WebSocket hacia el host.")
        else:
            out.append(f"El WS no conectó: {det}")
        return out
    ws = g("ws_md")
    if ws:
        if ws.get("cerrado"):
            out.append(f"Conectó pero el broker cortó el socket: {ws.get('cerrado')}. Si es 'keepalive' o "
                       "'1006', hay un equipo de red cortando conexiones ociosas; si es 1000/1001, el broker "
                       "invalidó la sesión (otra sesión del mismo usuario abierta?).")
        if ws.get("errores"):
            out.append("El broker respondió ERROR al smd: " + " | ".join(ws["errores"][:3]) +
                       ". Si TODOS los símbolos dan error, es la sesión / permisos de market data de ese "
                       "usuario (no los símbolos): revisar con el broker qué tiene habilitado la cuenta.")
        if ws.get("md_total", 0) == 0 and not ws.get("errores") and not ws.get("cerrado"):
            if en_rueda is False:
                out.append("Conectó y no llegó market data, pero es fuera de rueda: normal. Repetir en horario "
                           "de mercado (11 a 17 BA).")
            else:
                out.append("Conectó, el smd no dio error y NO llegó ningún Md en rueda: la cuenta no tiene "
                           "market data habilitado en ese broker, o los símbolos no existen en su listado. "
                           "Probar con otros símbolos (escuchar([...], 30)) y consultar al broker.")
        if ws.get("md_total", 0) > 0 and not ws.get("cerrado"):
            out.append("Todo funciona desde esta PC con estas credenciales. Si la app igual muestra 'feed "
                       "caído', el problema está en la app (ver /conexion y /market/diag), no en la red.")
    return out


def _en_rueda() -> Optional[bool]:
    """Lunes a viernes, 10 a 18 hora BA (aprox.: sólo para leer un 0 Md)."""
    try:
        from zoneinfo import ZoneInfo
        h = datetime.now(ZoneInfo("America/Argentina/Buenos_Aires"))
    except Exception:  # noqa: BLE001 — sin tzdata (Windows sin el paquete)
        return None
    return h.weekday() < 5 and 10 <= h.hour < 18


# ── orquestación ─────────────────────────────────────────────────────────────
async def correr(host: str = HOST, usuario: str = "", clave: str = "",
                 simbolos: Optional[List[str]] = None, escuchar_s: float = ESCUCHAR_S) -> Dict[str, Dict[str, Any]]:
    RES.clear()
    simbolos = list(simbolos if simbolos is not None else SIMBOLOS)
    host = host.strip().rstrip("/") + "/"
    _p("=" * 78)
    _p(f"probar_conexion · {datetime.now():%d/%m/%Y %H:%M:%S}")
    _p("=" * 78)
    paso_entorno(host)
    if not usuario or not clave:
        u, c = _cred()
        usuario, clave = usuario or u, clave or c
    _p("-" * 78)
    if paso_dns(host) is None:
        return _cerrar()
    if not paso_tcp(host):
        return _cerrar()
    if not paso_tls(host):
        return _cerrar()
    await paso_http(host)
    paso_credenciales(usuario, clave)
    cli = await paso_login(host, usuario, clave)
    if cli is None:
        return _cerrar()
    try:
        await paso_rest(cli)
        await paso_ws(cli, simbolos, escuchar_s)
    finally:
        try:
            if cli._http is not None:
                await cli._http.aclose()
        except Exception:  # noqa: BLE001
            pass
    return _cerrar()


def _cerrar() -> Dict[str, Dict[str, Any]]:
    _p("-" * 78)
    _p("DIAGNÓSTICO")
    for linea in diagnostico(RES, _en_rueda()) or ["sin conclusión (mirá los pasos de arriba)"]:
        _p(f"  • {linea}")
    if LOG:
        _p(f"\nLog completo: {LOG}")
    return RES


# ── helpers para el interactivo ──────────────────────────────────────────────
def probar(**kw: Any) -> Dict[str, Dict[str, Any]]:
    """Vuelve a correr todo. probar(host="https://api.lbo.xoms.com.ar/")"""
    return asyncio.run(correr(**kw))


def login(host: str = HOST, usuario: str = "", clave: str = ""):
    """Sólo el login contra `host`; devuelve el PrimaryWS logueado (o None)."""
    if not usuario or not clave:
        u, c = _cred()
        usuario, clave = usuario or u, clave or c
    return asyncio.run(paso_login(host.strip().rstrip("/") + "/", usuario, clave))


def escuchar(simbolos: List[str], segundos: float = 30, host: str = HOST) -> Dict[str, Any]:
    """Sólo el paso WS con otros símbolos: escuchar(["MERV - XMEV - YPFD - 24hs"], 30)"""
    async def _go() -> Dict[str, Any]:
        u, c = _cred()
        cli = await paso_login(host.strip().rstrip("/") + "/", u, c)
        if cli is None:
            return {"handshake": False, "error": "login"}
        try:
            return await paso_ws(cli, list(simbolos), segundos)
        finally:
            if cli._http is not None:
                await cli._http.aclose()
    return asyncio.run(_go())


if __name__ == "__main__":
    _abrir_log()
    try:
        asyncio.run(correr())
    except KeyboardInterrupt:
        _p("\n(cortado con Ctrl+C)")
    if sys.flags.interactive:
        _p("\nInteractivo: RES · MD · NO_MD · LOG · probar() · escuchar([...], 30) · login(host, usuario, clave)")
