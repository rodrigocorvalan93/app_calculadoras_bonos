"""Espejo parquet de una base Excel: ¿sigue siendo copia fiel del xlsx?

Las bases históricas viven en Excel (canónico, lo abre el equipo) con un
espejo `.parquet` al lado que la app lee ~100× más rápido. La pregunta de
siempre es si el espejo está al día o si alguien tocó el Excel después
(corrección a mano, bymaapi viejo, sync de OneDrive con mtime preservado).

Regla anterior: el parquet valía si `mtime(pq) >= mtime(xlsx) − 2 s`. Esa
gracia de 2 s dejaba pasar una corrección hecha justo después del guardado
(auditoría R06/B07) y un mtime preservado por OneDrive (el Excel editado en
otra máquina llega con hora VIEJA) hacía ganar al espejo aunque el Excel
fuera otro. Regla nueva, en dos capas:

1. **Firma del Excel** (`<base>.parquet.src.json`): el writer deja junto al
   espejo la huella (mtime en ns + tamaño) del xlsx del que ese parquet es
   copia. El espejo vale SÓLO si la huella actual del Excel coincide exacto:
   cualquier guardado del Excel cambia mtime o tamaño → el Excel manda y el
   espejo se regenera. Independiente del orden de los relojes.
2. **Sin firma** (espejos anteriores a esta versión): regla estricta
   `mtime(pq) >= mtime(xlsx)`, sin gracia. Ante la duda, el Excel.

stdlib puro: lo importa también `bymaapi.py` fuera del server.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

SIDECAR_SUFFIX = ".src.json"

_lock = threading.Lock()
# (pq, xlsx) → (stat pq, stat xlsx, resultado): dos stat() por consulta en
# caliente (sub-ms), el JSON se relee sólo cuando alguno de los dos cambió.
_MEMO: Dict[Tuple[str, str], Tuple[Any, Any, bool]] = {}
_MEMO_MAX = 64


def sidecar_path(pq_path: str) -> str:
    return pq_path + SIDECAR_SUFFIX


def firma(path: str) -> Optional[Dict[str, int]]:
    """Huella barata de un archivo: mtime en ns + tamaño. None si no existe."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return {"xlsx_mtime_ns": int(st.st_mtime_ns), "xlsx_size": int(st.st_size)}


def _leer_sidecar(pq_path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(sidecar_path(pq_path), "r", encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _stat_key(path: str) -> Any:
    try:
        st = os.stat(path)
        return (int(st.st_mtime_ns), int(st.st_size))
    except OSError:
        return None


def _sha256(path: str) -> Optional[str]:
    """Digest del contenido (chunks de 1 MiB). None si no se puede leer. Se
    usa sólo al escribir la firma y al validar con el memo frío (stat cambió),
    NO en el path caliente."""
    import hashlib
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def espejo_valido(pq_path: str, xlsx_path: Optional[str]) -> bool:
    """True si `pq_path` existe y es copia fiel del Excel: con sidecar, la
    firma del xlsx coincide exacto; sin sidecar, el parquet no es más viejo
    que el xlsx (estricto). Sin Excel al lado, el parquet suelto vale."""
    k_pq = _stat_key(pq_path)
    if k_pq is None:
        return False
    if not xlsx_path:
        return True
    k_x = _stat_key(xlsx_path)
    if k_x is None:
        return True
    memo_key = (pq_path, xlsx_path)
    with _lock:
        ent = _MEMO.get(memo_key)
        if ent is not None and ent[0] == k_pq and ent[1] == k_x:
            return ent[2]
    sc = _leer_sidecar(pq_path)
    if sc is not None and "xlsx_mtime_ns" in sc:
        try:
            ok = (int(sc.get("xlsx_mtime_ns")) == k_x[0] and int(sc.get("xlsx_size")) == k_x[1])
            # La firma también describe al PARQUET (tamaño): OneDrive puede
            # traer el espejo de otra máquina y dejar el sidecar local — con
            # sólo la huella del Excel ese parquet ajeno pasaba por fiel.
            if ok and sc.get("pq_size") is not None:
                ok = int(sc.get("pq_size")) == k_pq[1]
            # Digest de contenido: tamaño == tamaño NO prueba mismo contenido
            # (un parquet ajeno del mismo tamaño pasaba por fiel — A06). Con
            # `pq_sha256` en la firma el espejo vale sólo si el hash coincide.
            # Se calcula acá nomás (memo frío = algún stat cambió), no por
            # request; una firma vieja sin hash cae a la regla de tamaño.
            if ok and sc.get("pq_sha256"):
                ok = (_sha256(pq_path) == sc.get("pq_sha256"))
        except (TypeError, ValueError):
            ok = False
    else:
        # Espejo sin firma (versión anterior / bymaapi viejo): estricto, sin
        # los 2 s de gracia de antes.
        ok = k_pq[0] >= k_x[0]
    with _lock:
        if len(_MEMO) >= _MEMO_MAX:
            _MEMO.clear()
        _MEMO[memo_key] = (k_pq, k_x, ok)
    return ok


def marcar_espejo(pq_path: str, xlsx_path: Optional[str]) -> bool:
    """Deja constancia de que `pq_path` es copia fiel del xlsx TAL COMO ESTÁ
    AHORA (llamar después de escribir los dos). Escritura atómica; best-effort
    (un sidecar que no se pudo escribir sólo degrada a la regla de mtime).
    Sin Excel al lado se borra la firma vieja (no describe nada)."""
    sc = sidecar_path(pq_path)
    f = firma(xlsx_path) if xlsx_path else None
    with _lock:
        _MEMO.pop((pq_path, xlsx_path or ""), None)
    if f is None:
        try:
            os.remove(sc)
        except OSError:
            pass
        return False
    k_pq = _stat_key(pq_path)
    tmp = sc + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({**f, "xlsx": os.path.basename(xlsx_path or ""),
                       **({"pq_size": k_pq[1]} if k_pq is not None else {}),
                       **({"pq_sha256": _sha256(pq_path)} if k_pq is not None else {})}, fh)
        os.replace(tmp, sc)
        return True
    except OSError as exc:
        logger.info("[espejo] no pude escribir la firma %s: %s", sc, exc)
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


def olvidar_firma(pq_path: str) -> None:
    """Borra el sidecar (el espejo dejó de ser copia de nada — p. ej. falló
    su escritura después de guardar el Excel)."""
    with _lock:
        for k in [k for k in _MEMO if k[0] == pq_path]:
            _MEMO.pop(k, None)
    try:
        os.remove(sidecar_path(pq_path))
    except OSError:
        pass


def reset_memo() -> None:
    with _lock:
        _MEMO.clear()


# Columnas numéricas de la base px/tasas: en el espejo van SIEMPRE float64.
COLS_NUMERICAS = ("Last Price", "Close Price", "Variación %", "TIREA", "TNA", "TEM",
                  "Paridad", "Duration")


def normalizar_numericas(df: Any, origen: str, cols: Tuple[str, ...] = COLS_NUMERICAS) -> Any:
    """Columnas numéricas a float64 antes de escribir un espejo, venga de
    donde venga el cuadro (Excel leído por el writer, por el lector de
    Históricos o por bymaapi).

    `read_excel` deja una columna como `object` si alguna celda del Excel
    tiene TEXTO que no es un NA de pandas (un "s/d" tipeado, una nota, un
    encabezado pegado) y, en ese caso, un valor integral grande (una TIREA
    absurda de 1e+20 que el calc dejó algún día) queda como `int` de Python:
    pyarrow no lo puede meter en int64 y `to_parquet` revienta con "PyLong is
    too large to fit int64". Una celda volteaba TODO guardado (cierre del
    día, consolidación del journal, reconstrucción de un hueco) y dejaba al
    lector sin espejo (28/09/2026). Acá: texto → NaN (la fila cae en el
    dropna de métricas del writer), enteros → float, y un warning con qué
    celdas eran para poder limpiar el Excel. Una columna ya float64 no se
    toca: costo cero en el camino normal (espejo parquet). Modifica `df` en
    el lugar y lo devuelve. pandas se importa acá adentro: el módulo sigue
    siendo importable sin pandas."""
    import pandas as pd
    for col in cols:
        if col not in df.columns or df[col].dtype == "float64":
            continue
        orig = df[col]
        conv = pd.to_numeric(orig, errors="coerce")
        vacio = orig.isna() | orig.astype(str).str.strip().eq("")
        perdidos = conv.isna() & ~vacio
        if perdidos.any():
            cods = df["Código"] if "Código" in df.columns else orig
            fechas = df["fecha_hoy"] if "fecha_hoy" in df.columns else orig
            muestra = [f"{c} {f}: {v!r}" for c, f, v in
                       zip(cods[perdidos].head(5), fechas[perdidos].head(5), orig[perdidos].head(5))]
            logger.warning("[espejo] %s: %d celdas no numéricas en '%s' → NaN "
                           "(la fila cae del guardado si es una métrica): %s",
                           origen, int(perdidos.sum()), col, "; ".join(muestra))
        df[col] = conv.astype("float64")
    return df
