"""Curva UST + G/Z-spread de bonos hard-dollar (backend/services/ust.py).

Cubre: (a) la matemática pura (bootstrap, interpolación, recuperación de un
z conocido), (b) el hook en compute_metrics (globales sí, CER no), (c) el
render HTTP de YAS, (d) el wrapper genera_ticket_global de bymaapi.py (vía
extracción AST, mismo truco que test_bymaapi_guardar — el import completo
tarda ~27 s).

Nunca hay red: la curva sale de ust_backup.json commiteado (el thread de
refresh falla silencioso contra el proxy del CI y el backup queda vigente).
"""
from __future__ import annotations

import ast
import math
from datetime import date, timedelta
from pathlib import Path

import pytest

from backend.services import bond_universe, pricing, ust

_REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session", autouse=True)
def _load_universe() -> None:
    bond_universe.ensure_loaded()


# ── Matemática pura ──────────────────────────────────────────────────────

def test_bootstrap_curva_chata_es_identidad() -> None:
    # Con la par chata al 4%, el bono a la par de cupón 4 descuenta a 4% en
    # todos los nodos ⇒ los ceros semianuales tienen que dar 4% exacto.
    flat = [(t, 4.0) for t in (0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0)]
    zeros = ust._bootstrap_zero(flat)
    assert len(zeros) == 61  # 1 nodo <6M + 60 semianuales hasta 30 años
    assert max(abs(y - 4.0) for _, y in zeros) < 1e-9


def test_interp_lineal_extremos_planos() -> None:
    pts = [(1.0, 3.0), (3.0, 5.0)]
    assert ust._interp(pts, 2.0) == pytest.approx(4.0)
    assert ust._interp(pts, 0.1) == 3.0   # antes del primer nodo → plano
    assert ust._interp(pts, 10.0) == 5.0  # después del último → plano
    assert math.isnan(ust._interp([], 1.0))


def test_z_spread_recupera_z_conocido() -> None:
    # Bullet sintético 5 años: si el precio se construye descontando a
    # cero+z, el solver tiene que devolver exactamente ese z.
    ust._ensure_loaded()
    settle = date(2026, 9, 10)
    flows = [(settle + timedelta(days=int(k * 182.5)),
              4.0 + (100.0 if k == 10 else 0.0)) for k in range(1, 11)]
    with ust._lock:
        zero = list(ust._state["zero"])
    assert zero, "el backup ust_backup.json no cargó"
    for z_true in (0.0150, 0.0, -0.0075, 0.35):
        dirty = 0.0
        for f, m in flows:
            t = (f - settle).days / 365.0
            r = (ust._interp(zero, t) / 100.0 + z_true) / 2.0
            dirty += m / (1.0 + r) ** (2.0 * t)
        z_hat = ust.z_spread_bps(flows, dirty, settle)
        assert z_hat == pytest.approx(z_true * 1e4, abs=1e-6), z_true


def test_z_spread_casos_borde_dan_nan() -> None:
    settle = date(2026, 9, 10)
    flows = [(settle + timedelta(days=365), 100.0)]
    assert math.isnan(ust.z_spread_bps(flows, 1e9, settle))    # precio fuera de rango
    assert math.isnan(ust.z_spread_bps(flows, -5.0, settle))   # precio inválido
    assert math.isnan(ust.z_spread_bps([], 100.0, settle))     # sin flujos
    # todos los flujos ya vencidos al settle → sin patas → NaN
    assert math.isnan(ust.z_spread_bps([(settle - timedelta(days=10), 100.0)], 90.0, settle))


def test_g_spread_resta_en_efectiva() -> None:
    y = ust.yield_at(5.0)
    assert y == y
    # la par se convierte a efectiva: (1+y_sa/2)² − 1 > y_sa siempre
    with ust._lock:
        par = list(ust._state["par"])
    assert y > ust._interp(par, 5.0)
    assert ust.g_spread_bps(0.10, 5.0) == pytest.approx((10.0 - y) * 100.0)
    assert math.isnan(ust.g_spread_bps(float("nan"), 5.0))
    assert math.isnan(ust.g_spread_bps(0.10, float("nan")))
    assert math.isnan(ust.g_spread_bps(0.10, 0.0))


def test_parse_csv_formato_tesoro() -> None:
    csv_text = (
        "Date,1 Mo,2 Mo,3 Mo,6 Mo,1 Yr,2 Yr,5 Yr,10 Yr,30 Yr\n"
        "09/08/2026,4.10,4.08,4.05,3.95,3.80,3.70,3.85,4.20,4.75\n"
        "09/05/2026,4.11,4.09,4.06,3.96,3.81,3.71,3.86,4.21,4.76\n"
    )
    got = ust._parse_csv(csv_text)
    assert got is not None
    fecha, pts = got
    assert fecha == date(2026, 9, 8)  # primera fila = la más nueva
    assert (10.0, 4.20) in pts and pts == sorted(pts)
    # CSV roto / sin tenores largos → None, nunca levanta
    assert ust._parse_csv("Date,1 Mo\n09/08/2026,4.10\n") is None
    assert ust._parse_csv("garbage") is None


# ── Hook en compute_metrics ──────────────────────────────────────────────

def test_metrics_global_trae_spreads() -> None:
    if "GD30C" not in bond_universe.all_codes():
        pytest.skip("GD30C not present in especies.py")
    m = pricing.compute_metrics("GD30C", "precio", 70.0)
    assert m.get("error") is None, m.get("error")
    g, z = m["g_spread_bps"], m["z_spread_bps"]
    assert math.isfinite(g) and math.isfinite(z)
    # z y g miden lo mismo con curvas distintas (cero vs par a la duration):
    # tienen que quedar en el mismo orden de magnitud, no a pp de distancia.
    assert abs(z - g) < 300.0, (g, z)
    assert m["ust_fecha"] is not None


def test_metrics_cer_sin_spreads() -> None:
    if "TX26" not in bond_universe.all_codes():
        pytest.skip("TX26 not present in especies.py")
    m = pricing.compute_metrics("TX26", "precio", 735.4)
    assert m.get("error") is None, m.get("error")
    assert math.isnan(m["g_spread_bps"]) and math.isnan(m["z_spread_bps"])


# ── HTTP: YAS muestra el bloque sólo para hard-dollar ────────────────────

@pytest.mark.asyncio
async def test_yas_recompute_global_muestra_zspread() -> None:
    from httpx import ASGITransport, AsyncClient
    from backend.main import app

    if "GD30C" not in bond_universe.all_codes():
        pytest.skip("GD30C not present in especies.py")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.post("/yas/recompute", data={"code": "GD30C", "mode": "precio", "value": "70"})
    assert r.status_code == 200
    assert "Z-spread vs UST" in r.text
    assert "G-spread" in r.text
    assert "bps" in r.text


@pytest.mark.asyncio
async def test_yas_recompute_cer_no_muestra_zspread() -> None:
    from httpx import ASGITransport, AsyncClient
    from backend.main import app

    if "TX26" not in bond_universe.all_codes():
        pytest.skip("TX26 not present in especies.py")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.post("/yas/recompute", data={"code": "TX26", "mode": "precio", "value": "735,4"})
    assert r.status_code == 200
    assert "Z-spread" not in r.text


# ── bymaapi.genera_ticket_global (extracción AST, sin importar el módulo) ─

def _genera_ticket_global():
    tree = ast.parse((_REPO / "bymaapi.py").read_text(encoding="utf-8"))
    picked = [n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "genera_ticket_global"]
    assert picked, "genera_ticket_global no está en bymaapi.py"
    ns: dict = {}
    mod = ast.Module(body=picked, type_ignores=[])
    exec(compile(mod, "bymaapi.py", "exec"), ns)  # noqa: S102 — código propio del repo
    return ns["genera_ticket_global"]


def test_genera_ticket_global_agrega_filas_spread() -> None:
    if "GD30C" not in bond_universe.all_codes():
        pytest.skip("GD30C not present in especies.py")
    fn = _genera_ticket_global()
    bono = pricing._bond_obj_copy("GD30C")
    ticket = fn(bono, 0.70)
    filas = list(ticket.index)
    for fila in ("TIREA", "G-Spread", "Z-Spread", "UST interp. (dur)", "Curva UST"):
        assert fila in filas, f"falta '{fila}' en el ticket: {filas}"
    z_txt = str(ticket.loc["Z-Spread", "Valores"])
    assert z_txt.endswith("bps") and "s/d" not in z_txt, z_txt
    assert str(ticket.loc["Curva UST", "Valores"]) != "s/d"
