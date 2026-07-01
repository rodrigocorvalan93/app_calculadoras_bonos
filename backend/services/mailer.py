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
from typing import Tuple

logger = logging.getLogger("backend.mailer")


def is_configured() -> bool:
    from backend.config import settings
    return bool(settings.app_smtp_host and settings.app_smtp_user and settings.app_smtp_password)


def send(to: str, subject: str, body: str) -> Tuple[bool, str]:
    """Envía un mail de texto plano. Devuelve (ok, detalle). Nunca lanza."""
    from backend.config import settings
    if not is_configured():
        return False, "SMTP no configurado (APP_SMTP_HOST / APP_SMTP_USER / APP_SMTP_PASSWORD)."
    frm = settings.app_smtp_from or settings.app_smtp_user
    msg = EmailMessage()
    msg["From"] = frm
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
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
