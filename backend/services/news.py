"""Noticias — RSS de medios financieros (como OMSnews del legacy), sin deps.

Poller en thread daemon cada `_INTERVAL` s (mismo patrón que MAE/SIOPEL):
baja los feeds con urllib + xml.etree (feedparser no está instalado y NO
agregamos dependencias), dedupea por título y cachea. El path de request
sólo lee la lista en memoria → costo ~0. Sin red (sandbox/offline) degrada
a lista vacía y la marquesina no se muestra.
"""
from __future__ import annotations

import logging
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# (nombre, url, máx ítems) — prioridad Argentina primero (orden de la lista).
_FEEDS = [
    ("Ámbito", "https://www.ambito.com/rss/economia.xml", 6),
    ("Ámbito Fin.", "https://www.ambito.com/rss/finanzas.xml", 5),
    ("Cronista", "https://www.cronista.com/files/rss/feed_finanzas.xml", 5),
    ("Infobae", "https://www.infobae.com/feeds/rss/economia/", 4),
    ("Bloomberg Línea", "https://www.bloomberglinea.com/arc/outboundfeeds/rss/?outputType=xml&_website=bloomberglinea", 5),
]
_INTERVAL = 120.0
_TIMEOUT = 6.0

_lock = threading.Lock()
_items: List[Dict[str, Any]] = []
_started = False


def _parse(xml_bytes: bytes, source: str, max_items: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    root = ET.fromstring(xml_bytes)
    # RSS 2.0: rss>channel>item · Atom: feed>entry (con namespace).
    nodes = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
    for n in nodes[:max_items]:
        title = (n.findtext("title") or n.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
        link = (n.findtext("link") or "").strip()
        if not link:   # Atom: <link href="…"/>
            ln = n.find("{http://www.w3.org/2005/Atom}link")
            link = (ln.get("href") if ln is not None else "") or ""
        if title:
            out.append({"title": title, "link": link, "source": source})
    return out


def _refresh() -> None:
    global _items
    fresh: List[Dict[str, Any]] = []
    seen: set = set()
    for source, url, mx in _FEEDS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (news-tape)"})
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
                for it in _parse(r.read(), source, mx):
                    key = it["title"][:60].lower()
                    if key not in seen:
                        seen.add(key)
                        fresh.append(it)
        except Exception:  # noqa: BLE001 — un feed caído no voltea el resto
            continue
    with _lock:
        if fresh:
            # Un feed caído ESTE ciclo no debe vaciar su parte del ticker: conservamos
            # los titulares viejos de fuentes que no respondieron (dedup + acotado).
            ok = {it["source"] for it in fresh}
            kept = [it for it in _items
                    if it.get("source") not in ok and it["title"][:60].lower() not in seen]
            _items = (fresh + kept)[:60]
        elif not _items:
            _items = fresh
    if fresh:
        logger.info("[news] %d titulares", len(fresh))


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


def items(max_items: int = 24) -> List[Dict[str, Any]]:
    with _lock:
        return list(_items[:max_items])
