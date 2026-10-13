"""Noticias (services/news): parser RSS / Atom / Google News, GET condicional
con gzip, URLs alternativas por fuente con backoff, round-robin entre fuentes
y la marquesina con duración proporcional a los titulares."""
from __future__ import annotations

import gzip
import io
import urllib.error
from typing import Dict, List

import pytest

from backend.services import news

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>Bonos: el riesgo pa\xc3\xads baja</title><link>https://a/1</link></item>
<item><title>El d\xc3\xb3lar cerr\xc3\xb3 estable</title><link>https://a/2</link></item>
<item><title>Tercera nota</title><link>https://a/3</link></item>
</channel></rss>"""
ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>f</title>
<entry><title>Atom uno</title><link href="https://b/1"/></entry>
<entry><title>Atom dos</title><link href="https://b/2"/></entry></feed>"""
GNEWS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>g</title>
<item><title>Argentina coloca deuda - Reuters</title><link>https://news.google.com/x</link>
<source url="https://reuters.com">Reuters</source></item>
<item><title>Bonos: el riesgo pa\xc3\xads baja - \xc3\x81mbito</title><link>https://news.google.com/y</link>
<source url="https://ambito.com">\xc3\x81mbito</source></item>
</channel></rss>"""


def test_parse_rss_atom_y_google_news() -> None:
    rss = news._parse(RSS, "Ámbito", 2)
    assert [r["title"] for r in rss] == ["Bonos: el riesgo país baja", "El dólar cerró estable"]   # tope máx
    assert rss[0]["link"] == "https://a/1" and rss[0]["source"] == "Ámbito"
    atom = news._parse(ATOM, "X", 5)
    assert [a["title"] for a in atom] == ["Atom uno", "Atom dos"] and atom[1]["link"] == "https://b/2"
    g = news._parse(GNEWS, "Google News", 5)
    assert g[0] == {"title": "Argentina coloca deuda", "link": "https://news.google.com/x", "source": "Reuters"}
    assert g[1]["source"] == "Ámbito" and g[1]["title"] == "Bonos: el riesgo país baja"   # sin el " - Fuente"


class _Resp:
    def __init__(self, body: bytes, headers: Dict[str, str]):
        self._b, self.headers, self.status = body, headers, 200

    def read(self, n: int = -1) -> bytes:
        return self._b if n < 0 else self._b[:n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake_urlopen(plan: Dict[str, List], vistos: List):
    """plan[url] = lista de respuestas (bytes gzip / HTTPError / Exception) que
    se consumen en orden; la última se repite. Registra los headers enviados."""
    def urlopen(req, timeout=None, context=None):
        url = req.full_url
        vistos.append((url, dict(req.header_items())))
        cola = plan.get(url)
        if not cola:
            raise urllib.error.URLError("no existe (sintético)")
        r = cola.pop(0) if len(cola) > 1 else cola[0]
        if isinstance(r, BaseException):
            raise r
        return r
    return urlopen


def _http(code: int, url: str = "https://x") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url, code, "x", {}, io.BytesIO(b""))


@pytest.fixture()
def feeds(monkeypatch):
    """Tres fuentes sintéticas: A (RSS), B (alternativas) y G (Google News)."""
    news.reset()
    monkeypatch.setattr(news, "_FEEDS", [
        ("A", ["https://a/rss"], 3),
        ("B", ["https://b/vieja", "https://b/nueva"], 2),
        ("G", ["https://g/rss"], 5),
    ])
    yield
    news.reset()


def test_get_condicional_gzip_backoff_y_round_robin(feeds, monkeypatch) -> None:
    vistos: List = []
    gz = gzip.compress(RSS)
    plan = {
        "https://a/rss": [_Resp(gz, {"Content-Encoding": "gzip", "ETag": '"e1"', "Last-Modified": "Thu, 09 Oct 2026 12:00:00 GMT"}),
                          _http(304)],                                   # 2º ciclo: sin novedades
        "https://b/vieja": [_http(404)],                                 # la URL vieja murió…
        "https://b/nueva": [_Resp(ATOM, {})],                            # …la alternativa responde
        "https://g/rss": [_Resp(GNEWS, {})],
    }
    monkeypatch.setattr(news.urllib.request, "urlopen", _fake_urlopen(plan, vistos))

    news._refresh()
    st = {f["fuente"]: f for f in news.status()["fuentes"]}
    assert st["A"]["status"] == "ok" and st["A"]["items"] == 3 and st["A"]["bytes"] == len(gz)   # bytes del cable (gzip)
    assert st["B"]["status"] == "ok" and st["B"]["url"] == "https://b/nueva"                  # alternativa fijada
    assert st["G"]["status"] == "ok"
    its = news.items()
    # round-robin entre fuentes (A, B, G, A, B, G…) y dedup: la nota de Ámbito repetida en Google News no entra dos veces
    assert [i["source"] for i in its[:4]] == ["A", "B", "Reuters", "A"]
    assert sum(1 for i in its if i["title"] == "Bonos: el riesgo país baja") == 1
    assert len(its) == 3 + 2 + 2 - 1

    # 2º ciclo: A manda If-None-Match / If-Modified-Since y recibe 304 → conserva sus 3 titulares, 0 bytes;
    # B arranca directo por la URL que quedó fija (no vuelve a pegarle a la vieja).
    vistos.clear()
    news._refresh()
    hdr_a = next(h for u, h in vistos if u == "https://a/rss")
    assert hdr_a.get("If-none-match") == '"e1"' and hdr_a.get("If-modified-since", "").startswith("Thu")
    assert hdr_a.get("Accept-encoding") == "gzip" and "Chrome" in hdr_a.get("User-agent", "")
    assert [u for u, _ in vistos if u.startswith("https://b/")] == ["https://b/nueva"]
    st = {f["fuente"]: f for f in news.status()["fuentes"]}
    assert st["A"]["status"] == "304" and st["A"]["items"] == 3 and st["A"]["bytes"] == 0
    assert len(news.items()) == 6

    # 3º ciclo: B se cae del todo → backoff (2 ciclos, después 4, 8, 16) conservando su último lote
    plan["https://b/nueva"] = [_http(503)]
    plan["https://b/vieja"] = [_http(404)]
    vistos.clear()
    news._refresh()
    st = {f["fuente"]: f for f in news.status()["fuentes"]}
    assert st["B"]["status"] == "HTTP 503" and st["B"]["fallos"] == 1 and st["B"]["items"] == 2
    assert news._estado["B"]["skip_hasta"] == news._ciclo + 2
    vistos.clear()
    news._refresh()                                                      # en backoff: ni se pide
    assert not [u for u, _ in vistos if u.startswith("https://b/")]
    assert any(i["source"] == "B" for i in news.items())                 # y sigue en la marquesina


def test_feed_gigante_o_sin_items_no_entra(feeds, monkeypatch) -> None:
    vistos: List = []
    plan = {
        "https://a/rss": [_Resp(b"x" * (news._MAX_BYTES + 5), {})],
        "https://b/vieja": [_Resp(b"<rss><channel></channel></rss>", {})],
        "https://b/nueva": [_Resp(b"<rss><channel></channel></rss>", {})],
        "https://g/rss": [_Resp(b"no es xml", {})],
    }
    monkeypatch.setattr(news.urllib.request, "urlopen", _fake_urlopen(plan, vistos))
    news._refresh()
    st = {f["fuente"]: f for f in news.status()["fuentes"]}
    assert st["A"]["status"].startswith("ValueError") and "KB" in st["A"]["status"]
    assert st["B"]["status"].startswith("ValueError: sin ítems")
    assert st["G"]["status"] == "XML inválido"
    assert news.items() == []


@pytest.mark.asyncio
async def test_marquesina_mas_lenta_con_mas_titulares(monkeypatch) -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    monkeypatch.setattr(news, "_items", [{"title": f"Nota {i}", "link": "https://x", "source": "S"} for i in range(30)])
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get("/news/marquee")
        assert r.status_code == 200 and 'animation-duration:180s' in r.text         # 6 s × 30
        assert r.text.count('class="news-item"') == 60                               # duplicado para el loop
        monkeypatch.setattr(news, "_items", [{"title": "Una", "link": "https://x", "source": "S"}] * 5)
        r = await ac.get("/news/marquee?v=2")
        assert 'animation-duration:90s' in r.text                                    # piso
        monkeypatch.setattr(news, "_items", [])
        r = await ac.get("/news/marquee?v=3")
        assert r.status_code == 200 and "news-track" not in r.text                   # sin titulares, vacía
