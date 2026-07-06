"""El WS del broker debe validar TLS con el bundle de certifi.

Regresión del bug de macOS: el Python de python.org no carga los CA del
sistema → `websockets.connect` (default ssl) moría con
CERTIFICATE_VERIFY_FAILED en cada conexión y el feed nunca levantaba,
aunque el login REST (httpx, que trae certifi) funcionara.
"""
from __future__ import annotations

import ssl

from backend.services.primary_ws import _ssl_context_for


def test_wss_gets_certifi_context() -> None:
    ctx = _ssl_context_for("wss://api.latinsecurities.matrizoms.com.ar/")
    assert isinstance(ctx, ssl.SSLContext)
    # Verificación estricta intacta (nada de deshabilitar TLS)…
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True
    # …y con CAs realmente cargadas (el default vacío de macOS es el bug).
    assert len(ctx.get_ca_certs()) > 0


def test_plain_ws_needs_no_context() -> None:
    assert _ssl_context_for("ws://localhost:9999/") is None
