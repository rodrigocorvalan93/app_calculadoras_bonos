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
  ajuste contains "A3500" (DLK)    → 90/360 corporativo · 90/365 soberano (linear)
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

from backend.locale_ar import hoy_ba
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


def refresh_floater_coupons() -> int:
    """Recomputa el cupón de TODOS los floaters (TAMAR/BADLAR) del universo
    desde `rentafija.inputs` fresco. El cupón se congela en `Bono.__init__` al
    importar especies; sin esto, tras `inputs.refresh()` un server de varios
    días seguía priceando floaters con la proyección del boot (ALTA de la
    auditoría). Muta el SINGLETON bajo el mismo lock per-code que usa
    `_bond_obj_copy`, así ninguna copia en vuelo se lleva un objeto a medio
    escribir. Llamar desde un thread (hace pandas), nunca en el event loop.
    Devuelve cuántos bonos recomputó."""
    n = 0
    for code in bond_universe.all_codes():
        meta = bond_meta(code) or {}
        if (meta.get("tipo_tasa_interes") or "").upper() not in ("VARIABLE", "VARIABLE_CAP"):
            continue
        obj = bond_universe.get(code)
        if obj is None or not hasattr(obj, "recalcula_cupon_variable"):
            continue
        try:
            with _bond_locks[code]:
                obj.recalcula_cupon_variable()
            n += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("[pricing] recalcula_cupon_variable(%s) falló: %s", code, exc)
    return n


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
    """Fecha de liquidación EXPLÍCITA de la pestaña: CI → hoy hábil, 24hs → t+1
    hábil (fecha BA). Antes 24hs devolvía None y compute_metrics caía al default
    de la ficha (`plazo_habitual_liquidacion`): para una ficha con habitual ≠ 1,
    la TIR de la tabla (y0) y el carry de TR/Escenario (que fuerzan t+1) usaban
    fechas de liquidación DISTINTAS → descomposición carry/compresión
    internamente inconsistente. Ahora 24hs es t+1 para todos, igual que opera
    BYMA. Plazos desconocidos siguen devolviendo None (default de la ficha)."""
    import rentafija

    p = str(plazo).upper()
    if p == "CI":
        return rentafija.n_dias_laborales(hoy_ba(), 0).strftime("%d/%m/%Y")
    if p == "24HS":
        return rentafija.n_dias_laborales(hoy_ba(), 1).strftime("%d/%m/%Y")
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


# ── FX aplicable a DLK (A3500 cierre vs mayorista intradía) ─────────────────
# Durante la rueda, la serie A3500 tiene el dato de AYER (el BCRA publica el
# del día a la tarde) y el mercado valúa los DLK contra el mayorista del día
# (SIOPEL). Regla: serie con fecha de HOY (cierre ya publicado) manda; si no,
# intradía de HOY si existe; si no, la serie (último dato). Cacheado 2 s —
# las tablas de curvas lo consultan por fila. (El cache se instancia más
# abajo, junto a los otros: LockedTTLCache se importa diferido por un ciclo.)


def a3500_aplicable() -> Dict[str, Any]:
    """{'value', 'fuente' ('A3500'|'SIOPEL'|'DLR/SPOT'), 'fecha', 'intradia'}."""
    def _compute() -> Dict[str, Any]:
        fecha, serie = _last_series_value("a3500", "tca3500")
        out = {"value": serie if np.isfinite(serie) else float("nan"),
               "fuente": "A3500", "fecha": fecha, "intradia": False}
        from backend.config import settings
        if not settings.dlk_fx_intradia:
            return out
        # ¿La serie ya tiene el A3500 de HOY? → es el cierre oficial, manda.
        try:
            f = fecha.date() if hasattr(fecha, "date") else fecha
            if f is not None and f >= hoy_ba():
                return out
        except Exception:  # noqa: BLE001
            pass
        from backend.services import dolares
        intra = dolares.oficial_intradia_hoy()
        if intra is not None:
            return {"value": intra["last"], "fuente": intra["source"],
                    "fecha": None, "intradia": True}
        return out

    return _a3500_aplicable_cache.get_or_compute("v", _compute)


def _dlk_fx_auto() -> Optional[float]:
    """Override automático para un DLK sin TC custom: el mayorista intradía
    de HOY cuando el A3500 del día todavía no está publicado. None = usar la
    serie (sin override), el comportamiento de siempre."""
    a = a3500_aplicable()
    if a.get("intradia") and a.get("value") == a.get("value"):
        return float(a["value"])
    return None


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
        # TC custom del usuario (YAS): el card debe mostrar el FX que REALMENTE
        # priceó los flujos, no el último de la serie — antes las cuentas
        # usaban el override pero el card seguía mostrando el cierre oficial.
        ov = getattr(obj, "_a3500_override", None)
        if ov is not None and getattr(obj, "_a3500_custom", False):
            out.update({"kind": "FX", "label": "FX A3500 aplicable (TC custom)",
                        "value": float(ov), "value_fmt_hint": "decimal", "fecha": None})
            return out
        a = a3500_aplicable()
        label = ("FX aplicable — mayorista intradía (" + a["fuente"] + ")"
                 if a.get("intradia") else "FX A3500 aplicable (cierre)")
        out.update({"kind": "FX", "label": label, "value": a["value"],
                    "value_fmt_hint": "decimal", "fecha": a.get("fecha")})
        return out

    if tipo in ("VARIABLE", "VARIABLE_CAP") and idx in ("TAMAR", "BADLAR"):
        bench = _bench_pct(idx)
        out.update({"kind": "BENCH", "label": f"{idx} aplicable (avg 5d)", "value": bench, "value_fmt_hint": "percent_pp", "fecha": None})
        return out

    return out


# ── TNA convention table ─────────────────────────────────────────────────


def _is_hard_dollar(obj) -> bool:
    """A bond whose cashflows are in hard USD → 180/360 TNA, *regardless of
    which dollar leg it's quoted/settled in*.

    `Moneda` now encodes the FX quote leg (USD = cable, USB = MEP), so we
    can't key hard-dollar off `moneda == "USD"` alone — a USB (MEP) bond,
    or a hard-dollar bond quoted in pesos, is still USD-cashflow and must
    keep 180/360. Detect from the leg currency OR the classification /
    industria. Safe to be broad: the CER / UVA / A3500 / VARIABLE branches
    run *before* this one, so DLK and ARS-rate bonds never reach it.
    """
    moneda = (getattr(obj, "moneda", "") or "").upper()
    if moneda in ("USD", "USB"):
        return True
    clas = (getattr(obj, "clasificacion", "") or "").upper()
    ind = (getattr(obj, "industria", "") or "").upper()
    return "HARD DOLAR" in clas or "USD" in ind


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

    if tipo == "VARIABLE_CAP" and idx == "TAMAR":
        return "32/365 cap", 32, 365, "cap32"
    if tipo == "VARIABLE":
        return "90/365", 90, 365, "linear"
    if "CER" in ajuste:
        return "180/365", 180, 365, "linear"
    if "UVA" in ajuste:
        return "180/365", 180, 365, "linear"
    if "A3500" in ajuste:
        # El mercado cotiza los DLK corporativos en 90/360 (aunque el cupón
        # devengue actual/360); los soberanos se mantienen en 90/365.
        clas = (getattr(obj, "clasificacion", "") or "").upper()
        if "CORPORATIVO" in clas:
            return "90/360", 90, 360, "linear"
        return "90/365", 90, 365, "linear"
    if _is_hard_dollar(obj):
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


_meta_cache: Dict[str, Dict[str, Any]] = {}


def bond_meta(code: str) -> Dict[str, Any]:
    """Metadata estática del bono (no cambia en runtime). Memoizada: en curvas
    anchas se llama 1×/fila/refresh y rearmar 16 getattr cada vez era puro
    overhead. Los callers NO deben mutar el dict — el hot path copia con
    `dict(meta)`; si hace falta modificar, copiar primero."""
    cached = _meta_cache.get(code)
    if cached is not None:
        return cached
    obj = bond_universe.get(code)
    if obj is None:
        return {}
    meta = {
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
    _meta_cache[code] = meta
    return meta


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
    obj_override: Optional[Any] = None,
) -> Dict[str, Any]:
    """Run a YAS calc end-to-end and return numerics + ticket + cashflow.

    Modes:
      precio  → value is price as % of par (e.g. 87.30)
      tir     → value is TIREA in decimal (e.g. 0.42)
      tna     → value is TNA in decimal, inverted with `tirea_from_tna`
      margen  → spread over benchmark; TNA target = bench/100 + margen

    `obj_override`: price an *ad-hoc* `rentafija.Bono` that is NOT in the
    universe (especie ad-hoc: ficha pegada / generada). We `copy.copy` it so
    the caller's instance is never mutated, mirroring `_bond_obj_copy`. The
    whole downstream pipeline (TNA, duration, cashflows, index_applied) is
    reused unchanged — zero coupling to `especies.py`.
    """
    base = dict(NAN_METRICS)
    base["codigo"] = code
    base["mode"] = mode
    base["mode_value"] = value
    base["error"] = None
    base["freq_override"] = freq_override
    base["base_override"] = base_override

    obj = copy.copy(obj_override) if obj_override is not None else _bond_obj_copy(code)
    if obj is None:
        base["error"] = f"Bono '{code}' no encontrado."
        return base

    canonical_settle = _safe_settle(settle)
    # Fecha de liquidación EXPLÍCITA pero no parseable (p. ej. settle_custom de YAS
    # mal tipeado): antes se descartaba en silencio y se valuaba a la fecha default,
    # mostrando métricas creíbles pero a otra fecha. Ahora avisamos en vez de
    # engañar. `settle=None`/"" es el default legítimo y NO entra acá.
    if settle and str(settle).strip() and canonical_settle is None:
        base["error"] = f"Fecha de liquidación inválida: {settle!r}. Usá DD/MM/AAAA."
        return base
    base["fecha_settlement_input"] = canonical_settle

    # What-if de FX (DLK/A3500): override POR-OBJETO sobre la copia per-request, no
    # mutamos el global `rentafija.inputs` (eso corrompía el A3500 de TODO el proceso).
    # `rentafija` lee `getattr(self, '_a3500_override', None)`; la copia es thread-safe.
    if fx_override is not None:
        try:
            obj._a3500_override = float(fx_override)
            # Marca "TC custom del usuario": index_applied muestra ESTE valor
            # en el card de FX (antes las cuentas usaban el override pero el
            # card seguía mostrando el cierre de la serie). El auto-override
            # DLK intradía no la lleva: su card ya muestra el intradía.
            obj._a3500_custom = True
        except (TypeError, ValueError):
            pass
    elif obj_override is None and _bond_index_kind(code) == "a3500":
        # DLK sin TC custom: durante la rueda el mercado valúa contra el
        # mayorista del día (SIOPEL), no contra el A3500 de ayer. El auto-
        # override sólo aplica mientras el A3500 de HOY no está publicado;
        # después manda la serie (cierre). Costo: dict lookup + cache 2 s.
        auto = _dlk_fx_auto()
        if auto is not None:
            obj._a3500_override = auto

    # `calcula_tirea` / `calcula_precio` ya corren `generate_cashflows` +
    # `calcula_intereses_corridos` ADENTRO (rentafija), así que acá no se repiten:
    # cada llamada extra reconstruía los cashflows completos (sin memo) y era puro
    # costo en el hot path. En tna/margen la inversión TNA→TIR necesita
    # `dias_remanentes` ANTES de `tirea_from_tna` (la convención del bucket default
    # es días_remanentes/365 y sólo lo puebla `calcula_intereses_corridos`; con
    # `generate_cashflows` la inversión caía al fallback `cnv_tna` con OTRA base y
    # el round-trip TNA→precio→TNA no era inverso en LECAP/bullets ARS).
    try:
        if mode == "precio":
            obj.calcula_tirea(float(value) / 100.0, canonical_settle)
        elif mode == "tir":
            obj.calcula_precio(float(value), canonical_settle)
        elif mode == "tna":
            obj.calcula_intereses_corridos(canonical_settle)
            tir = tirea_from_tna(obj, float(value), freq_override, base_override)
            obj.calcula_precio(tir, canonical_settle)
        elif mode == "margen":
            idx_name = getattr(obj, "index", None)
            bench_pct = _bench_pct(idx_name)
            if not np.isfinite(bench_pct):
                # Sin serie del benchmark (BCRA caído / índice desconocido) el
                # fallback ajuste=0 produciría un precio/TIR plausible pero
                # errado — mejor un error visible que un número mentiroso.
                base["error"] = (f"Benchmark {idx_name or '?'} sin datos: "
                                 "no se puede pricear por margen.")
                return base
            tna_target = (bench_pct / 100.0) + float(value)
            obj.calcula_intereses_corridos(canonical_settle)
            tir = tirea_from_tna(obj, tna_target, freq_override, base_override)
            obj.calcula_precio(tir, canonical_settle)
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

# Curve rows poll ~1×/s (md-update). La key ya identifica TODO lo que mueve la
# TIR a un precio dado: el bono, el bucket de precio (2 decimales), el settle y
# el fingerprint del índice (A3500/CER/UVA) — más el día (ordinal), que captura
# el rollover de fecha (cambia días_corridos / settlement cuando el proceso cruza
# medianoche). Como la key es exacta, el TTL puede ser LARGO sin servir números
# viejos: con 20 s la entrada expiraba y se recomputaba en ciclo (los hits NO
# refrescan el TTL en LockedTTLCache), y un poll de 1 s pegaba la ventana fría
# antes que el warmup → spike de ~1,26 s por curva ancha cada ~20 s. Con 1 h el
# warmup deja todo caliente de sobra y sólo el 1er cómputo de cada (precio,día)
# paga; un cambio de índice o de bucket entra por la key, no por expiración.
_curve_metrics_cache = LockedTTLCache(maxsize=16384, ttl=3600)

# Bonos ajustados (DLK/CER/UVA): su TIR a un precio dado depende del índice
# (A3500/CER/UVA), no sólo del precio. Si la key del cache no lo incluye, al
# cambiar el índice la TIR queda vieja hasta el TTL (20 s). Metemos el valor del
# índice en la key — leído con un cache corto para que sea barato — así el cambio
# se refleja en ~2 s sin perder el cacheo cuando el índice está quieto.
_index_kind: Dict[str, str] = {}                       # code → "a3500"/"cer"/"uva"/"tamar"/"badlar"/"" (estático)
_index_val_cache = LockedTTLCache(maxsize=8, ttl=2)    # valor actual del índice (lectura barata)
_a3500_aplicable_cache = LockedTTLCache(maxsize=2, ttl=2)   # FX aplicable a DLK (cierre vs intradía)
# Errores transitorios de compute_metrics: cache CORTO y separado. Si fueran al
# cache grande (TTL 1 h), un fallo puntual sobre un bono no-indexado (fingerprint
# constante) quedaba "pegado" en guiones hasta el rollover de día; sin cachearlos,
# un bono roto permanente se recomputaría (~20 ms) en cada render.
_curve_metrics_err_cache = LockedTTLCache(maxsize=1024, ttl=120)
_INDEX_COLS = {"a3500": ("a3500", "tca3500"), "cer": ("CER", "CER"), "uva": ("UVA", "UVA")}


def _bond_index_kind(code: str) -> str:
    k = _index_kind.get(code)
    if k is None:
        m = bond_meta(code) or {}
        aj = (m.get("ajuste_sobre_capital") or "").upper()
        mon = (m.get("moneda") or "").upper()
        tipo = (m.get("tipo_tasa_interes") or "").upper()
        if "A3500" in aj or mon == "DLK":
            k = "a3500"
        elif "CER" in aj:
            k = "cer"
        elif "UVA" in aj:
            k = "uva"
        elif tipo in ("VARIABLE", "VARIABLE_CAP"):
            # Floaters: la TIR/margen a un precio dado depende del benchmark
            # vivo (últimas obs. BCRA) y de la proyección del cupón. Sin kind,
            # el fingerprint era 0.0 y una TAMAR/BADLAR nueva dejaba margen_tna
            # stale hasta 1 h (TTL) en bonos cuyo precio no se movía.
            k = "tamar" if (m.get("index") or "").upper() == "TAMAR" else "badlar"
        else:
            k = ""
        _index_kind[code] = k
    return k


def _index_fingerprint(kind: str) -> Any:
    if not kind:
        return 0.0
    if kind == "a3500":
        # DLK: el fingerprint es el FX que se APLICA (intradía o serie) — si el
        # SIOPEL tickea, la key del cache de métricas cambia y la TIR se
        # recalcula con el dólar nuevo. SIN memoización extra acá:
        # a3500_aplicable() ya cachea 2 s; el doble cache (esto dentro de
        # _index_val_cache) encadenaba la staleness hasta ~4 s y limpiar un
        # solo cache no invalidaba (bug destapado por la auditoría).
        v = a3500_aplicable().get("value")
        try:
            return round(float(v), 6) if v == v else 0.0
        except (TypeError, ValueError):
            return 0.0

    def _f() -> Any:
        if kind in ("tamar", "badlar"):
            # Huella del floater: benchmark (tail-5 mean, mueve margen_tna) +
            # último valor de la proyección (mueve el cupón → TIR). Cualquiera
            # de los dos cambia tras un refresh de índices → key nueva.
            import rentafija

            col = kind.upper()
            bench = _bench_pct(col)
            try:
                proy = rentafija.inputs.get(f"{kind}_proyectado")
                pv = float(proy[col].iloc[-1]) if proy is not None and len(proy) else 0.0
            except Exception:  # noqa: BLE001
                pv = 0.0
            return (round(bench, 6) if bench == bench else 0.0,
                    round(pv, 6) if pv == pv else 0.0)
        cols = _INDEX_COLS.get(kind)
        if not cols:
            return 0.0
        _, val = _last_series_value(*cols)
        return round(float(val), 6) if np.isfinite(val) else 0.0

    return _index_val_cache.get_or_compute(kind, _f)


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
    # Sanity: descarta sizes/garbage, pero los CER viejos (DICP/PARP/CUAP)
    # cotizan en decenas de miles de pesos por lámina, así que el techo
    # tiene que ser alto. Solo filtramos no-positivos y valores absurdos.
    if not (v > 0 and v < 10_000_000):
        return None

    bucket = round(v, 2)
    # La key incluye el valor del índice (DLK/CER/UVA/floater → un cambio del
    # A3500/CER/UVA/benchmark la invalida) y el día ordinal BA (rollover de fecha
    # con settle=None → recomputa con el settlement del día nuevo, no el de ayer).
    key = (code, bucket, settle or "", _index_fingerprint(_bond_index_kind(code)),
           hoy_ba().toordinal())

    # ¿Falló hace <120 s con esta misma key? → guiones sin recomputar (evita
    # martillar un calc roto en cada poll) pero SIN pegar el error 1 h/1 día.
    if _curve_metrics_err_cache.get(key) is not None:
        return None

    def _factory() -> Optional[Dict[str, Any]]:
        try:
            res = compute_metrics(
                code=code,
                mode="precio",
                value=bucket,
                settle=settle,
                include_cashflows=False,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("[pricing] metrics_for_market_price(%s, %s) failed: %s", code, bucket, exc)
            res = {"error": str(exc)}
        if res.get("error"):
            # Al cache corto de errores; devolver None evita que el cache
            # grande (TTL 1 h) lo retenga.
            _curve_metrics_err_cache.get_or_compute(key, lambda: res)
            return None
        return res

    return _curve_metrics_cache.get_or_compute(key, _factory)


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


# ── Total return puntual (ficha YAS) ─────────────────────────────────────────


def tr_puntual(
    code: str,
    mode: str,
    value: float,
    settle: Optional[str] = None,
    tir_salida: Optional[float] = None,
    fecha_salida: Optional[str] = None,
    nominales: float = 1_000_000.0,
    fx_override: Optional[float] = None,
    freq_override: Optional[int] = None,
    base_override: Optional[int] = None,
) -> Dict[str, Any]:
    """Total return puntual de la ficha YAS, vía `Bono.calcula_total_return`.

    Entrada = el estado actual de la ficha (mode/value/settle, con los mismos
    overrides de FX/convención); salida = `tir_salida` (TIREA decimal, default
    flat: la misma TIR de entrada) en `fecha_salida` (DD/MM/AAAA, default
    settle + 90 días corridos; puede ser ≥ vencimiento → hold to maturity,
    donde la tasa de salida no juega). Devuelve el desglose del período:
    px inicial/final, P&L de capital, interés y amortización cobrados (con
    ajuste de capital aplicado), TR directo / TEA / TNA y montos en $ por
    `nominales`. Cupones SIN reinversión (metodología del legacy). GIL-bound
    (~2 calcs completos): SIEMPRE correr en un executor, nunca en el loop."""
    out: Dict[str, Any] = {"error": None, "codigo": code}

    m = compute_metrics(code=code, mode=mode, value=value, settle=settle,
                        fx_override=fx_override, freq_override=freq_override,
                        base_override=base_override, include_cashflows=False)
    if m.get("error"):
        out["error"] = m["error"]
        return out
    tir_ini = m.get("tirea")
    if tir_ini is None or not np.isfinite(tir_ini):
        out["error"] = "La ficha no produce una TIREA finita — no se puede proyectar el total return."
        return out

    f_settle = m.get("fecha_settlement")            # date (del calc de entrada)
    if f_settle is None:
        out["error"] = "Sin fecha de liquidación en la ficha."
        return out

    salida_flat = tir_salida is None or not np.isfinite(tir_salida)
    tir_fin = float(tir_ini) if salida_flat else float(tir_salida)

    from datetime import timedelta
    canonical_salida = _safe_settle(fecha_salida)
    if fecha_salida and str(fecha_salida).strip() and canonical_salida is None:
        out["error"] = f"Fecha de salida inválida: {fecha_salida!r}. Usá DD/MM/AAAA."
        return out
    if canonical_salida is None:
        canonical_salida = (f_settle + timedelta(days=90)).strftime("%d/%m/%Y")
    terminal_dt = datetime.strptime(canonical_salida, "%d/%m/%Y").date()
    if terminal_dt <= f_settle:
        out["error"] = (f"La fecha de salida ({canonical_salida}) debe ser posterior "
                        f"a la liquidación ({f_settle.strftime('%d/%m/%Y')}).")
        return out

    obj = _bond_obj_copy(code)
    if obj is None:
        out["error"] = f"Bono '{code}' no encontrado."
        return out
    # Mismos overrides de FX que la ficha (custom o auto-DLK intradía): la
    # entrada del TR tiene que pricear EXACTAMENTE como el ticket de arriba.
    if fx_override is not None:
        try:
            obj._a3500_custom = True
            obj._a3500_override = float(fx_override)
        except (TypeError, ValueError):
            pass
    elif _bond_index_kind(code) == "a3500":
        auto = _dlk_fx_auto()
        if auto is not None:
            obj._a3500_override = auto

    canonical_settle = _safe_settle(settle)
    try:
        df = obj.calcula_total_return(float(tir_ini), tir_fin, canonical_salida, canonical_settle)
        vals = df["Total Return Valores"]
        px_ini = float(vals["Px inicial"])
        px_fin = float(vals["Px final"])
        pnl_cap = float(vals["P&L Capital"])
        cobrado = float(vals["Cupones Cobrados"])
    except Exception as exc:  # noqa: BLE001
        logger.debug("[pricing] tr_puntual(%s) failed: %s", code, exc)
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out
    if not (np.isfinite(px_ini) and px_ini > 0):
        out["error"] = "El precio inicial del período no es finito."
        return out

    # Desglose interés vs capital de los flujos cobrados (mismo filtro que usa
    # calcula_total_return sobre cashflow_cpn_full; Total = (int+amort)·ajuste/VN).
    full = obj.cashflow_cpn_full
    mask = (full["Fechas"] > obj.fecha_settlement) & (full["Fechas"] <= terminal_dt)
    rows = full.loc[mask]
    vn = float(obj.valor_nominal) or 100.0
    interes = float((rows["Intereses"] * rows["Ajuste"]).sum()) / vn
    capital = float((rows["Amortización"] * rows["Ajuste"]).sum()) / vn
    flujos = [{
        "fecha": f.strftime("%d/%m/%Y") if hasattr(f, "strftime") else str(f),
        "interes_pct": float(i) * float(a) / vn * 100.0,
        "capital_pct": float(am) * float(a) / vn * 100.0,
        "total_pct": float(t) * 100.0,
        "total_m": float(t) * nominales,
    } for f, i, am, a, t in zip(rows["Fechas"], rows["Intereses"], rows["Amortización"],
                                rows["Ajuste"], rows["Total"])]

    dias = (terminal_dt - obj.fecha_settlement).days
    tr = (pnl_cap + cobrado) / px_ini
    tea = (1.0 + tr) ** (365.0 / dias) - 1.0 if dias > 0 and tr > -1.0 else float("nan")
    tna = tr * 365.0 / dias if dias > 0 else float("nan")
    venc = getattr(obj, "vencimiento", None)
    if isinstance(venc, datetime):                  # Timestamp/datetime → date
        venc = venc.date()
    a_vencimiento = bool(isinstance(venc, date) and terminal_dt >= venc)

    out.update({
        "fecha_entrada": obj.fecha_settlement.strftime("%d/%m/%Y"),
        "fecha_salida": canonical_salida,
        "dias": dias,
        "tir_entrada": float(tir_ini),
        "tir_salida": tir_fin,
        "salida_flat": salida_flat,
        "a_vencimiento": a_vencimiento,
        "px_ini_pct": px_ini * 100.0,
        "px_fin_pct": px_fin * 100.0,
        "pnl_capital_pct": pnl_cap * 100.0,
        "interes_pct": interes * 100.0,
        "capital_pct": capital * 100.0,
        "cobrado_pct": cobrado * 100.0,
        "n_flujos": int(len(flujos)),
        "flujos": flujos,
        "tr": tr,
        "tea": tea,
        "tna": tna,
        "nominales": nominales,
        "monto_ini": px_ini * nominales,
        "monto_fin": px_fin * nominales,
        "interes_m": interes * nominales,
        "capital_m": capital * nominales,
        "cobrado_m": cobrado * nominales,
        "pnl_capital_m": pnl_cap * nominales,
        "pnl_total_m": (pnl_cap + cobrado) * nominales,
    })
    return out
