"""Batch operativo: mail de cierre (Qué pasó), watchdog del feed, campana de
alertas (superuser) y mini-histórico de la ficha YAS."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
from httpx import ASGITransport, AsyncClient

from backend.config import settings
from backend.services import auth, bond_universe, curves, historico_byma
from backend.services import alertas as alertas_svc, mailer, quepaso_report
from backend.services.watchdog import FeedWatchdog, en_rueda

_TZ = ZoneInfo("America/Argentina/Buenos_Aires")
_HOY = date.today() - timedelta(days=1)
_PREV = date.today() - timedelta(days=31)


def _client() -> AsyncClient:
    from backend.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


def _lecaps() -> list:
    bond_universe.ensure_loaded()
    td = date.today() + timedelta(days=90)
    out = []
    for c in curves.build_curve_codes().get("lecap") or []:
        o = bond_universe.get(c)
        v = getattr(o, "vencimiento", None)
        vd = v.date() if hasattr(v, "date") else v
        if vd and vd > td:
            out.append(c)
        if len(out) == 2:
            break
    if len(out) < 2:
        pytest.skip("sin 2 lecaps vivas para la fixture")
    return out


@pytest.fixture()
def base_sintetica(tmp_path, monkeypatch):
    monkeypatch.setenv("DELTA_HISTORICO_DIR", str(tmp_path))
    monkeypatch.delenv("DELTA_HISTORICO_PATH", raising=False)
    monkeypatch.delenv("DELTA_BASES_DIR", raising=False)
    c1, c2 = _lecaps()
    df = pd.DataFrame({
        "fecha_hoy": [_PREV, _PREV, _HOY, _HOY],
        "Código":    [c1, c2, c1, c2],
        "TIREA":     [0.34, 0.35, 0.30, 0.31],
        "TNA":       [0.29, 0.30, 0.26, 0.27],
        "TEM":       [0.0245, 0.0252, 0.0221, 0.0228],
        "Paridad":   [0.95, 0.94, 0.97, 0.96],
        "Last Price": [95.0, 90.0, 100.0, 94.5],
        "Duration":  [0.55, 0.90, 0.47, 0.82],
    })
    df.to_parquet(tmp_path / "Delta - historico_byma_px_tasas.parquet", index=False)
    historico_byma.refresh()
    yield {"c1": c1, "c2": c2}
    historico_byma._cache = None


# ── Mail de cierre ───────────────────────────────────────────────────────────
def test_default_recipient_prioridades(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "app_ops_mail_to", "ops@delta.com")
    assert mailer.default_recipient() == "ops@delta.com"
    # sin override → mail del superuser del store
    monkeypatch.setattr(settings, "app_ops_mail_to", "")
    monkeypatch.setattr(settings, "app_users_path", str(tmp_path / "u.json"))
    monkeypatch.setattr(settings, "app_superuser_email", "rodri@delta.com")
    auth.refresh()
    auth.ensure_bootstrapped()
    assert mailer.default_recipient() == "rodri@delta.com"
    auth.refresh()


def test_mail_de_cierre_con_adjuntos(base_sintetica, monkeypatch) -> None:
    sent = []
    monkeypatch.setattr(settings, "quepaso_mail", True)
    monkeypatch.setattr(mailer, "is_configured", lambda: True)
    monkeypatch.setattr(mailer, "default_recipient", lambda: "rodri@delta.com")
    monkeypatch.setattr(mailer, "send",
                        lambda to, s, b, attachments=None: (sent.append((to, s, b, attachments)) or (True, "ok")))
    r = quepaso_report.send_close_mail(dias_cuerpo=30)
    assert r["sent"] is True
    to, subject, body, adj = sent[0]
    assert to == "rodri@delta.com" and "Cierre" in subject and "Qué pasó" in subject
    assert "Tasa fija" in body and "Δ precio" in body          # resumen por segmento
    assert [a[0] for a in adj] == ["que_paso_30d.csv", "que_paso_7d.csv"]
    csv30 = adj[0][1].decode("utf-8")
    assert csv30.startswith("﻿") and base_sintetica["c1"] in csv30
    assert "5,26" in csv30                                     # 100/95−1 es-AR


def test_mail_de_cierre_apagado_o_sin_smtp(monkeypatch) -> None:
    monkeypatch.setattr(settings, "quepaso_mail", False)
    assert quepaso_report.send_close_mail()["sent"] is False
    monkeypatch.setattr(settings, "quepaso_mail", True)
    monkeypatch.setattr(mailer, "is_configured", lambda: False)
    r = quepaso_report.send_close_mail()
    assert r["sent"] is False and "SMTP" in r["detail"]


# ── Watchdog del feed ────────────────────────────────────────────────────────
def _wd(umbral_min, down_flag, t0):
    state = {"down": down_flag, "now": t0}
    wd = FeedWatchdog(umbral_min=umbral_min,
                      is_down=lambda: state["down"],
                      now_fn=lambda: state["now"])
    mails = []
    wd._mail = lambda s, b: mails.append((s, b))
    return wd, state, mails


def test_watchdog_avisa_una_vez_y_recupera() -> None:
    t0 = datetime(2026, 7, 15, 12, 0, tzinfo=_TZ)          # miércoles en rueda
    wd, st, mails = _wd(5, True, t0)
    assert wd.check_once() is None                          # recién caído
    st["now"] = t0 + timedelta(minutes=3)
    assert wd.check_once() is None                          # < umbral
    st["now"] = t0 + timedelta(minutes=6)
    assert wd.check_once() == "caida"                       # cruza el umbral
    st["now"] = t0 + timedelta(minutes=20)
    assert wd.check_once() is None                          # sin spam
    st["down"] = False
    st["now"] = t0 + timedelta(minutes=25)
    assert wd.check_once() == "recuperado"
    assert wd.check_once() is None                          # estable
    assert len(mails) == 2
    assert "caído" in mails[0][0] and "recuperado" in mails[1][0]


def test_watchdog_fuera_de_rueda_no_alarma() -> None:
    t0 = datetime(2026, 7, 15, 22, 0, tzinfo=_TZ)          # de noche
    wd, st, mails = _wd(5, True, t0)
    st["now"] = t0 + timedelta(minutes=30)
    assert wd.check_once() is None and mails == []
    # sábado al mediodía tampoco
    t1 = datetime(2026, 7, 18, 12, 0, tzinfo=_TZ)
    wd2, st2, mails2 = _wd(5, True, t1)
    st2["now"] = t1 + timedelta(minutes=30)
    assert wd2.check_once() is None and mails2 == []


def test_en_rueda(monkeypatch) -> None:
    assert en_rueda(datetime(2026, 7, 15, 12, 0, tzinfo=_TZ))
    assert en_rueda(datetime(2026, 7, 15, 10, 44, tzinfo=_TZ))      # 10:30 ya abrió
    assert not en_rueda(datetime(2026, 7, 15, 10, 29, tzinfo=_TZ))
    assert not en_rueda(datetime(2026, 7, 15, 17, 0, tzinfo=_TZ))
    assert not en_rueda(datetime(2026, 7, 18, 12, 0, tzinfo=_TZ))   # sábado
    # configurable: MISMO setting que los relojes (MKT_HORARIO_ARG)
    monkeypatch.setattr(settings, "mkt_horario_arg", "11:00-16:30")
    assert not en_rueda(datetime(2026, 7, 15, 10, 44, tzinfo=_TZ))
    assert en_rueda(datetime(2026, 7, 15, 16, 15, tzinfo=_TZ))
    assert not en_rueda(datetime(2026, 7, 15, 16, 45, tzinfo=_TZ))
    monkeypatch.setattr(settings, "mkt_horario_arg", "basura")      # ilegible → default
    assert en_rueda(datetime(2026, 7, 15, 10, 44, tzinfo=_TZ))


# ── Campana de alertas (superuser) ──────────────────────────────────────────
@pytest.mark.asyncio
async def test_estado_alertas_y_campana(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ALERTAS_PATH", str(tmp_path / "alertas.json"))
    monkeypatch.setattr(alertas_svc, "current_value", lambda c, m: 105.0)
    assert alertas_svc.add("AL30", "precio", ">=", 100.0) is None
    assert alertas_svc.add("GD30", "precio", ">=", 999_999.0) is None
    assert alertas_svc.check_once() == 1
    async with _client() as ac:
        r = await ac.get("/alertas/estado")
        assert r.status_code == 200
        assert r.json() == {"disparadas": 1, "activas": 1}
        # sin auth (dev) la topbar muestra la campana
        y = await ac.get("/yas")
        assert 'id="alert-bell"' in y.text


@pytest.mark.asyncio
async def test_campana_solo_superuser(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "app_users_path", str(tmp_path / "store.json"))
    auth.refresh()
    assert auth.ensure_bootstrapped()["created"]
    async with _client() as su:
        await su.post("/login", data={"username": "rodricor93", "password": "Rc_874562", "next": "/yas"})
        await su.post("/admin/users", data={"username": "prem", "password": "clave123", "role": "premium"})
        y = await su.get("/yas")
        assert 'id="alert-bell"' in y.text                  # superuser la ve
    async with _client() as ac:
        await ac.post("/login", data={"username": "prem", "password": "clave123", "next": "/yas"})
        y = await ac.get("/yas")
        assert y.status_code == 200 and 'id="alert-bell"' not in y.text
        assert (await ac.get("/alertas/estado")).status_code == 403
    auth.refresh()


# ── Mini-histórico YAS ──────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_yas_hist_sparklines(base_sintetica) -> None:
    async with _client() as ac:
        r = await ac.get("/yas/hist", params={"code": base_sintetica["c1"], "dias": 90})
        assert r.status_code == 200
        assert "Histórico" in r.text and "<svg" in r.text
        assert "Precio" in r.text and "TIREA" in r.text
        # delta de precio de la fixture: 95 → 100 = +5,26%
        assert "+5,26%" in r.text
        # TIR en %: 34 → 30 = −4 pp
        assert "-4,00 pp" in r.text
        # código sin histórico → nota suave, sin romper
        r2 = await ac.get("/yas/hist", params={"code": "ZZZZ99"})
        assert r2.status_code == 200 and "Sin histórico" in r2.text
        # la página YAS trae el contenedor lazy (no bloquea la ficha)
        page = await ac.get("/yas")
        assert 'id="yas-hist"' in page.text


def test_feriados_en_relojes() -> None:
    js = open("backend/static/js/app.js", encoding="utf-8").read()
    assert "'2026-07-09'" in js and "'2026-12-25'" in js       # ARG
    assert "'2026-11-26'" in js and "'2027-07-05'" in js       # NYSE (Thanksgiving/4 jul obs.)
    assert "feriado" in js
