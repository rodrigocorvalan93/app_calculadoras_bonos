"""Pulido UX (sept. 2026): timestamps legibles (last @ / blotter), copy de
las páginas en vivo, toast de errores htmx y foco visible."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from backend.locale_ar import TZ_BA, fmt_hora, fmt_ts

ROOT = Path(__file__).resolve().parent.parent


def test_ar_ts_y_ar_hora_aceptan_epoch_e_iso() -> None:
    hoy = datetime.now(TZ_BA).replace(hour=15, minute=30, second=12, microsecond=0)
    ms = str(int(hoy.timestamp() * 1000))
    assert fmt_ts(ms) == hoy.strftime("%d/%m %H:%M:%S")
    assert fmt_hora(ms) == "15:30:12"                                  # hoy → sólo la hora
    assert fmt_hora(int(hoy.timestamp())) == "15:30:12"                # epoch en segundos
    iso = hoy.replace(tzinfo=None).isoformat(timespec="seconds")       # como el audit del OMS
    assert fmt_ts(iso) == hoy.strftime("%d/%m %H:%M:%S") and fmt_hora(iso) == "15:30:12"
    ayer = hoy - timedelta(days=1)
    assert fmt_hora(ayer.replace(tzinfo=None).isoformat(timespec="seconds")) == ayer.strftime("%d/%m %H:%M")
    assert fmt_hora("") == "—" and fmt_hora(None) == "—" and fmt_hora("basura") == "basura"
    assert fmt_ts("2026-09-15T23:08:22.123456") == "15/09 23:08:22"


@pytest.mark.asyncio
async def test_last_at_y_blotter_legibles(tmp_path, monkeypatch) -> None:
    from backend.main import app
    from backend.services import marketdata_store as mds, oms, symbols as syms

    hoy = datetime.now(TZ_BA).replace(hour=15, minute=30, second=12, microsecond=0)
    ms = str(int(hoy.timestamp() * 1000))
    mds.get_store().update_from_md(syms.md_symbol("TX26", "24hs"),
                                   {"LA": {"price": 182.4, "size": 1000, "date": ms}})
    monkeypatch.setattr(oms, "_AUDIT_PATH", tmp_path / "audit.jsonl")
    monkeypatch.setattr(oms, "_tail_cache", None)
    oms.audit("paper_enviada", {"code": "AL30", "side": "buy", "qty": 100, "price": 100.0,
                                "account": "C1", "ordtype": "limit", "client_order_id": "calc-1"})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        y = (await ac.get("/yas/market?code=TX26&plazo=24hs")).text
        assert "last @ 15:30:12" in y and ("last @ " + ms) not in y     # antes: el epoch crudo
        b = (await ac.get("/ordenes/blotter")).text
        # HH:MM:SS en la celda (no el ISO con T) y el ISO completo en el title
        assert re.search(r'title="\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"[^>]*>\d{2}:\d{2}:\d{2}<', b), b[:600]


def test_copy_en_vivo_y_assets() -> None:
    tpl = ROOT / "backend" / "templates"
    for f in ("curves.html", "mercado.html", "graficos.html", "forwards.html"):
        t = (tpl / f).read_text(encoding="utf-8")
        assert "Refresh cada 5 s" not in t and "Refresh 5 s" not in t, f
        assert "En vivo" in t, f
    js = (ROOT / "backend" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert "htmx:responseError" in js and "htmx:sendError" in js and "/market/seq" in js
    css = (ROOT / "backend" / "static" / "css" / "style.css").read_text(encoding="utf-8")
    assert ".toast.show" in css and "button:focus-visible" in css
