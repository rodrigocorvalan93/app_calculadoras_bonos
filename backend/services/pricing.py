"""YAS pricing service.

Ported from `OMSweb_app._ticket_numeric` (the legacy Streamlit panel). It
runs the four input modes (precio / tir / tna / margen) through
`rentafija.Bono` and returns a dict of raw numerics for the templates.

Thread-safety: `rentafija.Bono` instances in `especies` are singletons,
and `calcula_tirea` mutates `self.tirea`, `self.cashflow_cpn`,
`self.fecha_settlement`, etc. With 4-5 tabs computing different prices for
the same code in parallel, they would clobber each other. We follow the
legacy pattern: a per-code lock + `copy.copy()` of the bond object before
mutating it (`OMSweb_app._bond_obj_copy`).

The Margen TNA formula for VARIABLE_CAP follows the fix in commit 0106d25:
`((1 + TIREA)^(32/365) - 1) * (365/32) - bench/100` (typical for dual
TAMAR like TXMJ9v). For VARIABLE it's the simple `TNA - bench/100`.
"""
from __future__ import annotations

import copy
import logging
import threading
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Dict, Optional

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
    "precio": float("nan"),
    "precio_clean": float("nan"),
    "intereses_corridos": float("nan"),
    "dias_corridos": float("nan"),
    "dias_remanentes": float("nan"),
    "valor_residual": float("nan"),
    "valor_tecnico": float("nan"),
}


def _bond_obj_copy(code: str):
    """Thread-safe shallow copy of a bond singleton."""
    obj = bond_universe.get(code)
    if obj is None:
        return None
    with _bond_locks[code]:
        return copy.copy(obj)


def _safe_settle(settle: Optional[str]) -> Optional[str]:
    """Accept '' / None / 'DD/MM/YYYY' / 'YYYY-MM-DD'. Return canonical DD/MM/YYYY or None."""
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
    """Default settlement for the chosen plazo (24hs or CI).

    Mirrors `OMSweb_app._settlement_date_str`. For 24hs we return None and
    let rentafija fall back to its own default (T+plazo_habitual). For CI
    we explicitly use today's business date.
    """
    import rentafija

    if str(plazo).upper() == "CI":
        d = rentafija.n_dias_laborales(date.today(), 0)
        return d.strftime("%d/%m/%Y")
    return None


def _bench_pct(idx_name: Optional[str]) -> float:
    """Mean of the last 5 BCRA observations for TAMAR / BADLAR (in %)."""
    if not idx_name:
        return float("nan")
    import rentafija

    inp = rentafija.inputs
    try:
        if idx_name == "BADLAR":
            return float(
                inp.get("badlar", pd.DataFrame())
                .tail(5)
                .get("BADLAR", pd.Series())
                .mean()
            )
        if idx_name == "TAMAR":
            return float(
                inp.get("tamar", pd.DataFrame())
                .tail(5)
                .get("TAMAR", pd.Series())
                .mean()
            )
    except Exception:  # noqa: BLE001
        return float("nan")
    return float("nan")


def tna_from_obj(obj, tirea: float) -> float:
    """TNA según la convención que corresponde al tipo de bono.

    Reemplaza a `obj.tna` (que rentafija calcula con cnv_tna/convencion_base
    naturales del bono) cuando esa fórmula no coincide con la convención
    de mercado. Tabla de detección (en orden, primer match gana):

      VARIABLE_CAP + TAMAR  → cap 32/365 (típico dual TAMAR)
      CER / CER PROYECTADO  → tir_a_tna(TIREA, 180, 365)
      A3500 (DLK)           → tir_a_tna(TIREA, 90, 365)
      moneda == USD         → tir_a_tna(TIREA, 180, 360)
      default               → tir_a_tna(TIREA, días_remanentes, 365)

    El bug del legacy era reportar `obj.tna` para todos los bonos —
    para TXMJ9v eso daba ~51% (1127/360) cuando la convención correcta
    es la cap 32/365 (~31%). El commit 0106d25 arregló el Margen TNA
    pero no la TNA misma; este helper cierra el círculo.
    """
    if not np.isfinite(tirea):
        return float("nan")

    import rentafija

    tipo = (getattr(obj, "tipo_tasa_interes", "") or "").upper()
    idx = (getattr(obj, "index", "") or "").upper()
    ajuste = (getattr(obj, "ajuste_sobre_capital", "") or "").upper()
    moneda = (getattr(obj, "moneda", "") or "").upper()

    try:
        if tipo == "VARIABLE_CAP" and idx == "TAMAR":
            return ((1.0 + tirea) ** (32.0 / 365.0) - 1.0) * (365.0 / 32.0)
        if "CER" in ajuste:
            return float(rentafija.tir_a_tna(tirea, 180, 365))
        if "A3500" in ajuste:
            return float(rentafija.tir_a_tna(tirea, 90, 365))
        if moneda == "USD":
            return float(rentafija.tir_a_tna(tirea, 180, 360))

        dias = getattr(obj, "dias_remanentes", None)
        if dias and dias > 0:
            return float(rentafija.tir_a_tna(tirea, int(dias), 365))
        # Fallback: lo que rentafija haya dejado en self.tna
        return float(getattr(obj, "tna", np.nan))
    except Exception:  # noqa: BLE001
        return float("nan")


def bond_meta(code: str) -> Dict[str, Any]:
    """Static metadata for a bond (no calc — cheap)."""
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
    }


def compute_metrics(
    code: str,
    mode: str,
    value: float,
    settle: Optional[str] = None,
    fx_override: Optional[float] = None,
) -> Dict[str, Any]:
    """Run a YAS calc and return raw numerics + ticket-ish payload.

    mode = 'precio'  → value is price as % of par (e.g. 87.30)
    mode = 'tir'     → value is TIREA in decimal (e.g. 0.42)
    mode = 'tna'     → value is TNA in decimal (e.g. 0.38), converted to
                       TIREA via tna_a_tir(value, cnv, base)
    mode = 'margen'  → value is spread over benchmark (decimal), summed to
                       benchmark/100 to obtain TNA, then same as 'tna'
    """
    import rentafija
    from utils import tna_a_tir

    base = dict(NAN_METRICS)
    base["codigo"] = code
    base["mode"] = mode
    base["mode_value"] = value
    base["error"] = None

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
            # Para VARIABLE_CAP + TAMAR la TNA reportada usa la fórmula cap
            # 32/365 (no la convencional de rentafija). Invertimos con la
            # misma fórmula para que ingreso ↔ output sean simétricos.
            tipo = getattr(obj, "tipo_tasa_interes", None)
            idx_name = getattr(obj, "index", None)
            obj.generate_cashflows(canonical_settle)
            if tipo == "VARIABLE_CAP" and idx_name == "TAMAR":
                tir = (float(value) * (32.0 / 365.0) + 1.0) ** (365.0 / 32.0) - 1.0
            else:
                cnv = (
                    (obj.vencimiento - obj.fecha_settlement).days
                    if obj.cnv_tna == "plazo remanente"
                    else obj.cnv_tna
                )
                tir = tna_a_tir(float(value), int(cnv), int(obj.convencion_base))
            obj.calcula_precio(tir, canonical_settle)
            obj.calcula_intereses_corridos(canonical_settle)
        elif mode == "margen":
            # Invertir la fórmula del Margen TNA para llegar al TIREA.
            # VARIABLE_CAP + TAMAR: margen + bench/100 = ((1+TIREA)^(32/365)-1)*(365/32)
            #                       → TIREA = ((tna_cap*32/365)+1)^(365/32) - 1
            # VARIABLE / VARIABLE_CAP otros: tna = margen + bench/100, luego TIREA via tna_a_tir.
            idx_name = getattr(obj, "index", None)
            tipo = getattr(obj, "tipo_tasa_interes", None)
            bench_pct = _bench_pct(idx_name)
            ajuste = bench_pct if np.isfinite(bench_pct) else 0.0
            tna_target = (ajuste / 100.0) + float(value)
            obj.generate_cashflows(canonical_settle)
            if tipo == "VARIABLE_CAP" and idx_name == "TAMAR":
                tir = (tna_target * (32.0 / 365.0) + 1.0) ** (365.0 / 32.0) - 1.0
            else:
                cnv = (
                    (obj.vencimiento - obj.fecha_settlement).days
                    if obj.cnv_tna == "plazo remanente"
                    else obj.cnv_tna
                )
                tir = tna_a_tir(tna_target, int(cnv), int(obj.convencion_base))
            obj.calcula_precio(tir, canonical_settle)
            obj.calcula_intereses_corridos(canonical_settle)
        else:
            base["error"] = f"Modo desconocido: {mode!r}"
            return base
    except Exception as exc:  # noqa: BLE001
        logger.exception("[pricing] %s mode=%s value=%s failed", code, mode, value)
        base["error"] = f"{type(exc).__name__}: {exc}"
        return base

    tirea = float(getattr(obj, "tirea", np.nan))
    # TNA según la convención del tipo de bono (no la `obj.tna` cruda
    # de rentafija, que para VARIABLE_CAP TAMAR daba ~51% en lugar de
    # ~31%). Ver `tna_from_obj` para la tabla de detección.
    tna_raw = float(getattr(obj, "tna", np.nan))
    tna = tna_from_obj(obj, tirea)
    tem = (1 + tirea) ** (30 / 360) - 1 if np.isfinite(tirea) else float("nan")
    try:
        duration = (
            float(obj.calcula_duration(tirea, canonical_settle))
            if np.isfinite(tirea)
            else float("nan")
        )
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

    # Margen TNA — replicates rentafija.genera_ticket / _ticket_numeric
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

    base.update(
        {
            "tirea": tirea,
            "tna": tna,
            "tna_raw": tna_raw,  # rentafija crudo (para debug)
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
        }
    )
    return base


def ticket_rows(metrics: Dict[str, Any], nominales: float = 1_000_000.0) -> Dict[str, Any]:
    """Build the ticket rows (Nombre/Vto/Precio/Monto/etc.) from a metrics dict.

    Doesn't touch the bond object — uses values already computed by
    `compute_metrics`. Returns numerics; formatting is done in the
    template via the `ar_*` filters.
    """
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
