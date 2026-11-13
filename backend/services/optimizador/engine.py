"""Motor de optimización de carteras con Entropy Pooling generalizado.

Adaptado del repo de la tesis `non_extensive_q_entropy_pooling` (Corvalán
Salguero, MFIN UTDT): Entropy Pooling de Meucci (2008) con la divergencia
generalizada de Tsallis (q-EP), resuelto en el dual, más la estimación
robusta de covarianzas para paneles desbalanceados (pairwise + corrección
PSD de Higham 2002).

Es NumPy/SciPy puro, sin estado y sin I/O: recibe matrices, devuelve dicts.
La capa que habla con la app (parseo de archivos, fichas, formato) vive en
`backend/services/cartera_opt.py`.

Diferencias deliberadas con el repo de la tesis (hallazgos de la revisión):
  - El relleno de huecos es todo-o-nada: un hueco más largo que `max_gap`
    no se rellena NI parcialmente (pandas `interpolate(limit=N)` rellena
    los primeros N de un hueco largo, y eso fabrica datos).
  - `mean_variance` valida la factibilidad de los bounds antes de optimizar
    y solo renormaliza en el caso long-only.
  - El dual de Tsallis no emite warnings por componentes con c*z >= 0: ahí
    el mínimo interior del Lagrangiano es x_i -> 0 y el clamp ES la solución.
  - Solo Shannon y Tsallis q>1 (lo que usa la app); Rényi/q<1 quedan en la
    tesis.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import minimize

__all__ = [
    "prepare_series",
    "pairwise_covariance",
    "nearest_psd",
    "entropy_prog",
    "mean_variance",
    "ranking_rows",
    "run_qep",
]

_EPS = 1e-32


# ── 1. Preparación de series (huecos cortos, NaN de inicio intactos) ──────────

def prepare_series(df: pd.DataFrame, max_gap_fill: int = 5) -> pd.DataFrame:
    """Rellena por interpolación lineal SOLO los huecos interiores de hasta
    `max_gap_fill` observaciones consecutivas. Los NaN de inicio (activo sin
    historia) y los huecos largos quedan como están — todo o nada por hueco."""
    out = df.copy()
    for col in out.columns:
        s = out[col]
        if s.notna().sum() < 2:
            continue
        isna = s.isna().to_numpy()
        # runs de NaN: (inicio, largo)
        runs: List[Tuple[int, int]] = []
        i = 0
        n = len(isna)
        while i < n:
            if isna[i]:
                j = i
                while j < n and isna[j]:
                    j += 1
                runs.append((i, j - i))
                i = j
            else:
                i += 1
        first_valid = int(np.argmax(~isna))
        last_valid = n - 1 - int(np.argmax(~isna[::-1]))
        interp = s.interpolate(method="linear", limit_area="inside")
        filled = s.copy()
        for start, length in runs:
            interior = start > first_valid and (start + length - 1) < last_valid
            if interior and length <= max_gap_fill:
                filled.iloc[start:start + length] = interp.iloc[start:start + length]
        out[col] = filled
    return out


# ── 2. Covarianza pairwise + PSD (Higham) ────────────────────────────────────

def nearest_psd(A: np.ndarray, max_iter: int = 500, tol: float = 1e-12) -> np.ndarray:
    """Matriz PSD más cercana en Frobenius preservando la diagonal (varianzas).
    Proyecciones alternadas con corrección de Dykstra (Higham, 2002)."""
    Y = 0.5 * (A + A.T)
    diag = np.diag(A).copy()
    delta = np.zeros_like(Y)
    for _ in range(max_iter):
        R = Y - delta
        vals, vecs = np.linalg.eigh(R)
        X = (vecs * np.maximum(vals, 0.0)) @ vecs.T
        delta = X - R
        Y_new = X.copy()
        np.fill_diagonal(Y_new, diag)
        if np.linalg.norm(Y_new - Y, "fro") < tol:
            Y = Y_new
            break
        Y = Y_new
    # Cierre: clamp final y re-imposición de la diagonal. Restaurar la
    # diagonal puede dejar un autovalor apenas negativo: una pasada más de
    # clamp lo elimina en la práctica (y el residuo queda < 1e-10).
    for _ in range(2):
        Y = 0.5 * (Y + Y.T)
        vals, vecs = np.linalg.eigh(Y)
        if vals.min() >= -1e-12:
            break
        Y = (vecs * np.maximum(vals, 0.0)) @ vecs.T
        np.fill_diagonal(Y, diag)
    return 0.5 * (Y + Y.T)


def pairwise_covariance(
    returns: pd.DataFrame,
    min_obs: int = 60,
) -> Tuple[np.ndarray, Dict[str, object]]:
    """Covarianza para paneles con NaN: cada par usa su máximo solapamiento;
    pares con menos de `min_obs` observaciones comunes quedan con covarianza 0
    (conservador). Si la matriz resultante no es PSD se corrige con Higham.

    Devuelve (Sigma, diagnostico) con `diagnostico` = {"pairwise": bool,
    "psd_corregida": bool, "min_solap": int, "pares_sin_datos": [...]}."""
    vals = returns.to_numpy(dtype=float)
    n = vals.shape[1]
    cols = list(returns.columns)
    has_nan = bool(np.isnan(vals).any())
    diag_info: Dict[str, object] = {
        "pairwise": has_nan, "psd_corregida": False,
        "min_solap": int(returns.notna().sum().min()) if n else 0,
        "pares_sin_datos": [],
    }
    if not has_nan:
        Sigma = np.cov(vals.T, ddof=1) if n > 1 else np.array([[np.var(vals, ddof=1)]])
        return 0.5 * (Sigma + Sigma.T), diag_info

    Sigma = np.zeros((n, n))
    min_overlap = None
    for i in range(n):
        xi = vals[:, i]
        Sigma[i, i] = float(np.nanvar(xi, ddof=1))
        for j in range(i + 1, n):
            xj = vals[:, j]
            mask = ~np.isnan(xi) & ~np.isnan(xj)
            m = int(mask.sum())
            min_overlap = m if min_overlap is None else min(min_overlap, m)
            if m >= max(min_obs, 2):
                c = float(np.cov(xi[mask], xj[mask], ddof=1)[0, 1])
                Sigma[i, j] = Sigma[j, i] = c
            else:
                diag_info["pares_sin_datos"].append(f"{cols[i]}-{cols[j]} ({m} obs)")
    diag_info["min_solap"] = int(min_overlap or 0)
    Sigma = 0.5 * (Sigma + Sigma.T)
    if np.linalg.eigvalsh(Sigma).min() < -1e-10:
        Sigma = nearest_psd(Sigma)
        diag_info["psd_corregida"] = True
    return Sigma, diag_info


# ── 3. Entropy Pooling (Shannon / Tsallis q>1), dual ─────────────────────────

def entropy_prog(
    p: np.ndarray,
    A: Optional[np.ndarray],
    b: Optional[np.ndarray],
    Aeq: np.ndarray,
    beq: np.ndarray,
    family: str = "T",
    q: float = 2.0,
) -> np.ndarray:
    """Posterior p~ = argmin D(x||p) sujeto a A x <= b, Aeq x = beq.

    family "S": D = Kullback-Leibler (EP clásico de Meucci).
    family "T": D = divergencia de Tsallis de orden q (q > 1); para q = 2 es
    la divergencia chi-cuadrado, cuya minimización con prior uniforme coincide
    con la proyección euclídea sobre el conjunto factible.

    Se resuelve en el dual (multiplicadores l >= 0 para desigualdades, v libre
    para igualdades); el posterior sale de la condición KKT de primer orden:
      Shannon:  x = exp(ln p - 1 - z)
      Tsallis:  x = p * max(c z, 0)^(1/(q-1)),  c = 1/q - 1
    con z = A' l + Aeq' v. Para Tsallis con q>1, un componente con c*z <= 0
    tiene el ínfimo del Lagrangiano en x_i = 0: el clamp es la solución.
    """
    p = np.asarray(p, dtype=float).ravel()
    p = p / p.sum()
    J = p.size
    if A is None or np.size(A) == 0:
        A = np.zeros((0, J))
        b = np.zeros(0)
    A = np.atleast_2d(np.asarray(A, dtype=float))
    b = np.asarray(b, dtype=float).ravel()
    Aeq = np.atleast_2d(np.asarray(Aeq, dtype=float))
    beq = np.asarray(beq, dtype=float).ravel()
    K_, K = A.shape[0], Aeq.shape[0]

    fam = (family or "T").upper()
    if fam not in ("S", "T"):
        raise ValueError(f"entropy family no soportada: {family!r} (usar 'S' o 'T')")
    if fam == "T" and not q > 1.0:
        raise ValueError(f"Tsallis requiere q > 1 (recibido q={q})")

    if fam == "T":
        c = (1.0 / q) - 1.0          # < 0 para q > 1
        power = 1.0 / (q - 1.0)

    def equis(l: np.ndarray, v: np.ndarray) -> np.ndarray:
        z = np.zeros(J)
        if K_:
            z += A.T @ l
        if K:
            z += Aeq.T @ v
        if fam == "S":
            return np.maximum(np.exp(np.log(p) - 1.0 - z), _EPS)
        arg = np.maximum(c * z, _EPS)
        return np.maximum((arg ** power) * p, _EPS)

    def fe(x: np.ndarray) -> float:
        if fam == "S":
            return float(np.sum(x * (np.log(x) - np.log(p))))
        t = float(np.sum(p * ((x / p) ** q)))
        return (t - 1.0) / (q - 1.0)

    def neg_dual(lv: np.ndarray) -> Tuple[float, np.ndarray]:
        l, v = lv[:K_], lv[K_:]
        x = equis(l, v)
        L = fe(x)
        if K_:
            L += float(l @ (A @ x - b))
        if K:
            L += float(v @ (Aeq @ x - beq))
        grad = np.concatenate([
            (b - A @ x) if K_ else np.zeros(0),
            (beq - Aeq @ x) if K else np.zeros(0),
        ])
        return -L, grad

    x0 = np.zeros(K_ + K)
    if fam == "T":
        # warm start desde la solución Shannon: mismo espacio de multiplicadores
        try:
            lv_s = _solve_dual(neg_dual_shannon_factory(p, A, b, Aeq, beq), K_, K)
            if lv_s is not None:
                x0 = lv_s
        except Exception:
            pass
    bounds = [(0.0, None)] * K_ + [(None, None)] * K
    res = minimize(neg_dual, x0, jac=True, method="L-BFGS-B", bounds=bounds,
                   options={"maxiter": 10_000, "ftol": 1e-14})
    if not res.success:
        raise RuntimeError(f"Entropy Pooling no convergió: {res.message}")
    lv = np.asarray(res.x, dtype=float)
    x = equis(lv[:K_], lv[K_:])
    x = np.maximum(x, 0.0)
    return x / x.sum()


def neg_dual_shannon_factory(p, A, b, Aeq, beq):
    """Dual de Shannon con la misma firma que `neg_dual` (para warm start)."""
    J = p.size
    K_, K = A.shape[0], Aeq.shape[0]

    def neg_dual(lv: np.ndarray) -> Tuple[float, np.ndarray]:
        l, v = lv[:K_], lv[K_:]
        z = np.zeros(J)
        if K_:
            z += A.T @ l
        if K:
            z += Aeq.T @ v
        x = np.maximum(np.exp(np.log(p) - 1.0 - z), _EPS)
        L = float(np.sum(x * (np.log(x) - np.log(p))))
        if K_:
            L += float(l @ (A @ x - b))
        if K:
            L += float(v @ (Aeq @ x - beq))
        grad = np.concatenate([
            (b - A @ x) if K_ else np.zeros(0),
            (beq - Aeq @ x) if K else np.zeros(0),
        ])
        return -L, grad

    return neg_dual


def _solve_dual(neg_dual, K_: int, K: int) -> Optional[np.ndarray]:
    bounds = [(0.0, None)] * K_ + [(None, None)] * K
    res = minimize(neg_dual, np.zeros(K_ + K), jac=True, method="L-BFGS-B",
                   bounds=bounds, options={"maxiter": 5_000, "ftol": 1e-12})
    return np.asarray(res.x, dtype=float) if res.success else None


# ── 4. Views de ranking ──────────────────────────────────────────────────────

def ranking_rows(
    X_inv: np.ndarray,
    orden_idx: Sequence[int],
    lower_is_better: bool,
) -> Tuple[np.ndarray, np.ndarray]:
    """Constraints de ranking sobre el factor invariante.

    `orden_idx` viene en orden "mejor primero" EN TERMINOS DE PRECIO (lo que
    escribe el usuario). Si el invariante es un cambio de TIR/spread,
    `lower_is_better=True`: el mejor bono es el que MAS comprime, o sea
      E[inv_mejor] <= E[inv_peor]  ->  (X[:,mejor] - X[:,peor]) p <= 0.
    Con retornos de precio (`lower_is_better=False`) la desigualdad se
    invierte: E[inv_mejor] >= E[inv_peor] -> (X[:,peor] - X[:,mejor]) p <= 0.
    """
    rows = []
    for a, b_ in zip(orden_idx[:-1], orden_idx[1:]):
        if lower_is_better:
            rows.append(X_inv[:, a] - X_inv[:, b_])
        else:
            rows.append(X_inv[:, b_] - X_inv[:, a])
    if not rows:
        return np.zeros((0, X_inv.shape[0])), np.zeros(0)
    return np.vstack(rows), np.zeros(len(rows))


# ── 5. Media-varianza long-only ──────────────────────────────────────────────

def mean_variance(
    mu: np.ndarray,
    Sigma: np.ndarray,
    delta: float = 2.5,
    max_weight: float = 1.0,
) -> np.ndarray:
    """max_w  w'mu - (delta/2) w'Sigma w   s.a.  sum(w)=1, 0 <= w_i <= max_weight."""
    n = len(mu)
    if max_weight * n < 1.0 - 1e-9:
        raise ValueError(
            f"max_weight={max_weight:.0%} con {n} activos no permite sumar 100% "
            f"(hace falta max_weight >= {1.0 / n:.1%})"
        )
    bounds = [(0.0, float(max_weight))] * n

    def obj(w):
        return -(w @ mu - (delta / 2.0) * w @ Sigma @ w)

    def grad(w):
        return -(mu - delta * (Sigma @ w))

    cons = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0,
             "jac": lambda w: np.ones_like(w)}]
    res = minimize(obj, np.full(n, 1.0 / n), jac=grad, bounds=bounds,
                   constraints=cons, method="SLSQP",
                   options={"maxiter": 10_000, "ftol": 1e-12})
    w = np.clip(np.asarray(res.x, dtype=float), 0.0, max_weight)
    s = w.sum()
    if s <= 0:
        raise RuntimeError("la optimización media-varianza devolvió pesos nulos")
    return w / s


# ── 6. Pipeline completo ─────────────────────────────────────────────────────

def _portfolio_metrics(
    w: np.ndarray,
    mu: np.ndarray,
    Sigma: np.ndarray,
    X_ret: np.ndarray,
    p: np.ndarray,
    annualization: float = 252.0,
) -> Dict[str, float]:
    ret_d = float(w @ mu)
    vol_d = float(np.sqrt(max(w @ Sigma @ w, 0.0)))
    sq = float(np.sqrt(annualization))
    out = {
        "ret_anual": ret_d * annualization,
        "vol_anual": vol_d * sq,
        "sharpe": (ret_d / vol_d * sq) if vol_d > 0 else 0.0,
    }
    port = X_ret @ w
    order = np.argsort(port)
    cum = np.cumsum(p[order])
    idx = min(int(np.searchsorted(cum, 0.05)), len(port) - 1)
    var95 = float(port[order][idx])
    tail = port[order][: idx + 1]
    tp = p[order][: idx + 1]
    cvar95 = float(np.sum(tail * tp) / tp.sum()) if tp.sum() > 0 else var95
    out["var95"] = -var95
    out["cvar95"] = -cvar95
    return out


def run_qep(
    X_inv: np.ndarray,
    X_ret: np.ndarray,
    ranking_idx: Optional[Sequence[int]] = None,
    lower_is_better: bool = True,
    q: float = 2.0,
    confidence: float = 1.0,
    delta: float = 2.5,
    max_weight: float = 1.0,
    annualization: float = 252.0,
) -> Dict[str, object]:
    """Corre prior MV, EP-Shannon y q-Tsallis-EP y devuelve pesos y métricas.

    - `X_inv` (J,N): factor invariante (p. ej. cambios de TIR) — los views van acá.
    - `X_ret` (J,N): retornos de precio alineados — la optimización MV va acá.
    - `ranking_idx`: índices de columnas "mejor primero" en términos de precio.
    - `confidence`: mezcla global posterior = (1-c) p + c p~ (Meucci).
    """
    X_inv = np.asarray(X_inv, dtype=float)
    X_ret = np.asarray(X_ret, dtype=float)
    if X_inv.shape != X_ret.shape:
        raise ValueError("X_inv y X_ret deben tener la misma forma (J,N)")
    J, N = X_ret.shape
    p = np.full(J, 1.0 / J)

    A, b = (None, None)
    if ranking_idx and len(ranking_idx) >= 2:
        A, b = ranking_rows(X_inv, list(ranking_idx), lower_is_better)
    Aeq = np.ones((1, J))
    beq = np.array([1.0])

    def momentos(pp: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        mu = X_ret.T @ pp
        second = X_ret.T @ (X_ret * pp[:, None])
        second = 0.5 * (second + second.T)
        return mu, second - np.outer(mu, mu)

    resultados: Dict[str, object] = {"modelos": {}, "views_efecto": None}
    posterior_dist = {}
    for nombre, fam in (("prior", None), ("ep", "S"), ("qep", "T")):
        if fam is None or A is None:
            pp = p.copy()
        else:
            p_raw = entropy_prog(p, A, b, Aeq, beq, family=fam, q=q)
            pp = (1.0 - confidence) * p + confidence * p_raw
            pp = np.maximum(pp, 0.0)
            pp = pp / pp.sum()
        mu, Sigma = momentos(pp)
        w = mean_variance(mu, Sigma, delta=delta, max_weight=max_weight)
        resultados["modelos"][nombre] = {
            "w": w, "mu": mu, "Sigma": Sigma, "p": pp,
            "metrics": _portfolio_metrics(w, mu, Sigma, X_ret, pp, annualization),
        }
        posterior_dist[nombre] = pp

    if A is not None:
        d_ep = float(np.linalg.norm(posterior_dist["ep"] - p) / np.linalg.norm(p))
        d_qep = float(np.linalg.norm(posterior_dist["qep"] - p) / np.linalg.norm(p))
        slack_prior = (A @ p - b).tolist()
        resultados["views_efecto"] = {
            "dist_ep": d_ep, "dist_qep": d_qep,
            "slack_prior": slack_prior,
            "binding": [s > 1e-12 for s in slack_prior],
        }
    resultados["J"] = J
    resultados["N"] = N
    return resultados
