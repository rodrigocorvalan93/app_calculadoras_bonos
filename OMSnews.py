# -*- coding: utf-8 -*-
"""OMSnews.py

News Feed asíncrono para la marquesina de noticias financieras.

Fuentes (RSS gratuitos, sin API key):
  Argentina:  Ámbito (finanzas+economía), El Cronista, Infobae Eco,
              iProfesional (finanzas), El Economista AR (finanzas)
  LATAM:      Bloomberg Línea (tag Argentina, vía Atom/RSS)
  Global:     Investing.com (ES), CNBC Business, WSJ Markets

Bloomberg.com no tiene RSS público; Bloomberg Línea LATAM sí (Atom).

Prioridad geográfica: 1=Argentina, 2=LATAM, 3=USA/Global.
Thread daemon de background, refresh cada N segundos.
"""

from __future__ import annotations

import threading
import time
import html
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime

import feedparser


# ──────────────────────────────────────────────────────────────────────
# Feeds
# ──────────────────────────────────────────────────────────────────────

@dataclass
class FeedSource:
    name: str
    url: str
    priority: int  # 1=ARG, 2=LATAM, 3=Global
    max_items: int = 5


FEED_SOURCES: List[FeedSource] = [
    # ── Argentina (prioridad 1) ──
    FeedSource("Ámbito",       "https://www.ambito.com/rss/economia.xml",              priority=1, max_items=6),
    FeedSource("Ámbito Fin",   "https://www.ambito.com/rss/finanzas.xml",              priority=1, max_items=5),
    FeedSource("Cronista",     "https://www.cronista.com/files/rss/feed_finanzas.xml",  priority=1, max_items=5),
    FeedSource("Infobae Eco",  "https://www.infobae.com/feeds/rss/economia/",           priority=1, max_items=4),
    FeedSource("iProfesional", "https://www.iprofesional.com/adjuntos/html/RSS/finanzas.xml", priority=1, max_items=4),
    FeedSource("El Economista","https://eleconomista.com.ar/finanzas/feed/",            priority=1, max_items=4),
    # ── LATAM (prioridad 2) ──
    FeedSource("BL Argentina", "https://www.bloomberglinea.com/arc/outboundfeeds/rss/?outputType=xml&_website=bloomberglinea", priority=2, max_items=5),
    # ── Global (prioridad 3) ──
    FeedSource("Investing ES", "https://es.investing.com/rss/news.rss",                priority=3, max_items=4),
    FeedSource("CNBC Biz",     "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10001147", priority=3, max_items=4),
    FeedSource("WSJ Markets",  "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",        priority=3, max_items=4),
]


# ──────────────────────────────────────────────────────────────────────
# Modelo
# ──────────────────────────────────────────────────────────────────────

@dataclass
class NewsItem:
    title: str
    link: str
    source: str
    priority: int
    published: Optional[datetime] = None

    @property
    def display_title(self) -> str:
        return html.unescape(self.title).strip()


# ──────────────────────────────────────────────────────────────────────
# Cache thread-safe
# ──────────────────────────────────────────────────────────────────────

_news_lock = threading.Lock()
_news_cache: List[NewsItem] = []
_news_cache_ts: float = 0.0
_NEWS_TTL: int = 120

_bg_thread: Optional[threading.Thread] = None
_bg_running = False


def _parse_feed(source: FeedSource) -> List[NewsItem]:
    items = []
    try:
        feed = feedparser.parse(source.url)
        for entry in feed.entries[:source.max_items]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            if not title:
                continue
            pub = None
            pub_struct = entry.get("published_parsed") or entry.get("updated_parsed")
            if pub_struct:
                try:
                    pub = datetime(*pub_struct[:6])
                except Exception:
                    pass
            items.append(NewsItem(title=title, link=link, source=source.name,
                                  priority=source.priority, published=pub))
    except Exception:
        pass
    return items


def _refresh_news():
    global _news_cache, _news_cache_ts
    all_items: List[NewsItem] = []
    for src in FEED_SOURCES:
        all_items.extend(_parse_feed(src))

    # Dedup por título (primeros 60 chars)
    seen = set()
    unique = []
    for item in all_items:
        key = item.display_title[:60].lower()
        if key not in seen:
            seen.add(key)
            unique.append(item)

    def _sort_key(item: NewsItem):
        ts = item.published.timestamp() if item.published else 0
        return (item.priority, -ts)

    unique.sort(key=_sort_key)

    with _news_lock:
        _news_cache = unique
        _news_cache_ts = time.time()


def _bg_news_worker(interval: int):
    global _bg_running
    while _bg_running:
        try:
            _refresh_news()
        except Exception:
            pass
        time.sleep(interval)


def start_news_background(interval: int = 120):
    global _bg_thread, _bg_running
    if _bg_thread is not None and _bg_thread.is_alive():
        return
    _bg_running = True
    _bg_thread = threading.Thread(target=_bg_news_worker, args=(interval,), daemon=True)
    _bg_thread.start()


def stop_news_background():
    global _bg_running
    _bg_running = False


def get_news(max_items: int = 20, force_refresh: bool = False) -> List[NewsItem]:
    if force_refresh or not _news_cache or (time.time() - _news_cache_ts) > _NEWS_TTL:
        _refresh_news()
    with _news_lock:
        return list(_news_cache[:max_items])


# ──────────────────────────────────────────────────────────────────────
# HTML marquesina — adaptativa light/dark
# ──────────────────────────────────────────────────────────────────────

def news_marquee_html(
    items: Optional[List[NewsItem]] = None,
    max_items: int = 20,
    speed: int = 50,
    dark: bool = False,
) -> str:
    """Genera HTML de marquesina con noticias.

    Args:
        speed: segundos para una pasada completa (más alto = más lento).
        dark: True para estilo Bloomberg, False para light mode.
    """
    if items is None:
        items = get_news(max_items=max_items)
    if not items:
        return ""

    # Colores adaptativos
    if dark:
        bg = "linear-gradient(90deg, #0d1117 0%, #161b22 50%, #0d1117 100%)"
        border = "#30363d"
        badge_color = "#ff9800"
        link_color = "#e6e6e6"
    else:
        bg = "linear-gradient(90deg, #f0f2f6 0%, #ffffff 50%, #f0f2f6 100%)"
        border = "#d0d7de"
        badge_color = "#1a5276"
        link_color = "#1c1c1c"

    parts = []
    for item in items[:max_items]:
        src_badge = f'<span style="color:{badge_color};font-weight:700;">[{item.source}]</span>'
        link = f'<a href="{item.link}" target="_blank" style="color:{link_color};text-decoration:none;">{item.display_title}</a>'
        parts.append(f'{src_badge} {link}')

    separator = '&nbsp;&nbsp;•&nbsp;&nbsp;'
    ticker_text = separator.join(parts)

    return f"""
<div style="
    background: {bg};
    border-top: 1px solid {border};
    border-bottom: 1px solid {border};
    padding: 6px 0;
    overflow: hidden;
    white-space: nowrap;
    font-size: 12px;
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
">
    <div style="
        display: inline-block;
        animation: news_marquee {speed}s linear infinite;
        padding-left: 100%;
    ">
        {ticker_text}
    </div>
</div>
<style>
@keyframes news_marquee {{
    0%   {{ transform: translateX(0%); }}
    100% {{ transform: translateX(-100%); }}
}}
</style>
"""
