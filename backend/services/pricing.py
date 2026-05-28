"""YAS pricing service.

Ported from `OMSweb_app._ticket_numeric` and extended with:

- Per-tipo TNA convention table (returned alongside the value so the UI
  can render it next to the metric, e.g. "TNA (32/365)").
- Convention override: when the user supplies `freq_days` / `base_days`,
  those win over the auto-detected pair. Lets you sanity-check a number
  against a custom convention without touching `rentafija`.
- Applicable index value: CER / UVA / A3500 / TAMAR / BADLAR — whatever
  index drives the bond. Shown in a sidebar card so dollar-linked, UVA
  and dual TAMAR bonds tell you which series they're being scored
  against.
- Cashflow table (CPN dates + intereses + amortización + ajuste + total)
  returned as a list of plain rows so the template can render it 1816-style.

Thread-safety: `rentafija.Bono` instances in `especies` are singletons,
and `calcula_tirea` mutates `self.tirea`, `self.cashflow_cpn`,
`self.fecha_settlement`, etc. With 4-5 tabs computing different prices
for the same code in parallel they would clobber each other. We follow
the legacy pattern: per-code lock + `copy.copy()` of the bond object
before mutating it.

Convention table — first match wins. `cap32` is a non-linear formula
typical of dual TAMAR; the others use the standard `tir_a_tna`.

  VARIABLE_CAP + TAMAR             → 32/365  (cap32)
  VARIABLE  (BADLAR, TAMAR puro)   → 90/365  (linear)   ← user-requested
  ajuste contains "CER"            → 180/365 (linear)
  ajuste contains "A3500" (DLK)    → 90/365  (linear)
  moneda == USD (hard-dollar)      → 180/360 (linear)
  default (LECAP / bullets ARS)    → días_remanentes/365 (linear)

Margen TNA: VARIABLE_CAP uses cap32 fórmula, VARIABLE uses TNA − bench/100
(both ported verbatim from rentafija.genera_ticket / commit 0106d25).
"""
from __future__ import annotations

import copy
import logging
import threading
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from . import bond_universe

logger = logging.getLogger("backend.pricing")

_bond_locks: Dict[str, threading.Lock] = defaultdict(threading.Lock)

NAN_METRICS: Dict[str, float] = {
    "tirea": float("nan"),
    "tna": float("nan"),
    "tna_raw": float("nan"),
    "tem": float("nan"),
    "duration": float("nan"),
    "paridad": float("nan"),
    "margen_tna": float("nan"),
    "precio_pct": float("nan"),
    "precio_clean_pct": float("nan"),
    "precio": float("nan"),
    "precio_clean": float("nan"),
    "intereses_corridos": float("nan"),
    "dias_corridos": float("nan"),
    "dias_remanentes": float("nan"),
    "valor_residual": float("nan"),
    "valor_tecnico": float("nan"),
}


def _bond_obj_copy(code: str):
    obj = bond_universe.get(code)
    if obj is None:
        return None
    with _bond_locks[code]:
        return copy.copy(obj)


def _safe_settle(settle: Optional[str]) -> Optional[str]:
    if settle is None:
        return None
    s = settle.strip()
    if not s:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return None


def settlement_date_str(plazo: str) -> Optional[str]:
    import rentafija

    if str(plazo).upper() == "CI":
        d = rentafija.n_dias_laborales(date.today(), 0)
        return d.strftime("%d/%m/%Y")
    return None


# ── Index applicable values ──────────────────────────────────────────────


def _bench_pct(idx_name: Optional[str]) -> float:
    """Avg of the last 5 BCRA observations for TAMAR / BADLAR (in %)."""
    if not idx_name:
        return float("nan")
    import rentafija

    inp = rentafija.inputs
    try:
        if idx_name == "BADLAR":
            return float(inp.get("badlar", pd.DataFrame()).tail(5).get("BADLAR", pd.Series()).mean())
        if idx_name == "TAMAR":
            return float(inp.get("tamar", pd.DataFrame()).tail(5).get("TAMAR", pd.Series()).mean())
    except Exception:  # noqa: BLE001
        return float("nan")
    return float("nan")


def _last_series_value(key: str, colname: str) -> Tuple[Optional[Any], float]:
    """Return (fecha, valor) of the most recent row of rentafija.inputs[key].

    Used to expose the CER, UVA and A3500 daily values right at the top
    of the YAS panel so the user can see what number is being applied
    behind a CER/UVA/DLK bond.
    """
    import rentafija

    df = rentafija.inputs.get(key)
    if df is None or len(df) == 0:
        return None, float("nan")
    try:
        last_idx = df.index[-1]
        last_val = float(df.iloc[-1][colname])
        return last_idx, last_val
    except Exception:  # noqa: BLE001
        return None, float("nan")


def index_applied(obj) -> Dict[str, Any]:
    """Identifies the index that prices this bond and returns its current value.

    Output schema:
      kind: "CER" | "UVA" | "FX" | "BENCH" | None
      label: human-readable label for the value card
      value: numeric (CER index, UVA, FX in ARS/USD, or rate in %)
      value_fmt_hint: "decimal" or "percent" (controls template formatter)
      fecha: date of the observation (None if N/A)
    """
    ajuste = (getattr(obj, "ajuste_sobre_capital", "") or "").upper()
    moneda = (getattr(obj, "moneda", "") or "").upper()
    tipo = (getattr(obj, "tipo_tasa_interes", "") or "").upper()
    idx = (getattr(obj, "index", "") or "").upper()

    out = {"kind": None, "label": "", "value": float("nan"), "value_fmt_hint": "decimal", "fecha": None}

    if "CER" in ajuste:
        fecha, val = _last_series_value("CER", "CER")
        if not np.isfinite(val) or fecha is None:
            fecha, val = _last_series_value("cer_proyectado", "CER")
        out.update({"kind": "CER", "label": "CER aplicable", "value": val, "value_fmt_hint": "decimal", "fecha": fecha})
        return out

    if "UVA" in ajuste:
        fecha, val = _last_series_value("UVA", "UVA")
        if not np.isfinite(val) or fecha is None:
            fecha, val = _last_series_value("uva_proyectado", "UVA")
        out.update({"kind": "UVA", "label": "UVA aplicable", "value": val, "value_fmt_hint": "decimal", "fecha": fecha})
        return out

    if "A3500" in ajuste or moneda == "DLK":
        fecha, val = _last_series_value("a3500", "tca3500")
        out.update({"kind": "FX", "label": "FX A3500 aplicable", "value": val, "value_fmt_hint": "decimal", "fecha": fecha})
        return out

    if tipo in ("VARIABLE", "VARIABLE_CAP") and idx in ("TAMAR", "BADLAR"):
        bench = _bench_pct(idx)
        out.update({"kind": "BENCH", "label": f"{idx} aplicable (avg 5d)", "value": bench, "value_fmt_hint": "percent_pp", "fecha": None})
        return out

    return out


# ── TNA convention table ─────────────────────────────────────────────────


def tna_convention(
    obj,
    freq_override: Optional[int] = None,
    base_override: Optional[int] = None,
) -> Tuple[str, Optional[int], Optional[int], str]:
    """Returns (label, freq_days, base_days, formula).

    `formula` is "cap32" for VARIABLE_CAP+TAMAR (capitalized every 32 days)
    and "linear" for the regular `tir_a_tna(tirea, freq, base)` family.
    When the user passes `freq_override` and `base_override` we always
    use `linear` with those values (lets you sanity-check vs an
    alternative convention without touching rentafija).
    """
    if freq_override and base_override:
        return f"{int(freq_override)}/{int(base_override)} custom", int(freq_override), int(base_override), "linear"

    tipo = (getattr(obj, "tipo_tasa_interes", "") or "").upper()
    idx = (getattr(obj, "index", "") or "").upper()
    ajuste = (getattr(obj, "ajuste_sobre_capital", "") or "").upper()
    moneda = (getattr(obj, "moneda", "") or "").upper()

    if tipo == "VARIABLE_CAP" and idx == "TAMAR":
        return "32/365 cap", 32, 365, "cap32"
    if tipo == "VARIABLE":
        return "90/365", 90, 365, "linear"
    if "CER" in ajuste:
        return "180/365", 180, 365, "linear"
    if "UVA" in ajuste:
        return "180/365", 180, 365, "linear"
    if "A3500" in ajuste:
        return "90/365", 90, 365, "linear"
    if moneda == "USD":
        return "180/360", 180, 360, "linear"

    dias = getattr(obj, "dias_remanentes", None)
    if dias and dias > 0:
        return f"{int(dias)}/365", int(dias), 365, "linear"
    return "—", None, None, "linear"


def tna_from_tirea(
    obj,
    tirea: float,
    freq_override: Optional[int] = None,
    base_override: Optional[int] = None,
) -> Tuple[float, str]:
    """Apply the convention from `tna_convention` to convert TIREA → TNA.

    Returns (tna, label). The label is meant to live next to the metric
    title in the UI ("TNA (32/365)" etc.).
    """
    if not np.isfinite(tirea):
        return float("nan"), "—"
    label, freq, base, formula = tna_convention(obj, freq_override, base_override)
    if formula == "cap32":
        return ((1.0 + tirea) ** (32.0 / 365.0) - 1.0) * (365.0 / 32.0), label
    if freq and base:
        try:
            return ((1.0 + tirea) ** (freq / base) - 1.0) * (base / freq), label
        except Exception:  # noqa: BLE001
            return float("nan"), label
    return float(getattr(obj, "tna", np.nan)), label


def tirea_from_tna(
    obj,
    tna: float,
    freq_override: Optional[int] = None,
    base_override: Optional[int] = None,
) -> float:
    """Inverse of `tna_from_tirea` for use in mode=tna / mode=margen."""
    if not np.isfinite(tna):
        return float("nan")
    _label, freq, base, formula = tna_convention(obj, freq_override, base_override)
    if formula == "cap32":
        return (tna * (32.0 / 365.0) + 1.0) ** (365.0 / 32.0) - 1.0
    if freq and base:
        try:
            return (1.0 + tna / (base / freq)) ** (base / freq) - 1.0
        except Exception:  # noqa: BLE001
            return float("nan")
    # Fall back to rentafija convention if we can't pin freq/base.
    from utils import tna_a_tir

    cnv = (
        (obj.vencimiento - obj.fecha_settlement).days
        if getattr(obj, "cnv_tna", None) == "plazo remanente"
        else getattr(obj, "cnv_tna", 365)
    )
    return float(tna_a_tir(tna, int(cnv), int(getattr(obj, "convencion_base", 365))))


# ── Bond meta + cashflows ────────────────────────────────────────────────


def bond_meta(code: str) -> Dict[str, Any]:
    obj = bond_universe.get(code)
    if obj is None:
        return {}
    return {
        "codigo": getattr(obj, "codigo", code),
        "nombre": getattr(obj, "nombre_security", code),
        "moneda": getattr(obj, "moneda", ""),
        "vencimiento": getattr(obj, "vencimiento", None),
        "emision": getattr(obj, "emision", None),
        "tipo_tasa_interes": getattr(obj, "tipo_tasa_interes", ""),
        "index": getattr(obj, "index", "") or "",
        "ajuste_sobre_capital": getattr(obj, "ajuste_sobre_capital", "") or "",
        "callable": getattr(obj, "callable", False),
        "calificacion": getattr(obj, "calificacion", ""),
        "frecuencia": getattr(obj, "frecuencia_pago_cupon", ""),
        "convencion_base": getattr(obj, "convencion_base", ""),
        "quote_price_cnv": getattr(obj, "quote_price_cnv", ""),
        "cupon_spread": getattr(obj, "cupon_spread", ""),
        "tipo_amortizacion": getattr(obj, "tipo_amortizacion", ""),
        "legislacion": getattr(obj, "legislacion", ""),
    }


def _cashflows_from_obj(obj, limit: int = 40) -> List[Dict[str, Any]]:
    """Return the per-coupon cashflow as a list of dicts.

    Uses `obj.cashflow_cpn` (post-settlement), capped at `limit` rows so
    we don't dump 100 lines for high-coupon-count bonds. We also expose
    the payment date (`cashflow_pmt`) so the template can show both.
    """
    cpn = getattr(obj, "cashflow_cpn", None)
    pmt = getattr(obj, "cashflow_pmt", None)
    if cpn is None or len(cpn) == 0:
        return []
    rows: List[Dict[str, Any]] = []
    try:
        cpn_iter = cpn.head(limit).reset_index(drop=True)
        pmt_iter = pmt.head(limit).reset_index(drop=True) if pmt is not None else None
        for i, row in cpn_iter.iterrows():
            pmt_date = None
            if pmt_iter is not None and i < len(pmt_iter):
                try:
                    pmt_date = pmt_iter.iloc[i]["Fechas"]
                except Exception:  # noqa: BLE001
                    pmt_date = None
            rows.append(
                {
                    "fecha_cpn": row.get("Fechas"),
                    "fecha_pmt": pmt_date,
                    "intereses": float(row.get("Intereses", float("nan"))),
                    "amortizacion": float(row.get("Amortización", float("nan"))),
                    "ajuste": float(row.get("Ajuste", float("nan"))),
                    "total": float(row.get("Total", float("nan"))),
                }
            )
    except Exception:  # noqa: BLE001
        logger.exception("[pricing] cashflow extraction failed")
        return []
    return rows


# ── Main entry point ─────────────────────────────────────────────────────


def compute_metrics(
    code: str,
    mode: str,
    value: float,
    settle: Optional[str] = None,
    fx_override: Optional[float] = None,
    freq_override: Optional[int] = None,
    base_override: Optional[int] = None,
    include_cashflows: bool = True,
) -> Dict[str, Any]:
    """Run a YAS calc end-to-end and return numerics + ticket + cashflow.

    Modes:
      precio  → value is price as % of par (e.g. 87.30)
      tir     → value is TIREA in decimal (e.g. 0.42)
      tna     → value is TNA in decimal, inverted with `tirea_from_tna`
      margen  → spread over benchmark; TNA target = bench/100 + margen
    """
    import rentafija

    base = dict(NAN_METRICS)
    base["codigo"] = code
    base["mode"] = mode
    base["mode_value"] = value
    base["error"] = None
    base["freq_override"] = freq_override
    base["base_override"] = base_override

    obj = _bond_obj_copy(code)
    if obj is None:
        base["error"] = f"Bono '{code}' no encontrado."
        return base

    canonical_settle = _safe_settle(settle)
    base["fecha_settlement_input"] = canonical_settle

    if fx_override is not None:
        try:
            fecha_hoy = date.today().isoformat()
            rentafija.inputs["a3500"].loc[fecha_hoy, "tca3500"] = float(fx_override)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[pricing] fx_override inject failed: %s", exc)

    try:
        if mode == "precio":
            obj.calcula_tirea(float(value) / 100.0, canonical_settle)
            obj.calcula_intereses_corridos(canonical_settle)
        elif mode == "tir":
            obj.calcula_precio(float(value), canonical_settle)
            obj.calcula_intereses_corridos(canonical_settle)
        elif mode == "tna":
            obj.generate_cashflows(canonical_settle)
            tir = tirea_from_tna(obj, float(value), freq_override, base_override)
            obj.calcula_precio(tir, canonical_settle)
            obj.calcula_intereses_corridos(canonical_settle)
        elif mode == "margen":
            idx_name = getattr(obj, "index", None)
            bench_pct = _bench_pct(idx_name)
            ajuste = bench_pct if np.isfinite(bench_pct) else 0.0
            tna_target = (ajuste / 100.0) + float(value)
            obj.generate_cashflows(canonical_settle)
            tir = tirea_from_tna(obj, tna_target, freq_override, base_override)
            obj.calcula_precio(tir, canonical_settle)
            obj.calcula_intereses_corridos(canonical_settle)
        else:
            base["error"] = f"Modo desconocido: {mode!r}"
            return base
    except Exception as exc:  # noqa: BLE001
        # debug-level: a single matured or quirky bond on a 100+ row
        # curve must not flood the logs with stack traces every poll.
        # YAS callers that need the full trace can re-enable DEBUG.
        logger.debug("[pricing] %s mode=%s value=%s failed: %s", code, mode, value, exc)
        base["error"] = f"{type(exc).__name__}: {exc}"
        return base

    tirea = float(getattr(obj, "tirea", np.nan))
    tna_raw = float(getattr(obj, "tna", np.nan))
    tna, tna_label = tna_from_tirea(obj, tirea, freq_override, base_override)
    tem = (1 + tirea) ** (30 / 360) - 1 if np.isfinite(tirea) else float("nan")
    try:
        duration = float(obj.calcula_duration(tirea, canonical_settle)) if np.isfinite(tirea) else float("nan")
    except Exception:  # noqa: BLE001
        duration = float("nan")
    paridad = float(getattr(obj, "paridad", np.nan))
    precio = float(getattr(obj, "precio", np.nan))
    precio_clean = float(getattr(obj, "precio_clean", np.nan))
    ic = float(getattr(obj, "intereses_corridos", np.nan))
    dd = getattr(obj, "dias_corridos", np.nan)
    drem = getattr(obj, "dias_remanentes", np.nan)
    vr = float(getattr(obj, "valor_residual", np.nan))
    vt = float(getattr(obj, "valor_tecnico", np.nan))
    fl = getattr(obj, "fecha_settlement", None)

    idx_name = getattr(obj, "index", None)
    tipo = getattr(obj, "tipo_tasa_interes", None)
    margen_tna = float("nan")
    bench_pct = float("nan")
    if tipo in ("VARIABLE", "VARIABLE_CAP") and idx_name:
        bench_pct = _bench_pct(idx_name)
        if np.isfinite(bench_pct):
            if tipo == "VARIABLE_CAP" and np.isfinite(tirea):
                tna_eq = ((1.0 + tirea) ** (32.0 / 365.0) - 1.0) * (365.0 / 32.0)
                margen_tna = tna_eq - bench_pct / 100.0
            elif tipo == "VARIABLE" and np.isfinite(tna):
                margen_tna = tna - bench_pct / 100.0

    precio_pct = precio * 100.0 if np.isfinite(precio) else float("nan")
    precio_clean_pct = precio_clean * 100.0 if np.isfinite(precio_clean) else float("nan")

    idx_info = index_applied(obj)
    cashflows = _cashflows_from_obj(obj) if include_cashflows else []

    base.update(
        {
            "tirea": tirea,
            "tna": tna,
            "tna_raw": tna_raw,
            "tna_convention_label": tna_label,
            "tem": tem,
            "duration": duration,
            "paridad": paridad,
            "margen_tna": margen_tna,
            "precio_pct": precio_pct,
            "precio_clean_pct": precio_clean_pct,
            "precio": precio,
            "precio_clean": precio_clean,
            "intereses_corridos": ic,
            "dias_corridos": dd,
            "dias_remanentes": drem,
            "valor_residual": vr,
            "valor_tecnico": vt,
            "fecha_settlement": fl,
            "tipo_tasa_interes": tipo or "",
            "index": idx_name or "",
            "benchmark_pct": bench_pct,
            "index_applied": idx_info,
            "cashflows": cashflows,
        }
    )
    return base


# ── Curve-row helper (cached) ────────────────────────────────────────────

from backend.cache import LockedTTLCache  # noqa: E402  (avoid top circular)

# Curve rows poll every 5 s. We bucket the price (rounded to 2 decimals)
# and TTL at 20 s so steady polling NEVER hits a cold cache mid-session
# — only the very first request for a curve pays the compute cost. The
# background warmup daemon (next step) will keep the cache hot ahead of
# the first user click too.
_curve_metrics_cache = LockedTTLCache(maxsize=8192, ttl=20)


def metrics_for_market_price(
    code: str,
    last_price_pct: Optional[float],
    settle: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Cheap variant for curve tables: returns the same shape as
    `compute_metrics` for a market price, cached with a short TTL.

    Returns None when there's no usable price (no live data, broker
    offline, etc.) or when the calc raised — the template renders
    dashes. A matured / non-quoted bond should never bring the page
    down because of one bad row.
    """
    if last_price_pct is None:
        return None
    try:
        v = float(last_price_pct)
    except (TypeError, ValueError):
        return None
    if not (v > 0 and v < 1000):  # sanity: bond prices live in 5-500 %
        return None

    bucket = round(v, 2)
    key = (code, bucket, settle or "")

    def _factory() -> Dict[str, Any]:
        try:
            return compute_metrics(
                code=code,
                mode="precio",
                value=bucket,
                settle=settle,
                include_cashflows=False,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("[pricing] metrics_for_market_price(%s, %s) failed: %s", code, bucket, exc)
            return {"error": str(exc)}

    res = _curve_metrics_cache.get_or_compute(key, _factory)
    if res.get("error"):
        return None
    return res


def ticket_rows(metrics: Dict[str, Any], nominales: float = 1_000_000.0) -> Dict[str, Any]:
    precio = metrics.get("precio", float("nan"))
    precio_clean = metrics.get("precio_clean", float("nan"))
    ic = metrics.get("intereses_corridos", float("nan"))
    vr = metrics.get("valor_residual", float("nan"))
    vn = 100.0
    try:
        monto_total = nominales * float(precio)
    except (TypeError, ValueError):
        monto_total = float("nan")
    try:
        principal = nominales * float(precio_clean) * float(vr) / vn
    except (TypeError, ValueError, ZeroDivisionError):
        principal = float("nan")
    try:
        interes = nominales * float(ic)
    except (TypeError, ValueError):
        interes = float("nan")

    return {
        "vn_ticket": nominales,
        "monto_total": monto_total,
        "principal": principal,
        "interes": interes,
    }
