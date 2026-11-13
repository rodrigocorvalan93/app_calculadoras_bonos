"""Cartera óptima desde un archivo de series históricas (TIR/spreads o precios).

Adaptador entre el upload del usuario y el motor q-Entropy Pooling
(`services/optimizador/engine.py`, adaptado del repo de la tesis
`non_extensive_q_entropy_pooling`).

Flujo (`run()`, pensado para correr en el executor — es CPU-bound):
  1. Parsear el archivo (xlsx/csv) a un DataFrame fechas × tickers.
  2. Detectar la escala (bps / % / decimal) si el invariante es TIR/spread.
  3. Resolver cada ticker contra el universo (`bond_universe.resolve`) y
     buscar su modified duration con `pricing.compute_metrics(mode="tir")`
     a la última TIR de la serie subida.
  4. Mapear el invariante a retornos de precio:  dP/P = -D * dy  (1er orden;
     la convexity de `rentafija` está marcada como dudosa en su docstring y
     no se usa — ver CLAUDE.md "no tocar").
  5. Correr prior MV / EP-Shannon / q-Tsallis-EP y armar el contexto del
     template (filas, dona, métricas, avisos y diagnóstico).

Todo mensaje de error al usuario es un `ValueError` en es-AR.
"""
from __future__ import annotations

import io
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from backend.services.optimizador import engine

MAX_BYTES = 5 * 1024 * 1024
EXTENSIONES = (".xlsx", ".xls", ".csv")
MIN_OBS = 40          # mínimo de observaciones del panel para optimizar
MAX_ACTIVOS = 60      # tope sano para un upload


# ── 1. Parseo del archivo ────────────────────────────────────────────────────

def parse_tabla(nombre: str, data: bytes) -> pd.DataFrame:
    """Archivo subido -> DataFrame con DatetimeIndex y columnas numéricas.

    Formato esperado: primera columna fechas, una columna por ticker.
    CSV: acepta `;` con coma decimal (es-AR) o `,` con punto decimal.
    """
    if len(data) > MAX_BYTES:
        raise ValueError(f"El archivo supera el máximo de {MAX_BYTES // (1024 * 1024)} MB.")
    if not data:
        raise ValueError("El archivo llegó vacío.")
    nombre_l = (nombre or "").lower()
    if not nombre_l.endswith(EXTENSIONES):
        raise ValueError("Formato no soportado: subí un .xlsx o un .csv.")
    try:
        if nombre_l.endswith(".csv"):
            texto = data.decode("utf-8-sig", errors="replace")
            primera = texto.splitlines()[0] if texto.splitlines() else ""
            if primera.count(";") >= 1:
                df = pd.read_csv(io.StringIO(texto), sep=";", decimal=",", index_col=0)
            else:
                df = pd.read_csv(io.StringIO(texto), sep=",", index_col=0)
        else:
            df = pd.read_excel(io.BytesIO(data), index_col=0)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"No pude leer el archivo: {exc}") from exc

    if df.shape[1] < 2:
        raise ValueError("Hacen falta al menos 2 columnas de activos además de la fecha.")
    try:
        df.index = pd.to_datetime(df.index, dayfirst=True, errors="raise")
    except Exception as exc:
        raise ValueError(
            "La primera columna tiene que ser la fecha (DD/MM/AAAA o AAAA-MM-DD). "
            f"Detalle: {exc}"
        ) from exc
    df.columns = [str(c).strip() for c in df.columns]
    df = df.apply(pd.to_numeric, errors="coerce")
    df = df.dropna(axis=1, how="all").dropna(axis=0, how="all").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    if df.shape[1] < 2:
        raise ValueError("Después de limpiar quedaron menos de 2 columnas numéricas.")
    if df.shape[1] > MAX_ACTIVOS:
        raise ValueError(f"Demasiados activos ({df.shape[1]}); el tope es {MAX_ACTIVOS}.")
    if len(df) < MIN_OBS:
        raise ValueError(
            f"Muy pocas filas con datos ({len(df)}); hacen falta al menos {MIN_OBS} "
            "observaciones para estimar algo con sentido."
        )
    return df


def detectar_escala(df: pd.DataFrame) -> Tuple[str, float]:
    """Escala de los NIVELES de TIR/spread: ("bps"|"porcentaje"|"decimal", factor
    a decimal). Mediana |nivel| > 50 -> bps; > 0,5 -> %; si no, decimal."""
    med = float(np.nanmedian(np.abs(df.to_numpy(dtype=float))))
    if med > 50.0:
        return "bps", 1e-4
    if med > 0.5:
        return "porcentaje", 1e-2
    return "decimal", 1.0


# ── 2. Duration desde las fichas de la app ───────────────────────────────────

def resolver_duraciones(
    tickers: List[str],
    ultimo_nivel_decimal: Dict[str, float],
) -> Dict[str, Dict[str, object]]:
    """Para cada ticker subido: código de ficha y modified duration valuada a
    la última TIR de la serie. Import tardío para que el motor sea testeable
    sin universo cargado."""
    from backend.services import bond_universe, pricing

    out: Dict[str, Dict[str, object]] = {}
    for t in tickers:
        codigo = bond_universe.resolve(t)
        info: Dict[str, object] = {"codigo": codigo, "duration": None, "error": None}
        if codigo:
            try:
                tir = float(ultimo_nivel_decimal.get(t, float("nan")))
                m = pricing.compute_metrics(codigo, "tir", tir, include_cashflows=False)
                dur = m.get("duration")
                if m.get("error"):
                    info["error"] = str(m["error"])
                elif dur is not None and np.isfinite(float(dur)) and float(dur) > 0:
                    info["duration"] = float(dur)
                else:
                    info["error"] = "la ficha no devolvió duration"
            except Exception as exc:  # una ficha rota no voltea el resto
                info["error"] = str(exc)
        else:
            info["error"] = "sin ficha en el universo"
        out[t] = info
    return out


# ── 3. Ranking del usuario ───────────────────────────────────────────────────

def parse_ranking(texto: str, columnas: List[str]) -> List[int]:
    """"GD35 > GD41 > GD30" (mejor primero, en términos de PRECIO) -> índices
    de columnas. Vacío -> []. Ticker desconocido o repetido -> ValueError."""
    texto = (texto or "").strip()
    if not texto:
        return []
    upper_map = {c.upper(): i for i, c in enumerate(columnas)}
    idx: List[int] = []
    for tok in texto.replace("≥", ">").split(">"):
        tok = tok.strip()
        if not tok:
            continue
        i = upper_map.get(tok.upper())
        if i is None:
            raise ValueError(
                f"El ranking nombra '{tok}', que no es una columna del archivo. "
                f"Columnas disponibles: {', '.join(columnas)}."
            )
        if i in idx:
            raise ValueError(f"El ranking repite '{tok}'.")
        idx.append(i)
    if len(idx) == 1:
        raise ValueError("Un ranking necesita al menos 2 tickers separados por '>'.")
    return idx


# ── 4. Pipeline completo ─────────────────────────────────────────────────────

def run(
    nombre_archivo: str,
    data: bytes,
    invariante: str = "tir",
    q: float = 2.0,
    confianza: float = 1.0,
    max_peso: float = 0.35,
    delta: float = 2.5,
    ranking_texto: str = "",
    max_gap_fill: int = 5,
    duraciones_override: Optional[Dict[str, float]] = None,
) -> Dict[str, object]:
    """Corre todo y devuelve el contexto del partial de resultado."""
    if invariante not in ("tir", "precios"):
        raise ValueError(f"Invariante no reconocido: {invariante!r}")
    if not q > 1.0:
        raise ValueError("q tiene que ser mayor que 1 (con q=2 es la entropía de colisión).")
    if not 0.0 < confianza <= 1.0:
        raise ValueError("La confianza tiene que estar entre 0 y 100%.")
    if not 0.0 < max_peso <= 1.0:
        raise ValueError("El peso máximo por activo tiene que estar entre 0 y 100%.")

    avisos: List[str] = []
    niveles = parse_tabla(nombre_archivo, data)
    niveles = engine.prepare_series(niveles, max_gap_fill=max_gap_fill)
    tickers = list(niveles.columns)

    fichas: Dict[str, Dict[str, object]] = {}
    if invariante == "tir":
        escala_nombre, factor = detectar_escala(niveles)
        niveles_dec = niveles * factor
        delta_y = niveles_dec.diff().iloc[1:]
        ultimo = {t: float(niveles_dec[t].dropna().iloc[-1]) for t in tickers
                  if niveles_dec[t].notna().any()}
        if duraciones_override is not None:
            fichas = {t: {"codigo": None, "duration": float(d), "error": None}
                      for t, d in duraciones_override.items()}
        else:
            fichas = resolver_duraciones(tickers, ultimo)
        sin_dur = [t for t in tickers if not (fichas.get(t) or {}).get("duration")]
        if sin_dur:
            motivos = {t: (fichas.get(t) or {}).get("error") or "sin duration" for t in sin_dur}
            avisos.append(
                "Quedaron afuera por no poder resolver su duration: "
                + "; ".join(f"{t} ({motivos[t]})" for t in sin_dur)
            )
            tickers = [t for t in tickers if t not in sin_dur]
            if len(tickers) < 2:
                raise ValueError(
                    "Con invariante TIR/spread necesito la duration de al menos 2 "
                    "activos y no pude resolverla (" +
                    "; ".join(f"{t}: {motivos[t]}" for t in sin_dur) +
                    "). Revisá los tickers o subí precios en su lugar."
                )
            delta_y = delta_y[tickers]
        dur_vec = np.array([float(fichas[t]["duration"]) for t in tickers])
        completos = delta_y.dropna(axis=0, how="any")
        if len(completos) < MIN_OBS:
            raise ValueError(
                f"Solo {len(completos)} filas tienen dato para todos los activos "
                f"(mínimo {MIN_OBS}). Recortá el panel o revisá los huecos."
            )
        X_inv = completos.to_numpy(dtype=float)
        X_ret = -X_inv * dur_vec[None, :]
        lower_is_better = True
        detalle_invariante = (
            f"cambios de TIR/spread (escala detectada: {escala_nombre}); "
            "mapeo dP/P = -D * dy con la duration de cada ficha"
        )
    else:
        # (niveles / shift - 1) y no pct_change: la firma de fill_method cambió
        # entre pandas 2.x y 3.x y acá no queremos relleno implícito.
        retornos = (niveles / niveles.shift(1) - 1.0).iloc[1:]
        completos = retornos.dropna(axis=0, how="any")
        if len(completos) < MIN_OBS:
            raise ValueError(
                f"Solo {len(completos)} filas tienen dato para todos los activos "
                f"(mínimo {MIN_OBS})."
            )
        tickers = list(completos.columns)
        X_inv = completos.to_numpy(dtype=float)
        X_ret = X_inv
        lower_is_better = False
        detalle_invariante = "retornos simples de precio"

    ranking_idx_orig = parse_ranking(ranking_texto, list(niveles.columns))
    # re-mapear al subconjunto que quedó (algún ticker del ranking pudo caer)
    ranking_idx: List[int] = []
    if ranking_idx_orig:
        nombres_orden = [list(niveles.columns)[i] for i in ranking_idx_orig]
        perdidos = [n for n in nombres_orden if n not in tickers]
        if perdidos:
            raise ValueError(
                "El ranking usa activos que quedaron excluidos: " + ", ".join(perdidos)
            )
        pos = {t: i for i, t in enumerate(tickers)}
        ranking_idx = [pos[n] for n in nombres_orden]

    res = engine.run_qep(
        X_inv, X_ret,
        ranking_idx=ranking_idx or None,
        lower_is_better=lower_is_better,
        q=q, confidence=confianza, delta=delta, max_weight=max_peso,
    )

    if ranking_idx and res.get("views_efecto"):
        ve = res["views_efecto"]
        if not any(ve["binding"]):
            avisos.append(
                "El prior ya cumple todas las desigualdades del ranking: los views "
                "no atan y el posterior es igual al prior (EP = q-EP = prior MV)."
            )
    elif not ranking_idx:
        avisos.append(
            "Sin views: los tres modelos optimizan sobre el prior histórico "
            "(EP y q-EP coinciden con el prior). Agregá un ranking para ver el efecto."
        )

    # ── filas para la tabla ──
    modelos = res["modelos"]
    filas = []
    for i, t in enumerate(tickers):
        ficha = fichas.get(t) or {}
        filas.append({
            "ticker": t,
            "codigo": ficha.get("codigo") or "",
            "duration": ficha.get("duration"),
            "w_prior": float(modelos["prior"]["w"][i]),
            "w_ep": float(modelos["ep"]["w"][i]),
            "w_qep": float(modelos["qep"]["w"][i]),
            "mu_qep_anual": float(modelos["qep"]["mu"][i]) * 252.0,
        })
    filas.sort(key=lambda r: -r["w_qep"])

    dona = None
    items = [{"label": r["ticker"], "val": r["w_qep"], "pct": r["w_qep"]}
             for r in filas if r["w_qep"] > 0.001]
    if items:
        from backend.services.svg_charts import donut
        dona = donut(items, size=170)

    metricas = []
    for clave, etiqueta, en_pct in (
        ("ret_anual", "Retorno esperado anual", True),
        ("vol_anual", "Volatilidad anual", True),
        ("sharpe", "Sharpe", False),
        ("var95", "VaR 95% diario", True),
        ("cvar95", "CVaR 95% diario", True),
    ):
        metricas.append({
            "label": etiqueta, "pct": en_pct,
            "prior": modelos["prior"]["metrics"][clave],
            "ep": modelos["ep"]["metrics"][clave],
            "qep": modelos["qep"]["metrics"][clave],
        })

    ranking_labels = [tickers[i] for i in ranking_idx] if ranking_idx else []
    return {
        "filas": filas,
        "dona": dona,
        "metricas": metricas,
        "avisos": avisos,
        "q": q,
        "confianza": confianza,
        "max_peso": max_peso,
        "delta": delta,
        "invariante": invariante,
        "detalle_invariante": detalle_invariante,
        "ranking": " > ".join(ranking_labels),
        "diag": {
            "obs": int(res["J"]),
            "activos": int(res["N"]),
            "desde": niveles.index[0].date().isoformat(),
            "hasta": niveles.index[-1].date().isoformat(),
            "views_efecto": res.get("views_efecto"),
        },
    }
