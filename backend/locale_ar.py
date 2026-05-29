"""es-AR formatting helpers (decimal coma, fechas DD/MM/YYYY).

All template-facing formatters live here so the UI is consistent across
panels. Each helper returns the empty-state token "—" for NaN/None to
match the look of the legacy Streamlit app.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

try:
    import numpy as np
except ImportError:  # pragma: no cover - numpy always present at runtime
    np = None  # type: ignore[assignment]


DASH = "—"


def _is_nan(x: Any) -> bool:
    if x is None:
        return True
    if isinstance(x, str):
        return False
    if np is not None:
        try:
            return bool(np.isnan(x))
        except (TypeError, ValueError):
            return False
    try:
        return x != x  # NaN trick
    except Exception:  # noqa: BLE001
        return False


def _swap_sep(s: str) -> str:
    # 1,234.5678 → 1.234,5678 (US → es-AR)
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def fmt_pct(x: Any, decimals: int = 4) -> str:
    """0.4231 → '42,3100%'."""
    if _is_nan(x):
        return DASH
    try:
        return _swap_sep(f"{float(x) * 100:,.{decimals}f}") + "%"
    except (TypeError, ValueError):
        return DASH


def fmt_pct_pp(x: Any, decimals: int = 2) -> str:
    """100.0 → '100,00%' (the value is already a percentage point)."""
    if _is_nan(x):
        return DASH
    try:
        return _swap_sep(f"{float(x):,.{decimals}f}") + "%"
    except (TypeError, ValueError):
        return DASH


def fmt_num(x: Any, decimals: int = 4) -> str:
    """1234.5678 → '1.234,5678'."""
    if _is_nan(x):
        return DASH
    try:
        return _swap_sep(f"{float(x):,.{decimals}f}")
    except (TypeError, ValueError):
        return DASH


def fmt_int(x: Any) -> str:
    if _is_nan(x):
        return DASH
    try:
        return _swap_sep(f"{int(x):,d}")
    except (TypeError, ValueError):
        return DASH


def fmt_money(x: Any, decimals: int = 2) -> str:
    """Same as fmt_num but with fewer decimals by default."""
    return fmt_num(x, decimals=decimals)


def fmt_date(d: Any) -> str:
    if d is None:
        return DASH
    if isinstance(d, datetime):
        return d.strftime("%d/%m/%Y")
    if isinstance(d, date):
        return d.strftime("%d/%m/%Y")
    return str(d)


def fmt_ts(ts: Any) -> str:
    """Epoch-ms (o string) → 'DD/MM HH:MM:SS'. Para Price Date (LA/CL)."""
    if ts is None or ts == "":
        return DASH
    try:
        ms = float(ts)
    except (TypeError, ValueError):
        return str(ts)
    if ms <= 0:
        return DASH
    try:
        return datetime.fromtimestamp(ms / 1000.0).strftime("%d/%m %H:%M:%S")
    except (OverflowError, OSError, ValueError):
        return DASH


def fmt_hum(x: Any) -> str:
    """1234567 → '1,2M'. Para volúmenes ($ efectivo / nominales)."""
    if _is_nan(x):
        return DASH
    try:
        n = float(x)
    except (TypeError, ValueError):
        return DASH
    a = abs(n)
    for div, suf in ((1e12, "B"), (1e9, "MM"), (1e6, "M"), (1e3, "k")):
        if a >= div:
            return _swap_sep(f"{n / div:,.1f}") + suf
    return _swap_sep(f"{n:,.0f}")


JINJA_FILTERS = {
    "ar_pct": fmt_pct,
    "ar_pct_pp": fmt_pct_pp,
    "ar_num": fmt_num,
    "ar_int": fmt_int,
    "ar_money": fmt_money,
    "ar_date": fmt_date,
    "ar_ts": fmt_ts,
    "ar_hum": fmt_hum,
}
