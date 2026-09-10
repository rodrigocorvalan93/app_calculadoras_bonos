"""Curva de Treasuries USA (par yields) + G-spread / Z-spread de bonos USD.

Fuente: "Daily Treasury Par Yield Curve Rates" (CSV público de
home.treasury.gov, sin API key, dato EOD). La curva se baja 1×/día en un
THREAD DE FONDO — nunca dentro de un request — y sin red se usa el snapshot
commiteado `ust_backup.json` (mismo patrón que `bcra_data_backup.json`).
La fecha de la curva usada viaja en todos los outputs, así siempre se ve
contra qué curva se calculó.

Todo stdlib a propósito (sin scipy/pandas/requests): el módulo lo importa
también `bymaapi.py` fuera del server, y el z-spread se resuelve por
bisección — la función precio(z) es monótona decreciente en z, 60 pasos
sobre ~30 flujos son microsegundos.

Convenciones (documentadas para poder auditarlas):
- Los par yields del Tesoro son bond-equivalent → compuestos SEMIANUALES,
  en % anual. Tenores 1M…30Y.
- Curva cero: bootstrap estándar sobre nodos semianuales 0.5…30 años con la
  par interpolada lineal (un bono a la par de cupón c: 100 = c/2·Σdf + 100·df_n
  ⇒ df_n despeja en cadena). Los tenores < 6M pasan directo (un solo pago).
- Tiempos ACT/365: el MISMO day-count con que rentafija descuenta la TIR
  (`_cf_yearfracs`), así el z-spread es consistente con la TIREA de la app.
- G-spread = TIREA − UST a la duration del bono, con la UST convertida a
  EFECTIVA anual ((1+y_sa/2)²−1) para restar en las mismas unidades que la
  TIREA (que es efectiva). En bps.
- Z-spread = shift z (anual, decimal) tal que descontando los flujos del
  bono contra la curva cero semianual desplazada reproduce el precio dirty:
      Σ flujo_i / (1 + (zero(t_i)+z)/2)^(2·t_i)  ==  precio
  Se usan LOS MISMOS flujos que usó rentafija para la TIR
  (cashflow_cpn['Fechas'] > fecha_settlement, columna 'Total'). En bps.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import threading
import time
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger("uvicorn.error")

# Encabezados del CSV del Tesoro → años. El parser es tolerante: usa los que
# encuentre (el Tesoro agregó/quitó tenores a lo largo de los años).
_TENOR_YEARS: Dict[str, float] = {
    "1 mo": 1 / 12, "1.5 month": 1.5 / 12, "2 mo": 2 / 12, "3 mo": 3 / 12,
    "4 mo": 4 / 12, "6 mo": 6 / 12,
    "1 yr": 1.0, "2 yr": 2.0, "3 yr": 3.0, "5 yr": 5.0, "7 yr": 7.0,
    "10 yr": 10.0, "20 yr": 20.0, "30 yr": 30.0,
}

_CSV_URL = ("https://home.treasury.gov/resource-center/data-chart-center/"
            "interest-rates/daily-treasury-rates.csv/{year}/all"
            "?type=daily_treasury_yield_curve&field_tdr_date_value={year}"
            "&page&_format=csv")

_BACKUP_PATH = Path(__file__).resolve().parents[2] / "ust_backup.json"
_REFRESH_OK_S = 6 * 3600    # dato EOD: con reintentar cada 6 h sobra
_REFRESH_FAIL_S = 30 * 60   # sin red: reintento suave cada 30 min

_lock = threading.Lock()
# par/zero: listas de (t_años, tasa_%) ordenadas por t. fuente: "treasury.gov" | "backup".
_state: Dict[str, Any] = {"fecha": None, "par": [], "zero": [], "fuente": None}
_thread_started = False


# ── fetch + parseo ───────────────────────────────────────────────────────


def _parse_csv(text: str) -> Optional[Tuple[date, List[Tuple[float, float]]]]:
    """Primera fila con datos del CSV del Tesoro (viene ordenado nuevo→viejo)."""
    try:
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            pts: List[Tuple[float, float]] = []
            for k, v in row.items():
                t = _TENOR_YEARS.get((k or "").strip().lower())
                if t is None or v in (None, "", "N/A"):
                    continue
                try:
                    pts.append((t, float(v)))
                except ValueError:
                    continue
            # Curva usable: varios puntos y algo en la parte larga.
            if len(pts) >= 6 and max(t for t, _ in pts) >= 10.0:
                fecha = datetime.strptime(row.get("Date", "").strip(), "%m/%d/%Y").date()
                pts.sort()
                return fecha, pts
    except Exception as exc:  # noqa: BLE001
        logger.debug("[ust] CSV inválido: %s", exc)
    return None


def _fetch_treasury() -> Optional[Tuple[date, List[Tuple[float, float]]]]:
    """Baja el CSV del año actual (o el anterior, si el año recién empieza)."""
    year = date.today().year
    for y in (year, year - 1):
        try:
            req = urllib.request.Request(
                _CSV_URL.format(year=y),
                headers={"User-Agent": "Mozilla/5.0 (app-calculadoras-bonos)"},
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                got = _parse_csv(resp.read().decode("utf-8", "replace"))
            if got:
                return got
        except Exception as exc:  # noqa: BLE001
            logger.debug("[ust] fetch %s falló: %s", y, exc)
    return None


def _load_backup() -> Optional[Tuple[date, List[Tuple[float, float]]]]:
    try:
        raw = json.loads(_BACKUP_PATH.read_text(encoding="utf-8"))
        fecha = date.fromisoformat(raw["fecha"])
        pts = sorted((float(t), float(y)) for t, y in raw["par"])
        return (fecha, pts) if pts else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("[ust] backup ilegible (%s): %s", _BACKUP_PATH.name, exc)
        return None


# ── curva cero (bootstrap) ───────────────────────────────────────────────


def _interp(pts: Sequence[Tuple[float, float]], t: float) -> float:
    """Interpolación lineal en t; extremos planos. `pts` ordenada por t."""
    if not pts:
        return float("nan")
    if t <= pts[0][0]:
        return pts[0][1]
    if t >= pts[-1][0]:
        return pts[-1][1]
    for (t0, y0), (t1, y1) in zip(pts, pts[1:]):
        if t0 <= t <= t1:
            return y0 + (y1 - y0) * (t - t0) / (t1 - t0)
    return pts[-1][1]  # inalcanzable con pts ordenada


def _bootstrap_zero(par: Sequence[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Curva cero semianual (%) desde la par. Nodos: los tenores <6M directos
    (un solo pago ⇒ cero == par) + semianuales 0.5…30 bootstrapeados."""
    zero: List[Tuple[float, float]] = [(t, y) for t, y in par if t < 0.5]
    t_max = max(t for t, _ in par)
    cum_df = 0.0
    k = 1
    while k * 0.5 <= t_max + 1e-9:
        t = k * 0.5
        c = _interp(par, t) / 100.0
        df = (1.0 - (c / 2.0) * cum_df) / (1.0 + c / 2.0)
        if df <= 0.0:  # curva rota (no debería con yields reales)
            break
        cum_df += df
        zero.append((t, ((1.0 / df) ** (1.0 / (2.0 * t)) - 1.0) * 2.0 * 100.0))
        k += 1
    zero.sort()
    return zero


def _set_curve(fecha: date, par: List[Tuple[float, float]], fuente: str) -> None:
    zero = _bootstrap_zero(par)
    with _lock:
        _state.update({"fecha": fecha, "par": list(par), "zero": zero, "fuente": fuente})


def _fetch_loop() -> None:
    while True:
        got = None
        try:
            got = _fetch_treasury()
            if got:
                _set_curve(got[0], got[1], "treasury.gov")
                logger.info("[ust] curva del %s cargada (%d tenores)", got[0], len(got[1]))
        except Exception as exc:  # noqa: BLE001
            logger.debug("[ust] refresh falló: %s", exc)
        time.sleep(_REFRESH_OK_S if got else _REFRESH_FAIL_S)


def _ensure_loaded() -> None:
    """Backup sincrónico la primera vez (lectura local, sub-ms) + arranca el
    thread daemon que intenta la curva viva. Nunca red en el caller."""
    global _thread_started
    with _lock:
        empty = not _state["par"]
        start = not _thread_started
        _thread_started = True
    if empty:
        got = _load_backup()
        if got:
            _set_curve(got[0], got[1], "backup")
    if start:
        threading.Thread(target=_fetch_loop, name="ust-refresh", daemon=True).start()


# ── API pública ──────────────────────────────────────────────────────────


def curve_info() -> Dict[str, Any]:
    """{"fecha": date|None, "fuente": str|None, "n": int} de la curva vigente."""
    _ensure_loaded()
    with _lock:
        return {"fecha": _state["fecha"], "fuente": _state["fuente"], "n": len(_state["par"])}


def yield_at(t_years: float) -> float:
    """UST a t años en % EFECTIVO anual (par semianual interpolada y convertida)."""
    _ensure_loaded()
    with _lock:
        par = _state["par"]
    if not par or not (t_years == t_years) or t_years <= 0:
        return float("nan")
    y_sa = _interp(par, t_years)
    return ((1.0 + y_sa / 200.0) ** 2 - 1.0) * 100.0


def g_spread_bps(tirea: float, duration: float) -> float:
    """TIREA (decimal) − UST efectiva a la duration, en bps."""
    if not (tirea == tirea) or not (duration == duration) or duration <= 0:
        return float("nan")
    y = yield_at(duration)
    return (tirea * 100.0 - y) * 100.0 if y == y else float("nan")


def z_spread_bps(flows: Sequence[Tuple[date, float]], dirty: float, settle: date) -> float:
    """Resuelve por bisección el z tal que PV(curva cero + z) == dirty.

    `flows`: (fecha, monto) en la MISMA escala que `dirty` (la escala se
    cancela). Devuelve bps, o NaN si no hay curva/flujos o el precio queda
    fuera del rango alcanzable con z ∈ [−50%, +500%] anual.
    """
    _ensure_loaded()
    with _lock:
        zero = _state["zero"]
    if not zero or not flows or not (dirty == dirty) or dirty <= 0:
        return float("nan")

    # (t ACT/365, monto, cero_t) precalculados: la bisección sólo hace potencias.
    legs: List[Tuple[float, float, float]] = []
    for f, m in flows:
        t = (f - settle).days / 365.0
        if t > 0 and m == m:
            legs.append((t, float(m), _interp(zero, t) / 100.0))
    if not legs:
        return float("nan")

    def pv(z: float) -> float:
        total = 0.0
        for t, m, r0 in legs:
            r = (r0 + z) / 2.0
            if r <= -1.0:
                return float("inf")
            total += m / (1.0 + r) ** (2.0 * t)
        return total

    lo, hi = -0.5, 5.0
    if not (pv(hi) <= dirty <= pv(lo)):
        return float("nan")
    for _ in range(60):  # 5.5/2^60 ≈ precisión infinita a efectos de bps
        mid = (lo + hi) / 2.0
        if pv(mid) > dirty:  # PV alto ⇒ falta spread
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0 * 1e4


# ── Integración con rentafija.Bono ───────────────────────────────────────


def _as_date(x: Any) -> Optional[date]:
    if isinstance(x, datetime):  # cubre pandas.Timestamp (subclase)
        return x.date()
    return x if isinstance(x, date) else None


def flujos_bono(bono: Any) -> List[Tuple[date, float]]:
    """Flujos (fecha, total) del bono ya calculado — EXACTAMENTE los que
    rentafija usa para la TIR: cashflow_cpn con Fechas > fecha_settlement,
    columna Total. Duck-typed (no importa pandas)."""
    cf = getattr(bono, "cashflow_cpn", None)
    settle = _as_date(getattr(bono, "fecha_settlement", None))
    if cf is None or settle is None or len(cf) == 0:
        return []
    try:
        # Acceso por columna (no iterrows): ~10× más rápido y en el render
        # frío de curvas esto corre para ~100 bonos hard-dollar.
        fechas = list(cf["Fechas"])
        totales = list(cf["Total"])
    except Exception:  # noqa: BLE001
        return []
    out: List[Tuple[date, float]] = []
    for f_raw, m in zip(fechas, totales):
        f = _as_date(f_raw)
        if f is not None and f > settle and m is not None and m == m:
            out.append((f, float(m)))
    return out


def spreads_bono(bono: Any, tirea: float, duration: float) -> Tuple[float, float, Optional[date]]:
    """(g_bps, z_bps, fecha_curva) de un bono hard-dollar YA calculado
    (calcula_tirea/calcula_precio corridos: usa .precio dirty,
    .fecha_settlement y cashflow_cpn). Nunca levanta: NaN en falla."""
    try:
        g = g_spread_bps(tirea, duration)
    except Exception:  # noqa: BLE001
        g = float("nan")
    z = float("nan")
    try:
        settle = _as_date(getattr(bono, "fecha_settlement", None))
        dirty = float(getattr(bono, "precio", float("nan")))
        flows = flujos_bono(bono)
        if flows and settle is not None:
            z = z_spread_bps(flows, dirty, settle)
    except Exception:  # noqa: BLE001
        pass
    return g, z, curve_info().get("fecha")
