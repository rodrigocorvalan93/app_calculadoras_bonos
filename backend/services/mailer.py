"""Envío de mail por SMTP (recuperación de contraseña).

Best-effort y fuera del event loop: el envío puede tardar (handshake TLS), así
que el caller lo corre en un threadpool. Config por env (`APP_SMTP_*`). Si no
está configurado, `send()` devuelve (False, motivo) y la ruta /forgot avisa.

Gmail: host smtp.gmail.com, port 587, user = tu gmail, password = un
**App Password** (no la clave normal; requiere 2FA en la cuenta).
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from typing import List, Optional, Tuple

logger = logging.getLogger("backend.mailer")


def is_configured() -> bool:
    from backend.config import settings
    return bool(settings.app_smtp_host and settings.app_smtp_user and settings.app_smtp_password)


def default_recipient() -> str:
    """Destino de los mails operativos (cierre / watchdog): APP_OPS_MAIL_TO si
    está seteado; si no, el mail del (primer) superuser del store de usuarios;
    último recurso, la propia casilla SMTP. '' si no hay ninguno."""
    from backend.config import settings
    if (settings.app_ops_mail_to or "").strip():
        return settings.app_ops_mail_to.strip()
    try:
        from backend.services import auth
        for u in auth.list_users():
            if u.get("role") == "superuser" and (u.get("email") or "").strip():
                return u["email"].strip()
    except Exception:  # noqa: BLE001 — sin store de usuarios (dev) no es error
        pass
    return (settings.app_smtp_user or "").strip()


def send(to: str, subject: str, body: str,
         attachments: Optional[List[Tuple[str, bytes, str]]] = None) -> Tuple[bool, str]:
    """Envía un mail de texto plano, con adjuntos opcionales
    [(nombre, bytes, mime)]. Devuelve (ok, detalle). Nunca lanza."""
    from backend.config import settings
    if not is_configured():
        return False, "SMTP no configurado (APP_SMTP_HOST / APP_SMTP_USER / APP_SMTP_PASSWORD)."
    frm = settings.app_smtp_from or settings.app_smtp_user
    msg = EmailMessage()
    msg["From"] = frm
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    for fname, data, mime in attachments or []:
        maintype, _, subtype = (mime or "application/octet-stream").partition("/")
        msg.add_attachment(data, maintype=maintype or "application",
                           subtype=subtype or "octet-stream", filename=fname)
    try:
        ctx = ssl.create_default_context()
        port = int(settings.app_smtp_port or 587)
        if port == 465:
            with smtplib.SMTP_SSL(settings.app_smtp_host, port, timeout=15, context=ctx) as s:
                s.login(settings.app_smtp_user, settings.app_smtp_password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(settings.app_smtp_host, port, timeout=15) as s:
                s.starttls(context=ctx)
                s.login(settings.app_smtp_user, settings.app_smtp_password)
                s.send_message(msg)
        logger.info("[mailer] mail enviado a %s", to)
        return True, "enviado"
    except Exception as exc:  # noqa: BLE001
        logger.error("[mailer] fallo enviando a %s: %s", to, exc)
        return False, f"Error SMTP: {exc}"
