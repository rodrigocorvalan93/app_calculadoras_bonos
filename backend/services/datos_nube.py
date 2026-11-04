"""Archivos de DATOS "sólo en la nube" (OneDrive) — chequeo del arranque,
tarjeta de /admin y recarga sola cuando bajan (04/11).

La PC nueva de un superuser arrancó con la biblioteca "Inversiones -
Documentos" entera como marcadores de OneDrive: cientos de warnings sueltos
(cafci, cierres, historico_byma) y Posiciones / Matriz vacías sin una sola
línea que dijera por qué (`positions` y `delta_especies` guardan el EINVAL
en `error` y nadie lo loguea). Y aunque OneDrive los bajara después, los
loaders cachean el fallo (`positions.ensure_loaded` sirve el dict fallido,
`cafci` recarga sólo si cambia el candidato, `historico_byma` sólo con
`refresh()`): había que reiniciar.

Acá, sólo en Windows (fuera no hay marcadores) y antes de la PRIMERA lectura
de datos del lifespan:
- `chequear_arranque()` escanea las carpetas de datos (las de secrets.txt,
  igual que `backend.tools.onedrive --datos`: un scandir con los atributos del
  listado, sin abrir archivos, decenas de ms) y deja UNA línea con cuántos
  archivos faltan por carpeta, cuántos son esenciales para el arranque y el
  remedio; el detalle queda para /admin · Salud (`status()`).
- Si faltan esenciales (composición, PN, Especies, bases px/tasas y FX…)
  arranca un thread que re-escanea cada `_CADA_S` y, cuando OneDrive los
  bajó (ya no tienen el bit RECALL), limpia TODO lo cacheado por firma de
  archivo (memo de `espejo_valido`, resumen de ruedas y manifiesto del
  writer, frame de Históricos · Base — la hidratación NO cambia mtime ni
  tamaño, así que esos memos no se enteran solos) y recarga Posiciones /
  Especies / CAFCI / Históricos / FX / acciones; si un loader sigue sin
  cargar, lo dice y reintenta en la próxima vuelta. Un `refresh()` nunca
  corre con el archivo todavía marcador ni sobre un escaneo incompleto (una
  carpeta que no se pudo listar no cuenta como "todo bajado").
`DATOS_NUBE=0` lo apaga. Todo failure-silent: el arranque no depende de esto.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.tools import onedrive

logger = logging.getLogger("backend.datos_nube")

_CADA_S = 60.0                 # re-escaneo mientras falten esenciales
_MAX_S = 8 * 3600.0            # después de eso, dejamos de vigilar (↻ manual / reinicio)
_MEMO_S = 30.0                 # `status()` (lo sondea /admin) re-escanea a lo sumo cada 30 s
_lock = threading.Lock()
_estado: Dict[str, Any] = {"activo": False, "pendientes": 0, "esenciales": 0, "carpetas": [], "ts": 0.0}
_vigilante: Optional[threading.Thread] = None
_recargado = False


def activo() -> bool:
    return onedrive.es_windows() and os.getenv("DATOS_NUBE", "1") != "0"


def carpetas() -> List[Tuple[str, Path]]:
    """Las carpetas de datos de secrets.txt (ya en os.environ: backend.config
    importó OMSsecrets), sin duplicados ni hijas de otra de la lista."""
    from backend.services import deltapaths

    cand: List[Tuple[str, str]] = []
    hist = deltapaths.historico_dir()
    if hist:
        cand.append(("Delta Bases", hist))
    for var in onedrive._VARS_CARPETAS:
        d = deltapaths.expand(os.getenv(var), want="dir")
        if d and os.path.isdir(d):
            cand.append((var, d))
    for var in onedrive._VARS_ARCHIVOS:
        f = deltapaths.expand(os.getenv(var), want="file")
        if f and os.path.isfile(f):
            cand.append((var, os.path.dirname(f)))
    out: List[Tuple[str, Path]] = []
    for label, d in cand:
        p = Path(d).resolve()
        if any(p == q or q in p.parents for _l, q in out):
            continue
        out = [(lb, q) for lb, q in out if p not in q.parents] + [(label, p)]
    return out


def escanear() -> Dict[str, Any]:
    """Estado actual: scandir con los atributos del listado, sin abrir
    archivos. Nunca tira. `incompleto` = una carpeta no se pudo listar o el
    escaneo reventó: lo de adentro NO se chequeó — no cuenta como "todo
    bajado" (el vigilante no recarga sobre un escaneo incompleto)."""
    st: Dict[str, Any] = {"activo": activo(), "pendientes": 0, "esenciales": 0, "bytes": 0,
                          "carpetas": [], "errores": 0, "incompleto": False, "ts": time.time()}
    if not st["activo"]:
        return st
    try:
        onedrive.exponer_marcadores()
        for label, root in carpetas():
            esc = onedrive.escanear(root, excluir=(), clasificar_basura=False)
            ese = onedrive.esenciales(esc)
            st["carpetas"].append({
                "label": label, "nombre": root.name, "total": esc.total,
                "pendientes": len(esc.pendientes), "esenciales": len(ese),
                "bytes": sum(a.size for a in esc.pendientes), "fijada": esc.root_fijado, "nube": esc.nube,
                "esenciales_nombres": [a.path.name for a in ese][:12], "errores": len(esc.errores),
            })
            st["pendientes"] += len(esc.pendientes)
            st["esenciales"] += len(ese)
            st["bytes"] += sum(a.size for a in esc.pendientes)
            st["errores"] += len(esc.errores)
            for d, e in esc.errores:
                logger.warning("[datos_nube] no pude listar %s: %s (lo de adentro no se chequeó)", d, e)
    except Exception as exc:  # noqa: BLE001 — diagnóstico: nunca voltea el arranque
        logger.warning("[datos_nube] escaneo falló: %s", exc)
        st["error_escaneo"] = str(exc)
    st["incompleto"] = bool(st["errores"] or st.get("error_escaneo"))
    with _lock:
        _estado.clear()
        _estado.update(st)
    return st


def _resumen(st: Dict[str, Any]) -> str:
    partes = [f"{c['nombre']}: {c['pendientes']} de {c['total']}"
              + (f" ({c['esenciales']} esenciales)" if c["esenciales"] else "")
              for c in st["carpetas"] if c["pendientes"]]
    return " · ".join(partes) or "ninguna"


def chequear_arranque() -> Dict[str, Any]:
    """Lo llama el lifespan ANTES de leer posiciones / especies / bases."""
    global _vigilante
    st = escanear()
    if not st["activo"]:
        return st
    if st["pendientes"] or st["incompleto"]:
        mb = st["bytes"] / (1 << 20)
        if st["esenciales"] or st["incompleto"]:
            logger.warning("[datos_nube] %d archivos de datos están 'sólo en la nube' (OneDrive, %.0f MB) — %s. "
                           "Posiciones / Matriz / Históricos van a estar vacíos hasta que OneDrive los baje; "
                           "la app los recarga sola cuando lleguen (o ↻ en la pestaña). %s",
                           st["pendientes"], mb, _resumen(st), onedrive_remedio())
            if _vigilante is None or not _vigilante.is_alive():
                _vigilante = threading.Thread(target=_vigilar, name="datos-nube", daemon=True)
                _vigilante.start()
        else:
            logger.info("[datos_nube] %d archivos de datos 'sólo en la nube' (OneDrive, %.0f MB), ninguno esencial "
                        "— %s; Históricos los toma solos cuando bajen", st["pendientes"], mb, _resumen(st))
    return st


def onedrive_remedio() -> str:
    return ("Remedio: OneDrive abierto y sincronizando; botón derecho sobre 'Delta Bases' > \"Mantener "
            "siempre en este dispositivo\" (el .bat de la app lo hace solo desde el 04/11).")


def _vigilar() -> None:
    inicio = time.monotonic()
    while time.monotonic() - inicio < _MAX_S:
        time.sleep(_CADA_S)
        try:
            st = escanear()
        except Exception:  # noqa: BLE001
            continue
        if not st["activo"]:
            return
        if st["esenciales"] == 0 and not st["incompleto"]:
            if _recargar():
                return                               # todo cargado: listo
            # algún loader sigue sin cargar (el archivo bajó a medias, permisos…):
            # seguir vigilando y reintentar en la próxima vuelta


def _recargar() -> bool:
    """OneDrive bajó lo esencial: releer lo que cacheó el fallo. True si todos
    los loaders que informan `loaded` quedaron cargados."""
    global _recargado
    hechos: List[str] = []
    fallidos: List[str] = []
    for nombre, fn in _recargas():
        try:
            r = fn()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[datos_nube] recarga de %s falló: %s", nombre, exc)
            fallidos.append(nombre)
            continue
        if isinstance(r, dict) and r.get("loaded") is False:
            # positions / delta_especies / cafci / historico_byma atrapan su
            # excepción y la dejan en `error`: no es una recarga lograda
            logger.warning("[datos_nube] recarga de %s: sigue sin cargar (%s)", nombre, r.get("error") or "?")
            fallidos.append(nombre)
            continue
        hechos.append(nombre)
    _recargado = not fallidos
    if fallidos:
        logger.warning("[datos_nube] OneDrive bajó los archivos esenciales pero no cargaron: %s (recargados %s); "
                       "se reintenta", ", ".join(fallidos), ", ".join(hechos) or "—")
    else:
        logger.info("[datos_nube] OneDrive bajó los archivos esenciales: recargados %s", ", ".join(hechos) or "—")
    return not fallidos


def _recargas() -> List[Tuple[str, Any]]:
    from backend.services import acciones_hist, base_export, cafci, delta_especies, espejo, fx_hist, historico_byma, positions
    from backend.services import historico_writer as hw

    def _memos() -> None:
        # Todo lo cacheado por FIRMA (mtime + tamaño) del archivo: un marcador
        # tiene stat normal y la hidratación no lo cambia, así que el veredicto
        # o el frame tomado sobre el marcador quedaría pegado hasta la próxima
        # escritura (revisión 04/11).
        espejo.reset_memo()                 # espejo_valido (¿parquet fiel al Excel?)
        hw._fechas_cache = ()               # resumen de ruedas de la base
        hw._manifest_cache = ()             # manifiesto compartido (regresión entre máquinas)
        base_export.invalidar()             # frame de Históricos · Base

    return [("memos", _memos), ("posiciones", positions.refresh), ("especies", delta_especies.refresh),
            ("cafci", cafci.refresh), ("historico", historico_byma.refresh),
            ("fx", fx_hist.refresh), ("acciones", acciones_hist.refresh)]


def status() -> Dict[str, Any]:
    """Tarjeta de /admin · Salud (pill roja `error` mientras falten esenciales)."""
    with _lock:
        st = dict(_estado)
    if not activo():
        return {"activo": False, "nota": "sólo aplica en Windows con OneDrive"}
    if time.time() - float(st.get("ts") or 0) > _MEMO_S:
        st = escanear()
    out: Dict[str, Any] = {
        "activo": True,
        "sin bajar": st.get("pendientes", 0),
        "esenciales sin bajar": st.get("esenciales", 0),
        "MB sin bajar": f"{st.get('bytes', 0) / (1 << 20):.0f}",
        "carpetas": " · ".join(f"{c['nombre']} {c['pendientes']}/{c['total']}"
                               f"{' · fijada' if c['fijada'] else ' · SIN fijar'}" for c in st.get("carpetas", []))
                    or "sin carpetas de datos configuradas",
        "recargado": _recargado,
    }
    if st.get("esenciales"):
        out["error"] = (f"{st['esenciales']} archivo(s) esenciales 'sólo en la nube': "
                        + ", ".join(n for c in st["carpetas"] for n in c.get("esenciales_nombres", [])[:6])
                        + ". " + onedrive_remedio())
    if st.get("errores"):
        out["error"] = (f"{st['errores']} carpeta(s) no se pudieron listar (lo de adentro no se chequeó); "
                        + (out.get("error") or onedrive_remedio()))
    if st.get("error_escaneo"):
        out["error"] = f"escaneo falló: {st['error_escaneo']}"
    return out
