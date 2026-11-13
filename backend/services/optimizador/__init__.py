"""Optimizador de carteras (q-Entropy Pooling) — motor puro.

Ver `engine.py` (matemática) y `backend/services/cartera_opt.py` (adaptador
a la app: parseo de archivos subidos, fichas, formato del resultado).
"""
from backend.services.optimizador.engine import (  # noqa: F401
    entropy_prog,
    mean_variance,
    nearest_psd,
    pairwise_covariance,
    prepare_series,
    ranking_rows,
    run_qep,
)
