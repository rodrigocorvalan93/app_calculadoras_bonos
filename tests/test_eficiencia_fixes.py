"""Regresiones de la revisión de eficiencia + bugs (batch 1).

Cubre: round-trip TNA→precio→TNA en el bucket default (días/365), gap mínimo
en la matriz de forwards viva, guard de no-finitos en NSS eval_at, evict O(k)
del LockedTTLCache (orden de inserción == orden de expiry) y el seq_cached de
/dolares/tables.
"""
from __future__ import annotations

import math
import re

import pytest

from backend.services import bond_universe, pricing


# ── TNA round-trip: la inversión usa la MISMA convención que la conversión ────
def _default_bucket_code() -> str | None:
    """Primer bono vivo cuyo label de convención sea el default días/365."""
    for code in bond_universe.all_codes():
        m = pricing.compute_metrics(code, "precio", 100.0, include_cashflows=False)
        if m.get("error"):
            continue
        if re.match(r"^\d+/365$", m.get("tna_convention_label") or ""):
            if isinstance(m["tna"], float) and math.isfinite(m["tna"]):
                return code
    return None


def test_tna_roundtrip_bucket_default() -> None:
    """precio → TNA → precio debe volver al mismo precio (antes la inversión en
    modo tna caía al fallback cnv_tna con otra base y erraba hasta ~12 %VN)."""
    code = _default_bucket_code()
    if code is None:
        pytest.skip("sin bonos días/365 vivos en especies.py")
    m1 = pricing.compute_metrics(code, "precio", 100.0, include_cashflows=False)
    m2 = pricing.compute_metrics(code, "tna", m1["tna"], include_cashflows=False)
    assert not m2.get("error")
    assert m2["precio_pct"] == pytest.approx(m1["precio_pct"], abs=1e-6)
    assert m2["tirea"] == pytest.approx(m1["tirea"], abs=1e-10)
    # la convención mostrada en la vuelta es la misma que en la ida
    assert m2["tna_convention_label"] == m1["tna_convention_label"]


def test_modo_tna_puebla_dias_remanentes_antes_de_invertir() -> None:
    """El modo tna corre calcula_intereses_corridos ANTES de tirea_from_tna:
    la copia debe terminar con dias_remanentes poblado (no el fallback)."""
    code = _default_bucket_code()
    if code is None:
        pytest.skip("sin bonos días/365 vivos en especies.py")
    m = pricing.compute_metrics(code, "tna", 0.40, include_cashflows=False)
    assert not m.get("error")
    assert re.match(r"^\d+/365$", m["tna_convention_label"])


# ── Forwards en vivo: gap ínfimo de duration no envenena el heatmap ───────────
def test_forwards_matrix_min_gap() -> None:
    from backend.routes.curves import _forwards_matrix

    rows = [
        {"code": "A", "tirea": 0.40, "duration": 0.50},
        {"code": "B", "tirea": 0.80, "duration": 0.502},   # gap 0.002 < _MIN_GAP
        {"code": "C", "tirea": 0.45, "duration": 1.50},
    ]
    m = _forwards_matrix(rows)
    cells = {(r["code"], m["header"][j]["code"]): r["cells"][j]["txt"]
             for r in m["rows"] for j in range(m["n"])}
    assert cells[("A", "B")] == "·"          # par degenerado → sin forward
    assert cells[("A", "C")] != "·"          # los pares sanos siguen
    assert cells[("B", "C")] != "·"


# ── NSS: un fit divergente no mete inf/nan en la respuesta JSON ───────────────
def test_nss_eval_at_guard_no_finitos(monkeypatch) -> None:
    import numpy as np

    from backend.services import nss

    # popt desbocado: b0 enorme → model() da inf DENTRO del rango fiteado.
    monkeypatch.setattr(
        nss, "fit", lambda xs, ys, threshold=3.0: (np.array([1e308, 1e308, 0.0, 0.0, 1.0, 2.0]), 0.5, 2.0))
    out = nss.eval_at([1, 2, 3, 4], [1, 2, 3, 4], [0.1, 1.0, 1.5])
    assert out is not None
    assert out[0] is None                              # fuera de rango
    for v in out:
        assert v is None or math.isfinite(v)           # nunca inf/nan (JSON 500)


# ── LockedTTLCache: evict O(k) por orden de inserción == orden de expiry ──────
def test_cache_evict_descarta_las_mas_viejas() -> None:
    from backend.cache import LockedTTLCache

    c = LockedTTLCache(maxsize=10, ttl=60)
    for i in range(11):                                # la 11ª dispara el evict
        c.get_or_compute(i, lambda i=i: i)
    assert c.get(10) == 10                             # la recién insertada vive
    assert c.get(0) is None and c.get(1) is None       # el frente (viejas) se fue


def test_cache_touch_reinserta_al_final() -> None:
    """touch() extiende el TTL Y mueve la clave al final: el evict no debe
    llevarse una entrada keep-warm recién tocada."""
    from backend.cache import LockedTTLCache

    c = LockedTTLCache(maxsize=10, ttl=60)
    for i in range(10):
        c.get_or_compute(i, lambda i=i: i)
    assert c.touch(0)
    c.get_or_compute("nueva", lambda: "x")             # dispara evict
    assert c.get(0) == 0                               # la tocada sobrevive
    assert c.get(1) is None                            # la más vieja real se fue


# ── /dolares/tables comparte render por tick como sus hermanos ────────────────
@pytest.mark.asyncio
async def test_dolares_tables_seq_cached() -> None:
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r1 = await ac.get("/dolares/tables?plazo=24hs")
        r2 = await ac.get("/dolares/tables?plazo=24hs")
    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.headers.get("x-seq-cache") == "hit"
    assert r1.text == r2.text
