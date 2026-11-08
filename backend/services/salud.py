"""Salud de la app en lenguaje llano, para TODOS los usuarios (glow-up C,
06/11): `/salud` y el link del estado del feed de la topbar.

/admin · Salud sigue siendo el detalle técnico del superuser (stats del WS,
seq-cache, ring de errores con los mensajes). Acá va lo que cualquier usuario
del desk puede entender y, cuando hay, QUÉ puede hacer: feed del broker
(reconectar), cierre histórico, archivos de OneDrive, carteras, índices BCRA,
MAE, CAFCI, noticias y cuántos avisos hubo en la última hora. Cada ítem:

    {key, titulo, estado: ok | warn | err | off, texto, detalle,
     accion: {href, label} | None, tab: pestaña que la acción necesita | None}

Todo son lecturas de memoria o un stat (µs); `estado_cierre` y el escaneo de
OneDrive pueden costar decenas de ms el día que algo cambió, por eso la ruta
lo manda al executor igual. Un ítem que falle al leerse NO voltea la página:
queda como `err` con el motivo."""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

ESTADOS = ("ok", "warn", "err", "off")
_PESO = {"err": 3, "warn": 2, "off": 1, "ok": 0}


def _item(key: str, titulo: str, estado: str, texto: str, detalle: str = "",
          accion: Optional[Dict[str, str]] = None, tab: Optional[str] = None) -> Dict[str, Any]:
    return {"key": key, "titulo": titulo, "estado": estado if estado in ESTADOS else "off",
            "texto": texto, "detalle": detalle, "accion": accion, "tab": tab}


def _feed() -> Dict[str, Any]:
    from backend.services import feed_health
    h = feed_health.snapshot()
    acc = {"href": "/conexion", "label": "Reconectar"}
    t = "Feed del broker"
    if not h.get("authenticated"):
        return _item("feed", t, "off", "Sin sesión con el broker",
                     "La app no tiene sesión abierta con el feed BYMA: los precios no se mueven. "
                     "Conectá (o revisá usuario/clave del broker).", acc)
    if h.get("feed_down"):
        return _item("feed", t, "err", "Feed caído",
                     "Hay sesión pero el socket del broker está desconectado: los precios que ves están "
                     "congelados. Reconectá o elegí otro broker.", acc)
    if h.get("connecting"):
        return _item("feed", t, "warn", "Conectando al broker…",
                     "Sesión abierta, handshake en curso. Se resuelve solo en segundos; no hace falta "
                     "volver a reconectar.")
    if h.get("warn"):
        return _item("feed", t, "warn", "Precios posiblemente viejos",
                     f"{h['warn']}. Probá otro broker.", acc)
    age = h.get("data_age_s")
    if h.get("feed_alive"):
        return _item("feed", t, "ok", "En vivo",
                     f"Market data llegando; último tick hace {int(age)} s." if age is not None
                     else "Market data llegando.")
    return _item("feed", t, "ok", "Conectado",
                 "Sesión y socket vivos; " + ("mercado quieto." if h.get("en_rueda")
                                              else "fuera del horario de rueda."))


def _cierre() -> Dict[str, Any]:
    from backend.services import historico_writer
    e = historico_writer.estado_cierre()
    est = e.get("estado") or "sin_base"
    mapa = {"ok": "ok", "pendiente": "warn", "capturado": "warn", "falta": "err",
            "regresion": "err", "sin_base": "off"}
    texto = (e.get("texto") or "").lstrip("✓⚠ ").strip()
    if not texto:
        texto = "Carpeta Delta Bases no montada" if est == "sin_base" else est
    texto = texto[:1].upper() + texto[1:]
    detalle = e.get("detalle") or ("La base histórica vive en Delta Bases (OneDrive) y en esta máquina "
                                   "no está montada: Históricos y Posiciones quedan sin datos."
                                   if est == "sin_base" else "")
    acc = {"href": "/historicos", "label": "Ver la base"} if est != "sin_base" else None
    return _item("cierre", "Cierre histórico", mapa.get(est, "off"), texto, detalle, acc, "historicos")


def _datos() -> Optional[Dict[str, Any]]:
    from backend.services import datos_nube
    s = datos_nube.status()
    if not s.get("activo"):
        return None                      # Mac / Linux / sin OneDrive: no aplica
    t = "Archivos de datos (OneDrive)"
    if s.get("error"):
        return _item("datos", t, "err", "Faltan archivos esenciales", str(s["error"]))
    pend = int(s.get("sin bajar") or 0)
    carpetas = str(s.get("carpetas") or "")
    if pend:
        return _item("datos", t, "warn", f"{pend} archivos sin bajar",
                     "Nada esencial falta; OneDrive baja el resto en segundo plano (carpetas fijadas). "
                     + carpetas)
    return _item("datos", t, "ok", "Todo bajado", carpetas)


def _carteras() -> Dict[str, Any]:
    from backend.services import positions
    s = positions.status()
    t = "Carteras (Posiciones / Matriz)"
    if s.get("loaded"):
        asof = s.get("asof")
        return _item("carteras", t, "ok", f"{s.get('n_holdings', 0)} tenencias · {s.get('n_fondos_pn', 0)} fondos",
                     f"Delta_Composicion.xlsx · {asof}" if asof else "Delta_Composicion.xlsx leída.",
                     {"href": "/posiciones", "label": "Ver posiciones"}, "posiciones")
    return _item("carteras", t, "err", "No se cargaron las carteras", str(s.get("error") or "sin detalle"),
                 {"href": "/posiciones?refresh=1", "label": "Releer carteras"}, "posiciones")


def _macro() -> Dict[str, Any]:
    from backend.services import historico
    h = historico.status()
    t = "Índices BCRA"
    if h.get("loaded"):
        return _item("macro", t, "ok", f"{h.get('n', 0)} series en memoria",
                     "A3500, CER, UVA, TAMAR, BADLAR…: backup local que se refresca a las 11:00 y 15:30.")
    return _item("macro", t, "err", "Índices sin cargar", str(h.get("error") or "sin detalle"))


def _mae() -> Dict[str, Any]:
    from backend.services import mae
    s = mae.status()
    t = "MAE (OTC)"
    if not s.get("enabled"):
        return _item("mae", t, "off", "Sin token MAE",
                     "Las tasas y cauciones MAE no se consultan en esta instancia (MAE_API_KEY en secrets.txt).")
    ts = float(s.get("ts") or 0.0)
    if not ts:
        return _item("mae", t, "warn", "Sin datos todavía", "El poller MAE no trajo nada desde el arranque.")
    edad = int((time.time() - ts) // 60)
    txt = f"{s.get('n_rentafija', 0)} renta fija · {s.get('n_cauciones', 0)} cauciones"
    if s.get("fresh"):
        return _item("mae", t, "ok", txt, "Snapshot fresco.")
    return _item("mae", t, "warn", f"Último dato hace {edad} min", txt + ". MAE no responde o no publica.")


def _cafci() -> Dict[str, Any]:
    from backend.services import cafci_api
    s = cafci_api.status()
    t = "CAFCI"
    if not s.get("enabled"):
        return _item("cafci", t, "off", "Sin credenciales CAFCI", "La API de CAFCI no se consulta en esta instancia.")
    if s.get("auth_error"):
        return _item("cafci", t, "err", "CAFCI rechazó las credenciales", str(s["auth_error"]))
    if s.get("error"):
        return _item("cafci", t, "warn", "CAFCI con errores", str(s["error"]))
    return _item("cafci", t, "ok", f"{s.get('n_funds', 0)} fondos",
                 f"Vector del {s['funds_fecha']}." if s.get("funds_fecha") else "")


def _noticias() -> Dict[str, Any]:
    from backend.services import news
    s = news.status()
    n = int(s.get("items") or 0)
    fuentes = s.get("fuentes") or []
    ok = sum(1 for f in fuentes if f.get("status") in ("ok", "304"))
    if not n:
        return _item("news", "Noticias", "warn", "Sin titulares",
                     "Ninguna fuente RSS respondió todavía (red, proxy o primer ciclo).")
    return _item("news", "Noticias", "ok", f"{n} titulares", f"{ok} de {len(fuentes)} fuentes respondiendo.")


def _errores() -> Dict[str, Any]:
    from backend.services import errores
    corte = time.time() - 3600.0
    recientes = [e for e in errores.ultimos(120) if float(e.get("t") or 0.0) >= corte]
    t = "Avisos del proceso"
    if not recientes:
        return _item("errores", t, "ok", "Sin errores en la última hora", "",
                     {"href": "/admin", "label": "Ver el detalle"}, "admin")
    mods = sorted({str(e.get("logger") or "?") for e in recientes})
    graves = sum(1 for e in recientes if e.get("level") in ("ERROR", "CRITICAL"))
    return _item("errores", t, "err" if graves else "warn",
                 f"{len(recientes)} avisos en la última hora" + (f" ({graves} errores)" if graves else ""),
                 "Módulos: " + ", ".join(mods[:6]) + (" …" if len(mods) > 6 else "")
                 + ". El superuser ve los mensajes en /admin.",
                 {"href": "/admin", "label": "Ver el detalle"}, "admin")


_FUENTES = ("_feed", "_cierre", "_datos", "_carteras", "_macro", "_mae", "_cafci", "_noticias", "_errores")


def resumen() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for nombre in _FUENTES:
        fn: Callable[[], Optional[Dict[str, Any]]] = globals()[nombre]     # resuelto al llamar (parcheable)
        try:
            it = fn()
        except Exception as exc:  # noqa: BLE001 — un lector roto no voltea la página
            key = nombre.strip("_")
            it = _item(key, key.capitalize(), "err", "No se pudo leer", f"{type(exc).__name__}: {exc}"[:300])
        if it:
            out.append(it)
    return out


def titular(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Una línea para el encabezado: el peor estado y cuántos ítems no están ok."""
    peor = max((it["estado"] for it in items), key=lambda e: _PESO.get(e, 0), default="ok")
    n = sum(1 for it in items if it["estado"] in ("warn", "err"))
    if peor == "err":
        texto = f"{n} cosa{'s' if n != 1 else ''} para mirar"
    elif peor == "warn":
        texto = f"{n} aviso{'s' if n != 1 else ''}"
    else:
        texto = "Todo en orden"
    return {"estado": peor, "texto": texto, "n": n}
