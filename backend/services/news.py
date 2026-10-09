"""Noticias — RSS de medios financieros (como OMSnews del legacy), sin deps.

Poller en thread daemon cada `_INTERVAL` s (mismo patrón que MAE/SIOPEL):
baja los feeds con urllib + xml.etree (feedparser no está instalado y NO
agregamos dependencias), dedupea por título y cachea. El path de request
sólo lee la lista en memoria → costo ~0. Sin red (sandbox/offline) degrada
a lista vacía y la marquesina no se muestra.

Eficiencia de datos (09/10 — el desk veía sólo Ámbito y Bloomberg Línea):
  · GET condicional (`If-None-Match` / `If-Modified-Since`): un feed sin
    novedades responde 304 y cero bytes; sus titulares anteriores se conservan.
  · `Accept-Encoding: gzip` (un RSS de 150 KB viaja en ~20 KB) y tope de
    `_MAX_BYTES` por respuesta.
  · User-Agent de navegador real: los CDN de varios medios (Arc/Akamai)
    devuelven 403 a un UA "raro" — era lo que callaba a Infobae/Cronista.
  · URLs alternativas por fuente (las rutas de RSS cambian): la primera que
    responde queda fija; una fuente caída entra en backoff exponencial
    (2, 4, 8, 16 ciclos) en vez de pegarle cada 2 min.
  · Google News (búsqueda del mercado local, `when:1d`) = UN pedido que
    agrega Reuters, Bloomberg, Cronista…; la fuente real de cada ítem viene
    en `<source>` y el título pierde el sufijo " - Fuente".
`status()` dice qué fuente responde, con qué URL, cuántos ítems y bytes — y
el log deja una línea cuando cambia el estado de alguna fuente.
"""
from __future__ import annotations

import gzip
import logging
import threading
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# (fuente, URLs alternativas — la primera que responda queda fija —, máx ítems).
# Prioridad Argentina primero (orden de la lista); internacionales al final.
_FEEDS: List[Tuple[str, List[str], int]] = [
    ("Ámbito", ["https://www.ambito.com/rss/economia.xml"], 6),
    ("Ámbito Fin.", ["https://www.ambito.com/rss/finanzas.xml"], 5),
    ("Cronista", ["https://www.cronista.com/files/rss/feed_finanzas.xml",
                  "https://www.cronista.com/rss/finanzas-mercados/",
                  "https://www.cronista.com/rss/"], 5),
    ("Infobae", ["https://www.infobae.com/feeds/rss/economia/",
                 "https://www.infobae.com/arc/outboundfeeds/rss/category/economia/?outputType=xml",
                 "https://www.infobae.com/feeds/rss/"], 4),
    ("Bloomberg Línea", ["https://www.bloomberglinea.com/arc/outboundfeeds/rss/?outputType=xml&_website=bloomberglinea"], 5),
    ("La Nación", ["https://www.lanacion.com.ar/arc/outboundfeeds/rss/category/economia/?outputType=xml",
                   "https://www.lanacion.com.ar/arcio/rss/category/economia/"], 4),
    ("Clarín", ["https://www.clarin.com/rss/economia/"], 4),
    ("iProfesional", ["https://www.iprofesional.com/rss/finanzas",
                      "https://www.iprofesional.com/rss"], 4),
    ("Perfil", ["https://www.perfil.com/feed/economia"], 3),
    ("Página/12", ["https://www.pagina12.com.ar/rss/secciones/economia/notas"], 3),
    # Un solo pedido que agrega muchos medios sobre el mercado local; la
    # fuente real de cada ítem viene en <source>.
    ("Google News", ["https://news.google.com/rss/search?q=(bonos+OR+merval+OR+d%C3%B3lar+OR+BCRA+OR+"
                     "%22riesgo+pa%C3%ADs%22)+when:1d&hl=es-419&gl=AR&ceid=AR:es-419"], 8),
    ("Yahoo Finance", ["https://finance.yahoo.com/news/rssindex"], 3),
    ("CNBC", ["https://www.cnbc.com/id/100003114/device/rss/rss.html"], 3),
    ("MarketWatch", ["https://feeds.content.dowjones.io/public/rss/mw_topstories"], 3),
]
_INTERVAL = 120.0
_TIMEOUT = 6.0
_MAX_BYTES = 1_000_000            # por respuesta (un RSS normal pesa 20-200 KB)
_MAX_ITEMS = 60                   # titulares en memoria
_BACKOFF_MAX = 16                 # ciclos (≈ 32 min) entre reintentos de una fuente caída
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
_ATOM = "{http://www.w3.org/2005/Atom}"

_lock = threading.Lock()
_items: List[Dict[str, Any]] = []
_por_fuente: Dict[str, List[Dict[str, Any]]] = {}   # último lote bueno por fuente
_estado: Dict[str, Dict[str, Any]] = {}             # diagnóstico por fuente (status())
_ciclo = 0
_started = False
_ultima_firma = ""


def _texto(n: Any, tag: str) -> str:
    return (n.findtext(tag) or n.findtext(_ATOM + tag) or "").strip()


def _parse(xml_bytes: bytes, source: str, max_items: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    root = ET.fromstring(xml_bytes)
    # RSS 2.0: rss>channel>item · Atom: feed>entry (con namespace).
    nodes = root.findall(".//item") or root.findall(f".//{_ATOM}entry")
    for n in nodes[:max_items]:
        title = _texto(n, "title")
        link = (n.findtext("link") or "").strip()
        if not link:   # Atom: <link href="…"/>
            ln = n.find(_ATOM + "link")
            link = (ln.get("href") if ln is not None else "") or ""
        src = source
        # Google News (y otros agregadores): <source>Reuters</source> y el
        # título termina en " - Reuters" → se muestra la fuente real.
        s = n.find("source")
        real = (s.text or "").strip() if s is not None else ""
        if real:
            src = real
            if title.endswith(" - " + real):
                title = title[: -len(real) - 3].rstrip()
        if title:
            out.append({"title": title, "link": link, "source": src})
    return out


def _ssl_ctx():
    try:
        import ssl

        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001
        return None


def _fetch(url: str, etag: Optional[str] = None,
           last_modified: Optional[str] = None) -> Tuple[int, Optional[bytes], Optional[str], Optional[str], int]:
    """GET condicional + gzip → (status, cuerpo, etag, last_modified, bytes en
    el cable). 304 = sin novedades (cuerpo None, cero bytes). Cualquier otro
    error sube (lo maneja _refresh por fuente)."""
    headers = {
        "User-Agent": _UA,
        "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5",
        "Accept-Encoding": "gzip",
    }
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    req = urllib.request.Request(url, headers=headers)
    try:
        # certifi: el Python de python.org en macOS no trae CAs (ver primary_ws)
        with urllib.request.urlopen(req, timeout=_TIMEOUT, context=_ssl_ctx()) as r:
            raw = r.read(_MAX_BYTES + 1)
            if len(raw) > _MAX_BYTES:
                raise ValueError(f"feed de más de {_MAX_BYTES // 1000} KB")
            cable = len(raw)
            if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
                raw = gzip.decompress(raw)
            return 200, raw, r.headers.get("ETag"), r.headers.get("Last-Modified"), cable
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            return 304, None, etag, last_modified, 0
        raise


def _motivo(exc: Optional[BaseException]) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code}"
    if isinstance(exc, urllib.error.URLError):
        return f"red: {str(exc.reason)[:60]}"
    if isinstance(exc, ET.ParseError):
        return "XML inválido"
    if exc is None:
        return "sin respuesta"
    return f"{type(exc).__name__}: {str(exc)[:60]}"


def _estado_de(source: str) -> Dict[str, Any]:
    return _estado.setdefault(source, {"url": None, "etag": None, "lm": None, "fallos": 0,
                                       "skip_hasta": 0, "status": "pendiente", "items": 0,
                                       "bytes": 0, "at": None})


def _refresh() -> None:
    """Un ciclo: cada fuente (salvo las que están en backoff) se pide con GET
    condicional; con 304 conserva su último lote; si la URL fija falla se
    prueban las alternativas; si nada responde, backoff exponencial. Al final
    se arma la lista: round-robin entre fuentes (primero el titular más nuevo
    de cada una, después el segundo…) para que la marquesina muestre
    variedad y no sólo las primeras de la lista, con dedup por título."""
    global _items, _ciclo, _ultima_firma
    _ciclo += 1
    nuevos: Dict[str, List[Dict[str, Any]]] = {}
    for source, urls, mx in _FEEDS:
        st = _estado_de(source)
        if _ciclo < st["skip_hasta"]:
            continue
        candidatas = ([st["url"]] + [u for u in urls if u != st["url"]]) if st["url"] else list(urls)
        ok, err = False, None
        for url in candidatas:
            try:
                etag, lm = (st["etag"], st["lm"]) if url == st["url"] else (None, None)
                status, data, etag2, lm2, cable = _fetch(url, etag, lm)
                if status == 304:
                    st.update(status="304", at=time.time(), bytes=0, fallos=0, skip_hasta=0)
                    ok = True
                    break
                its = _parse(data or b"", source, mx)
                if not its:
                    raise ValueError("sin ítems")
                nuevos[source] = its
                st.update(url=url, etag=etag2, lm=lm2, status="ok", items=len(its), bytes=cable,
                          at=time.time(), fallos=0, skip_hasta=0)
                ok = True
                break
            except Exception as exc:  # noqa: BLE001 — un feed caído no voltea el resto
                if err is None:
                    err = exc                       # el motivo que se reporta es el de la URL fija / principal
                continue
        if not ok:
            st["fallos"] += 1
            st["skip_hasta"] = _ciclo + min(2 ** st["fallos"], _BACKOFF_MAX)
            st.update(status=_motivo(err), at=time.time(), bytes=0)
    with _lock:
        for source, its in nuevos.items():
            _por_fuente[source] = its
        # Round-robin por prioridad + dedup por título (una misma noticia en dos
        # medios, o la de Google News repetida con la del medio).
        seen: set = set()
        merged: List[Dict[str, Any]] = []
        colas = [list(_por_fuente.get(source, [])) for source, _, _ in _FEEDS]
        while any(colas) and len(merged) < _MAX_ITEMS:
            for cola in colas:
                if not cola:
                    continue
                it = cola.pop(0)
                key = it["title"][:60].lower()
                if key in seen:
                    continue
                seen.add(key)
                merged.append(it)
        _items = merged
        total = len(merged)
        firma = "|".join(f"{s}:{_estado[s]['status']}" for s, _, _ in _FEEDS if s in _estado)
    if firma != _ultima_firma:
        _ultima_firma = firma
        ok_ = [s for s, _, _ in _FEEDS if _estado.get(s, {}).get("status") in ("ok", "304")]
        caidas = [f"{s} ({_estado[s]['status']})" for s, _, _ in _FEEDS
                  if s in _estado and _estado[s]["status"] not in ("ok", "304", "pendiente")]
        logger.info("[news] %d titulares · fuentes ok: %s · caídas: %s", total,
                    ", ".join(ok_) or "ninguna", ", ".join(caidas) or "ninguna")
    elif nuevos:
        logger.debug("[news] %d titulares (%d fuentes con novedades)", total, len(nuevos))


def _loop() -> None:
    while True:
        try:
            _refresh()
        except Exception:  # noqa: BLE001
            logger.exception("[news] refresh falló")
        time.sleep(_INTERVAL)


def start() -> None:
    """Arranca el poller (idempotente). Thread daemon: nunca bloquea requests."""
    global _started
    with _lock:
        if _started:
            return
        _started = True
    threading.Thread(target=_loop, name="news-poll", daemon=True).start()


def items(max_items: int = 30) -> List[Dict[str, Any]]:
    with _lock:
        return list(_items[:max_items])


def status() -> Dict[str, Any]:
    """Diagnóstico por fuente (qué responde, con qué URL, ítems, bytes del
    último pedido, fallos seguidos): para /admin y para saber en un vistazo
    por qué un medio no aparece en la marquesina."""
    with _lock:
        fuentes = []
        for source, urls, mx in _FEEDS:
            st = _estado.get(source) or {}
            fuentes.append({"fuente": source, "status": st.get("status", "pendiente"),
                            "url": st.get("url") or urls[0], "items": len(_por_fuente.get(source, [])),
                            "bytes": st.get("bytes", 0), "fallos": st.get("fallos", 0),
                            "at": st.get("at"), "max": mx})
        return {"items": len(_items), "ciclo": _ciclo, "intervalo_s": _INTERVAL, "fuentes": fuentes}


def reset() -> None:
    """Olvida titulares y estado (tests)."""
    global _items, _ciclo, _ultima_firma
    with _lock:
        _items = []
        _por_fuente.clear()
        _estado.clear()
        _ciclo = 0
        _ultima_firma = ""
