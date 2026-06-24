"""Escenario multi-activo — retorno esperado EN PESOS por categoría.

Parte las curvas (Tasa fija, CER, DLK, TAMAR, Globales, Bonares) en buckets por
duration (corto/medio/largo donde aplica) y, para un horizonte y un escenario de
salida (Exit YTM por categoría, con pendiente opcional por duration), calcula el
total return EN PESOS de cada bono descompuesto en:

    Carry (rosa)               = (1+carry+ajuste)·(1+fx) − 1   (cupón/rolldown +
                                 proyección CER/UVA/deva A3500 + apreciación CCL/MEP)
    Ganancia de capital (azul) = TR_pesos − Carry              (efecto precio)
    Retorno Total (punto)      = TR_pesos = (1+TR_nativo)·(1+fx) − 1

donde `TR_nativo = carry+compresión+ajuste` lo da `total_return._bond_tr` sobre la
ficha NATIVA del bono (pesos para ARS, USD/USB para hard-dollar) y `fx` es la
proyección de deva de la pata (0 en ARS, CCL en globales, MEP en bonares). El
dólar-linked NO lleva overlay: su deva ya es el `ajuste` A3500 (deva + margen).

Columnas extra, como el Excel del usuario:
    Neto de costo de fondeo = (1+TR_pesos)/(1+caución_al_plazo) − 1
    Total Return neto de FX = (1+TR_pesos)/(1+CCL_proy)        − 1   (rinde en CCL)

Núcleo reusado de `services.total_return` (→ `rentafija.calcula_total_return`).
On-demand; el cómputo pesado se cachea por inputs en la route.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from backend.services import total_return as tr


@dataclass(frozen=True)
class Cat:
    key: str           # id interno (también prefijo de los inputs por categoría)
    label: str         # rótulo es-AR
    curve: str         # curva de build_curve_codes
    dur_lo: float      # bucket [dur_lo, dur_hi) sobre la duration inicial
    dur_hi: float
    fx: str            # "" ARS · "ccl" globales (cable) · "mep" bonares (MEP)


# Orden = orden del gráfico/tabla (igual que el Excel del usuario).
CATEGORIES: List[Cat] = [
    Cat("tasa_fija",   "Tasa fija",       "lecap",       0.0, 1.0,   ""),
    Cat("tasa_fija_l", "Tasa fija larga", "lecap",       1.0, 1e9,   ""),
    Cat("cer_corto",   "CER corto",       "cer",         0.0, 0.5,   ""),
    Cat("cer_medio",   "CER medio",       "cer",         0.5, 1.5,   ""),
    Cat("cer_largo",   "CER largo",       "cer",         1.5, 1e9,   ""),
    Cat("dlk",         "DLK",             "dolarlinked", 0.0, 1e9,   ""),
    Cat("tamar",       "TAMAR",           "tamar",       0.0, 1e9,   ""),
    Cat("globales",    "Globales",        "globales",    0.0, 1e9,   "ccl"),
    Cat("bonares",     "Bonares",         "bonares",     0.0, 1e9,   "mep"),
]

CAT_BY_KEY: Dict[str, Cat] = {c.key: c for c in CATEGORIES}


def fx_of(cat: Cat, ccl_proy: float, mep_proy: float) -> float:
    """Proyección de deva de la pata de la categoría (0 si es ARS pura)."""
    if cat.fx == "ccl":
        return ccl_proy
    if cat.fx == "mep":
        return mep_proy
    return 0.0


def in_bucket(cat: Cat, dur: Optional[float]) -> bool:
    return dur is not None and dur == dur and cat.dur_lo <= dur < cat.dur_hi


def exit_ytm(level: float, slope_bps: float, dur: float, anchor: float = 1.0) -> float:
    """Exit YTM (decimal) por bono: nivel plano + pendiente·(dur−anchor).
    slope_bps en bps/año; nivel/level en decimal (0.25 = 25%)."""
    return float(level) + float(slope_bps) / 10000.0 * (float(dur) - float(anchor))


def _vto(code: str):
    from backend.services import bond_universe
    o = bond_universe.get(code)
    return getattr(o, "vencimiento", None) if o is not None else None


def _avg(vals: List[Optional[float]]) -> Optional[float]:
    xs = [float(v) for v in vals if v is not None and v == v]
    return sum(xs) / len(xs) if xs else None


def compute_category(
    cat: Cat,
    rows: List[Dict[str, Any]],
    y1_by_code: Dict[str, float],
    fx_proy: float,
    ccl_proy: float,
    cauc: float,
    terminal: str,
    settle: str,
) -> Dict[str, Any]:
    """Filas de TR EN PESOS por bono de la categoría + fila resumen (promedio
    simple). `rows` = filas de `_rows_for` ya filtradas al bucket de duration."""
    sd, td = tr._parse_d(settle), tr._parse_d(terminal)
    out: List[Dict[str, Any]] = []
    for r in rows:
        code = r.get("code")
        y0 = r.get("tirea")
        y1 = y1_by_code.get(code)
        if not code or y0 is None or y0 != y0 or y1 is None or y1 != y1:
            continue
        res = tr._bond_tr(code, y0, y1, terminal, settle, sd, td, r.get("duration"))
        if not res:
            continue
        carry, comp, aj, trn = res["carry"], res["compresion"], res["ajuste"], res["tr_total"]
        peso = (1.0 + trn) * (1.0 + fx_proy) - 1.0
        pink = (1.0 + carry + aj) * (1.0 + fx_proy) - 1.0   # Carry (income + deva/FX)
        blue = peso - pink                                  # Ganancia de capital
        neto_fondeo = (1.0 + peso) / (1.0 + cauc) - 1.0
        neto_fx = (1.0 + peso) / (1.0 + ccl_proy) - 1.0 if (1.0 + ccl_proy) else None
        out.append({
            "code": code, "vto": _vto(code), "price": r.get("px_calc"),
            "y0": y0, "dur0": r.get("duration"), "y1": y1,
            "carry": pink, "capital": blue, "total": peso,
            "neto_fondeo": neto_fondeo, "neto_fx": neto_fx,
        })
    out.sort(key=lambda x: (x["dur0"] is None, x["dur0"] or 0.0))
    summary = {
        "y0": _avg([r["y0"] for r in out]), "dur0": _avg([r["dur0"] for r in out]),
        "y1": _avg([r["y1"] for r in out]), "carry": _avg([r["carry"] for r in out]),
        "capital": _avg([r["capital"] for r in out]), "total": _avg([r["total"] for r in out]),
        "neto_fondeo": _avg([r["neto_fondeo"] for r in out]),
        "neto_fx": _avg([r["neto_fx"] for r in out]),
    } if out else None
    return {"key": cat.key, "label": cat.label, "fx_proy": fx_proy,
            "rows": out, "summary": summary, "n": len(out)}


def chart_from_categories(cats: List[Dict[str, Any]], **kw) -> Optional[Dict[str, Any]]:
    """Gráfico de columnas apiladas a nivel CATEGORÍA (como el Excel): una barra
    por categoría con Carry (rosa) + Ganancia de capital (azul) y punto = total.
    Reusa `total_return.bar_chart` (misma escala/clases que el cuadro por-curva)."""
    items = [{
        "label": c["label"],
        "carry": (c["summary"] or {}).get("carry") or 0.0,
        "capital": (c["summary"] or {}).get("capital") or 0.0,
        "total": (c["summary"] or {}).get("total"),
    } for c in cats if c.get("summary")]
    return tr.bar_chart(items, **kw)
