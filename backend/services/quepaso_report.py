"""Reporte "Qué pasó" — CSV es-AR + resumen de texto + mail de cierre.

El CSV es el mismo que baja el botón ⬇ de la pestaña (acá vive el builder;
la ruta HTTP delega). El mail de cierre se dispara desde el autosave de las
17:01 SOLO cuando el guardado corrió OK — un finde/feriado (autosave
salteado) no manda nada. Todo sale del cache de weekly_segments (costo ~0).

Sync a propósito: corre en el threadpool (autosave / executor de la ruta).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger("backend.quepaso_report")

_TZ = ZoneInfo("America/Argentina/Buenos_Aires")


def _n(v: Any, dec: int = 2) -> str:
    return ("" if v is None or v != v else f"{v:.{dec}f}".replace(".", ","))


def csv_es_ar(dias: int = 7) -> str:
    """CSV es-AR (';' separador, coma decimal, BOM para Excel) del resumen."""
    from backend.services import historico_byma

    dias = max(1, min(int(dias or 7), 120))
    w = historico_byma.weekly_segments(dias)
    lines = [f"Qué pasó;{w.get('start', '')} → {w.get('end', '')};ventana {dias} días", ""]
    lines.append("Segmento;Bono;Duration;Δ Precio %;Cupones %;Δ TIR pp;Δ TEM pp;TIR ini %;TIR fin %")
    for s in w.get("segments", []):
        lines.append(";".join([
            s["label"], f"PROMEDIO ({s['n']})", _n(s.get("dur_avg"), 2),
            _n((s.get("dprice") or 0) * 100, 2) if s.get("dprice") is not None else "",
            _n((s.get("cup_pct") or 0) * 100, 2) if s.get("cup_pct") is not None else "",
            _n((s.get("dtir") or 0) * 100, 2) if s.get("dtir") is not None else "",
            _n((s.get("dtem") or 0) * 100, 2) if s.get("dtem") is not None else "",
            "", _n((s.get("tir_avg") or 0) * 100, 2) if s.get("tir_avg") is not None else "",
        ]))
        for r in s.get("rows", []):
            lines.append(";".join([
                s["label"], r["code"], _n(r.get("dur"), 2),
                _n((r.get("dprice") or 0) * 100, 2) if r.get("dprice") is not None else "",
                _n((r.get("cup_pct") or 0) * 100, 2) if r.get("cup_pct") is not None else "",
                _n((r.get("dtir") or 0) * 100, 2) if r.get("dtir") is not None else "",
                _n((r.get("dtem") or 0) * 100, 2) if r.get("dtem") is not None else "",
                _n((r.get("tir0") or 0) * 100, 2) if r.get("tir0") is not None else "",
                _n((r.get("tir1") or 0) * 100, 2) if r.get("tir1") is not None else "",
            ]))
    return "﻿" + "\n".join(lines)          # BOM → Excel abre UTF-8 con acentos bien


def resumen_texto(dias: int = 1) -> str:
    """Resumen es-AR de texto plano por segmento (cuerpo del mail):
    Δ precio, cupones, Δ TIR y TIR final promedio de cada segmento."""
    from backend.services import historico_byma

    w = historico_byma.weekly_segments(max(1, min(int(dias or 1), 120)))
    out: List[str] = [f"Qué pasó — {w.get('start', '')} → {w.get('end', '')} ({dias} día{'s' if dias != 1 else ''})", ""]
    segs = w.get("segments", [])
    if not any(s.get("n") for s in segs):
        out.append("Sin datos comparables en la ventana (¿base sin fecha previa?).")
        return "\n".join(out)
    for s in segs:
        if not s.get("n"):
            continue
        parts = [f"{s['label']} ({s['n']} bonos):"]
        if s.get("dprice") is not None:
            parts.append(f"Δ precio {_n(s['dprice'] * 100)}%")
        if s.get("cup_pct"):
            parts.append(f"cupones {_n(s['cup_pct'] * 100)}%")
        if s.get("dtir") is not None:
            parts.append(f"Δ TIR {_n(s['dtir'] * 100)} pp")
        if s.get("tir_avg") is not None:
            parts.append(f"TIR prom. {_n(s['tir_avg'] * 100)}%")
        out.append("  " + " · ".join(parts))
    idx = w.get("indices") or {}
    idx_parts = []
    if idx.get("a3500") is not None:
        idx_parts.append(f"deva A3500 {_n(idx['a3500'] * 100)}%")
    if idx.get("cer") is not None:
        idx_parts.append(f"CER {_n(idx['cer'] * 100)}%")
    if idx.get("tamar_fin") is not None:
        d = f" ({'+' if (idx.get('tamar_delta') or 0) >= 0 else ''}{_n((idx.get('tamar_delta') or 0) * 100)} pp)" \
            if idx.get("tamar_delta") is not None else ""
        idx_parts.append(f"TAMAR {_n(idx['tamar_fin'] * 100)}%{d}")
    if idx_parts:
        out.append("")
        out.append("Índices: " + " · ".join(idx_parts))
    out.append("")
    out.append("CSV del día y de la semana adjuntos. — Calculadora de Bonos")
    return "\n".join(out)


def send_close_mail(dias_cuerpo: int = 1) -> Dict[str, Any]:
    """Manda el resumen del día al destinatario operativo, con los CSV de
    1 y 7 días adjuntos. Devuelve {sent, detail}. Nunca lanza."""
    from backend.config import settings
    from backend.services import mailer

    if not settings.quepaso_mail:
        return {"sent": False, "detail": "quepaso_mail apagado"}
    if not mailer.is_configured():
        return {"sent": False, "detail": "SMTP no configurado"}
    to = mailer.default_recipient()
    if not to:
        return {"sent": False, "detail": "sin destinatario (APP_OPS_MAIL_TO / mail del superuser)"}
    try:
        hoy = datetime.now(_TZ).strftime("%d/%m/%Y")
        body = resumen_texto(dias_cuerpo)
        adjuntos = [(f"que_paso_{d}d.csv", csv_es_ar(d).encode("utf-8"), "text/csv")
                    for d in (dias_cuerpo, 7)]
        ok, detail = mailer.send(to, f"Cierre {hoy} — Qué pasó", body, attachments=adjuntos)
        if ok:
            logger.info("[quepaso_report] mail de cierre enviado a %s", to)
        else:
            logger.warning("[quepaso_report] mail de cierre falló: %s", detail)
        return {"sent": ok, "detail": detail}
    except Exception as exc:  # noqa: BLE001 — nunca ensuciar el autosave
        logger.exception("[quepaso_report] mail de cierre reventó")
        return {"sent": False, "detail": str(exc)}
