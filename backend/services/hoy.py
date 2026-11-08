"""La línea «hoy» de Inicio (glow-up E, 06/11): qué día es, si hay rueda y
hasta qué hora, a qué fecha liquidan CI y 24 hs, el próximo feriado del
calendario argentino y el estado del cierre histórico — lo que el desk mira
antes de operar y hoy tenía que juntar de tres pantallas.

Todo sale del calendario de `dias_habiles` (el mismo de rentafija, con los
feriados agregados a mano), del horario de rueda de los relojes de la topbar
(`watchdog._rueda`) y de `historico_writer.estado_cierre` (stat, µs). Sin
red ni disco. `linea_hoy(ahora=…)` es pura para los tests. No hay fuente
dentro de la app para la próxima licitación del Tesoro: no se inventa."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional

from backend.locale_ar import TZ_BA

_DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre")
_HORIZONTE_FERIADO_DIAS = 180


def _hhmm(mins: int) -> str:
    return f"{mins // 60:02d}:{mins % 60:02d}"


def _feriados():
    import dias_habiles as dh
    return dh.ar_holidays


def _nombre_feriado(fer: Any, d: date) -> Optional[str]:
    if d.weekday() >= 5 or d not in fer:
        return None
    try:
        return str(fer.get(d) or "feriado")
    except Exception:  # noqa: BLE001
        return "feriado"


def proximo_feriado(desde: date, fer: Any = None) -> Optional[Dict[str, Any]]:
    """El próximo feriado ENTRE SEMANA después de `desde` (uno en sábado no
    quita rueda) dentro de `_HORIZONTE_FERIADO_DIAS`; None si no hay."""
    fer = fer if fer is not None else _feriados()
    for i in range(1, _HORIZONTE_FERIADO_DIAS + 1):
        d = desde + timedelta(days=i)
        nombre = _nombre_feriado(fer, d)
        if nombre:
            return {"fecha": d.isoformat(), "fecha_fmt": d.strftime("%d/%m/%Y"),
                    "dia": _DIAS[d.weekday()], "nombre": nombre, "en_dias": i}
    return None


def linea_hoy(ahora: Optional[datetime] = None, cierre: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    import dias_habiles as dh
    from backend.services import watchdog

    ahora = ahora or datetime.now(TZ_BA)
    hoy = ahora.date()
    fer = _feriados()
    feriado = _nombre_feriado(fer, hoy)
    finde = hoy.weekday() >= 5
    es_habil = not finde and feriado is None
    o, c = watchdog._rueda()
    mins = ahora.hour * 60 + ahora.minute
    if not es_habil:
        rueda_txt, rueda_estado = ("sin rueda (fin de semana)" if finde else "sin rueda (feriado)"), "off"
    elif mins < o:
        rueda_txt, rueda_estado = f"abre a las {_hhmm(o)}", "warn"
    elif mins < c:
        rueda_txt, rueda_estado = f"abierta hasta las {_hhmm(c)}", "ok"
    else:
        rueda_txt, rueda_estado = f"cerrada (cerró a las {_hhmm(c)})", "off"
    try:
        liq_ci = dh.siguiente_dia_habil_ar(hoy)
        liq_24 = dh.n_dias_laborales(hoy, 1)
    except Exception:  # noqa: BLE001 — calendario roto: la línea sale igual
        liq_ci = liq_24 = None
    if cierre is None:
        try:
            from backend.services import historico_writer
            cierre = historico_writer.estado_cierre()
        except Exception:  # noqa: BLE001
            cierre = {}
    est = str(cierre.get("estado") or "sin_base")
    ctexto = (cierre.get("texto") or "").lstrip("✓⚠ ").strip()
    cierre_cls = {"ok": "ok", "pendiente": "warn", "capturado": "warn", "falta": "err", "regresion": "err"}.get(est, "off")
    return {
        "fecha": hoy.isoformat(),
        "fecha_fmt": hoy.strftime("%d/%m/%Y"),
        "dia_txt": f"{_DIAS[hoy.weekday()]} {hoy.day} de {_MESES[hoy.month - 1]}",
        "hora": ahora.strftime("%H:%M"),
        "es_habil": es_habil,
        "feriado_hoy": feriado,
        "rueda_txt": rueda_txt,
        "rueda_estado": rueda_estado,
        "horario": f"{_hhmm(o)}–{_hhmm(c)}",
        "liq_ci": liq_ci.strftime("%d/%m/%Y") if liq_ci else "—",
        "liq_24": liq_24.strftime("%d/%m/%Y") if liq_24 else "—",
        "prox_feriado": proximo_feriado(hoy, fer),
        "cierre_estado": est,
        "cierre_cls": cierre_cls,
        "cierre_txt": (ctexto[:1].upper() + ctexto[1:]) if ctexto else ("sin carpeta Delta Bases" if est == "sin_base" else est),
    }
