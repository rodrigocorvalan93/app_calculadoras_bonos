"""Total Return — núcleo apoyado en `rentafija.Bono.calcula_total_return`.

Por bono y para un horizonte (fecha terminal) con una TIR de salida y1:

    Carry      = calcula_total_return(y0, y0)        → cupón + roll-down (yield fijo)
    Compresión = calcula_total_return(y0, y1) − Carry → efecto del Δyield (y0→y1)
    TR real    = Carry + Compresión = calcula_total_return(y0, y1)  (sin inflación)
    Ajuste     = drift del índice proyectado (CER/UVA/A3500) sobre [settle, terminal]
    TR total   = (1+TR real)·(1+Ajuste) − 1   (nominal, con proyección BASE)

Columnas aditivas para mostrar: Carry + Compresión + Ajuste = TR total.
Real vs proyectado: TR real ignora la proyección (es la ficha base, que congela
el índice a hoy); TR total la incluye vía el drift. Réplica fiel de
`OMSweb_app.compute_total_return_table` + `_tr_compute_drifts`. El cálculo es
on-demand y se cachea por (curva, plazo, terminal, modo, params, día).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

import numpy as np

from backend.cache import LockedTTLCache

_cache = LockedTTLCache(maxsize=64, ttl=20)


# ── parseo / helpers ───────────────────────────────────────────────────────
def _pct(x: Any) -> float:
    """'12.345600%' → 0.12345 ; números pasan derecho."""
    if x is None:
        return float("nan")
    if isinstance(x, (int, float, np.floating)):
        return float(x)
    try:
        s = str(x).strip().replace(",", ".")
        return float(s[:-1]) / 100.0 if s.endswith("%") else float(s)
    except (TypeError, ValueError):
        return float("nan")


def _parse_d(s: str) -> Optional[date]:
    try:
        return datetime.strptime(s, "%d/%m/%Y").date()
    except (TypeError, ValueError):
        return None


def settle_str(plazo: str) -> str:
    """Fecha de liquidación concreta '%d/%m/%Y'. CI → hoy; 24hs → próximo hábil
    (pricing.settlement_date_str devuelve None para 24hs)."""
    from backend.services import pricing
    s = pricing.settlement_date_str(plazo)
    if s:
        return s
    try:
        from dias_habiles import siguiente_dia_habil_ar
        return siguiente_dia_habil_ar(date.today()).strftime("%d/%m/%Y")
    except Exception:  # noqa: BLE001
        return date.today().strftime("%d/%m/%Y")


def _nearest_prior(df, target, col) -> Optional[float]:
    """Último valor con índice ≤ target (nearest-prior). Como el legacy."""
    if df is None or target is None or getattr(df, "empty", True):
        return None
    try:
        import pandas as pd
        idx = pd.to_datetime(df.index)
        mask = idx <= pd.Timestamp(target)
        if not mask.any():
            v = df.iloc[0][col]
        else:
            v = df.loc[df.index[mask][-1], col]
        if isinstance(v, pd.Series):
            v = v.iloc[0]
        return float(v) if pd.notna(v) else None
    except Exception:  # noqa: BLE001
        return None


def _index_drift(obj, settle_d: date, terminal_d: date) -> float:
    """Crecimiento del índice proyectado (CER/UVA/A3500) entre settle y terminal,
    lagueado con `dias_lag_ajuste_base`. 0 para bonos sin ajuste de capital."""
    ajuste = (getattr(obj, "ajuste_sobre_capital", None) or "").upper()
    if not ajuste:
        return 0.0
    import rentafija
    lag = int(getattr(obj, "dias_lag_ajuste_base", -10) or -10)
    sl = rentafija.n_dias_laborales(settle_d, lag)
    tl = rentafija.n_dias_laborales(terminal_d, lag)
    inputs = rentafija.inputs

    def _drift(key: str, col: str) -> float:
        df = inputs.get(key)
        cs = _nearest_prior(df, sl, col)
        ct = _nearest_prior(df, tl, col)
        return float(ct / cs - 1.0) if (cs and ct and cs > 0) else 0.0

    if "CER" in ajuste:
        return _drift("cer_proyectado", "CER")
    if "UVA" in ajuste:
        return _drift("uva_proyectado", "UVA")
    if "A3500" in ajuste:
        return _drift("a3500_proyectado", "tca3500")
    return 0.0


# ── curva de salida (3 modos) → y1 por duration ──────────────────────────────
def scenario_params(durations: np.ndarray, level_pct: float, slope_bps: float,
                    convex_bps: float, anchor: float = 1.0) -> np.ndarray:
    """y1 (decimal) por duration: parábola nivel + pendiente·dx + convexidad·dx²."""
    x = np.asarray(durations, dtype="float64")
    dx = x - float(anchor)
    y = float(level_pct) / 100.0 + float(slope_bps) / 10000.0 * dx + float(convex_bps) / 10000.0 * dx ** 2
    return np.clip(y, -0.99, 5.0)


def scenario_points(durations: np.ndarray, pts: List[tuple]) -> np.ndarray:
    """Interpolación lineal sobre puntos (duration, TIREA %). pts = [(d, y%), …]."""
    arr = [(float(d), float(y) / 100.0) for d, y in pts
           if d is not None and y is not None and d == d and y == y]
    if len(arr) < 2:
        return np.full(len(durations), np.nan)
    arr.sort()
    xs = np.array([a for a, _ in arr]); ys = np.array([b for _, b in arr])
    return np.interp(np.asarray(durations, dtype="float64"), xs, ys, left=ys[0], right=ys[-1])


def scenario_nss(durations: np.ndarray, popt: List[float]) -> np.ndarray:
    """y1 (decimal) evaluando el modelo NSS con params dados (β0..τ2)."""
    from backend.services import nss
    return np.asarray(nss.model(np.asarray(durations, dtype="float64"), *popt), dtype="float64") / 100.0


# ── total return por bono ────────────────────────────────────────────────────
def _bond_tr(code: str, y0: float, y1: float, terminal_str: str, settle_str: str,
             settle_d: date, terminal_d: date, dur0: Optional[float]) -> Optional[Dict[str, Any]]:
    from backend.services import pricing
    obj = pricing._bond_obj_copy(code)
    if obj is None or not hasattr(obj, "calcula_total_return"):
        return None
    try:
        # generate_cashflows se rearma en cada llamada → las dos son independientes.
        carry_df = obj.calcula_total_return(float(y0), float(y0), terminal_str, settle_str)
        real_df = obj.calcula_total_return(float(y0), float(y1), terminal_str, settle_str)
        carry = _pct(carry_df.loc["Total Return", "Total Return Valores"])
        tr_real = _pct(real_df.loc["Total Return", "Total Return Valores"])
        px_target = float(real_df.loc["Px final", "Total Return Valores"])
    except Exception:  # noqa: BLE001
        return None
    if tr_real != tr_real or carry != carry:        # NaN
        return None
    compresion = tr_real - carry
    drift = _index_drift(obj, settle_d, terminal_d)
    tr_total = (1.0 + tr_real) * (1.0 + drift) - 1.0
    ajuste = tr_total - tr_real
    # Duration a la fecha target (settle = terminal). La ficha CER base NO puede
    # calcular a un settle futuro (no hay CER observado futuro → KeyError), así
    # que para la duration final usamos la ficha proyectada `code+'j'` si existe.
    dur_f = None
    try:
        from backend.services import bond_universe, pricing as pr
        dcode = code + "j" if bond_universe.get(code + "j") is not None else code
        m = pr.compute_metrics(dcode, mode="tir", value=float(y1), settle=terminal_str, include_cashflows=False)
        d = (m or {}).get("duration") if (m and not m.get("error")) else None
        if d is not None and d == d:
            dur_f = float(d)
    except Exception:  # noqa: BLE001
        dur_f = None
    return {
        "code": code, "dur0": dur0, "y0": y0, "dur_f": dur_f, "y1": y1,
        "px_target": px_target, "carry": carry, "compresion": compresion,
        "ajuste": ajuste, "tr_real": tr_real, "tr_total": tr_total,
    }


def compute_rows(rows: List[Dict[str, Any]], terminal_str: str, settle_str: str,
                 y1_by_code: Dict[str, float]) -> tuple:
    """Una fila de TR por bono. `rows` = filas de `_rows_for` (code/duration/tirea).
    `y1_by_code` = TIR de salida (decimal) por código. Devuelve (filas, días)."""
    settle_d, terminal_d = _parse_d(settle_str), _parse_d(terminal_str)
    dias = (terminal_d - settle_d).days if (settle_d and terminal_d) else None
    out: List[Dict[str, Any]] = []
    for r in rows:
        code = r.get("code"); y0 = r.get("tirea")
        y1 = y1_by_code.get(code)
        if not code or y0 is None or y0 != y0 or y1 is None or y1 != y1:
            continue
        res = _bond_tr(code, y0, y1, terminal_str, settle_str, settle_d, terminal_d, r.get("duration"))
        if res:
            out.append(res)
    out.sort(key=lambda x: (x["dur0"] is None, x["dur0"] or 0.0))
    return out, dias
