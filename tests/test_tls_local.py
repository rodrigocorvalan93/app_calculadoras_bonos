"""HTTPS local del add-in: certificados (backend.tools.https_local) y puente
TLS (backend.services.tls_bridge).

El puente se prueba de punta a punta con sockets reales en puertos efímeros:
un backend dummy captura el head crudo que le llega (para verificar la
reescritura X-Forwarded-* / Connection) y responde por el pipe. httpx valida
el certificado contra la CA generada — o sea, el mismo camino que va a hacer
el webview de Office."""
from __future__ import annotations

import asyncio
import ssl

import httpx
import pytest

from backend.tools import https_local


@pytest.fixture(scope="module")
def certs(tmp_path_factory):
    d = tmp_path_factory.mktemp("certs")
    res = https_local.generate(d, ["localhost", "127.0.0.1", "::1"])
    assert res["regenerated"]
    return res


# ── Certificados ─────────────────────────────────────────────────────────────
def test_certs_validos_y_firmados_por_la_ca(certs):
    from cryptography import x509
    from cryptography.hazmat.primitives.asymmetric import padding

    leaf_pem = certs["leaf_cert"].read_bytes()
    ca = x509.load_pem_x509_certificate(certs["ca_cert"].read_bytes())
    leaf = x509.load_pem_x509_certificate(leaf_pem)

    san = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    dns = set(san.get_values_for_type(x509.DNSName))
    ips = {str(i) for i in san.get_values_for_type(x509.IPAddress)}
    assert "localhost" in dns and {"127.0.0.1", "::1"} <= ips

    # la hoja está firmada por la CA (mismo issuer + firma verificable)
    assert leaf.issuer == ca.subject
    ca.public_key().verify(leaf.signature, leaf.tbs_certificate_bytes,
                           padding.PKCS1v15(), leaf.signature_hash_algorithm)
    # fullchain: hoja + CA en el mismo pem (lo que espera load_cert_chain)
    assert leaf_pem.count(b"BEGIN CERTIFICATE") == 2

    # CDP: sin punto de CRL, el schannel estricto (curl / runtime de Excel en
    # máquinas corporativas) corta con CRYPT_E_NO_REVOCATION_CHECK
    cdp = leaf.extensions.get_extension_for_class(x509.CRLDistributionPoints).value
    uris = {str(n.value) for dp in cdp for n in dp.full_name}
    assert set(https_local.default_crl_urls()) <= uris


def test_certs_idempotente_y_force(certs):
    d = certs["leaf_cert"].parent
    res2 = https_local.generate(d, ["localhost", "127.0.0.1", "::1"])
    assert not res2["regenerated"] and res2["reason"] == "vigente"
    # un host nuevo que el SAN no cubre fuerza la regeneración
    res3 = https_local.generate(d, ["localhost", "127.0.0.1", "::1", "10.1.2.3"])
    assert res3["regenerated"] and "10.1.2.3" in res3["reason"]


def test_ca_se_reusa_y_san_se_une(certs):
    """Regenerar la hoja NO cambia la CA (la confianza instalada con certutil
    sigue valiendo) y el SAN nuevo es la UNIÓN con el anterior — clave para
    dos máquinas que comparten certs/ vía OneDrive (hostnames distintos): sin
    unión se pisaban los hosts mutuamente en un loop de regeneraciones."""
    from cryptography import x509

    d = certs["leaf_cert"].parent
    ca_antes = certs["ca_cert"].read_bytes()
    res = https_local.generate(d, ["localhost", "127.0.0.1", "::1", "10.9.9.9"])
    assert res["regenerated"] and res["ca_reused"]
    assert certs["ca_cert"].read_bytes() == ca_antes         # misma CA en disco

    leaf = x509.load_pem_x509_certificate(certs["leaf_cert"].read_bytes())
    ca = x509.load_pem_x509_certificate(ca_antes)
    assert leaf.issuer == ca.subject                          # firmada por la CA vieja
    san = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    ips = {str(i) for i in san.get_values_for_type(x509.IPAddress)}
    # el host nuevo Y el del test anterior (10.1.2.3, ya en el SAN previo)
    assert {"10.9.9.9", "10.1.2.3", "127.0.0.1"} <= ips


def test_cert_viejo_sin_cdp_se_regenera(tmp_path):
    """Un cert generado para OTRO punto CRL (p.ej. versión vieja del código u
    otro puerto) se detecta y regenera solo."""
    otro = ["http://127.0.0.1:9000/excel/crl"]
    res = https_local.generate(tmp_path, ["localhost"], crl_urls=otro)
    assert res["regenerated"]
    res2 = https_local.generate(tmp_path, ["localhost"])      # CDP default (8000)
    assert res2["regenerated"] and "CDP" in res2["reason"]
    assert res2["ca_reused"]


def test_crl_firmada_y_fresca(certs):
    import datetime as dt

    from cryptography import x509

    d = certs["leaf_cert"].parent
    der = https_local.build_crl(d)
    crl = x509.load_der_x509_crl(der)
    ca = x509.load_pem_x509_certificate(certs["ca_cert"].read_bytes())
    assert crl.issuer == ca.subject
    assert crl.is_signature_valid(ca.public_key())
    vence = getattr(crl, "next_update_utc", None)
    if vence is None:
        vence = crl.next_update.replace(tzinfo=dt.timezone.utc)
    assert vence > dt.datetime.now(dt.timezone.utc)
    assert len(list(crl)) == 0                               # vacía: nada revocado


# ── Puente TLS ───────────────────────────────────────────────────────────────
class _DummyBackend:
    """Server http mínimo: guarda el head crudo de cada request y contesta."""

    def __init__(self):
        self.heads = []
        self.server = None
        self.port = None

    async def start(self):
        async def handle(r, w):
            head = await r.readuntil(b"\r\n\r\n")
            self.heads.append(head)
            # body si hay content-length (el puente lo pipea aparte del head)
            low = head.lower()
            if b"content-length:" in low:
                n = int(low.split(b"content-length:")[1].split(b"\r\n")[0])
                body = await r.readexactly(n) if n else b""
            else:
                body = b""
            out = b"pong:" + body
            w.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n"
                    b"Content-Length: " + str(len(out)).encode() +
                    b"\r\nConnection: close\r\n\r\n" + out)
            await w.drain()
            w.close()

        self.server = await asyncio.start_server(handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def stop(self):
        self.server.close()
        await self.server.wait_closed()


async def _bridge_up(certs, target_port):
    from backend.services.tls_bridge import TlsBridge

    bridge = TlsBridge(certs["leaf_cert"], certs["leaf_key"], "127.0.0.1", 0,
                       "127.0.0.1", target_port)
    await bridge.start()
    bridge.port = bridge._server.sockets[0].getsockname()[1]
    return bridge


async def test_bridge_reescribe_forwarded_y_pipea(certs):
    back = _DummyBackend()
    await back.start()
    bridge = await _bridge_up(certs, back.port)
    try:
        ctx = ssl.create_default_context(cafile=str(certs["ca_cert"]))
        async with httpx.AsyncClient(verify=ctx) as c:
            # el cliente intenta spoofear el scheme: el puente lo PISA
            r = await c.get(f"https://127.0.0.1:{bridge.port}/hola",
                            headers={"X-Forwarded-Proto": "http",
                                     "X-Forwarded-For": "6.6.6.6"})
            assert r.status_code == 200 and r.text == "pong:"
            r2 = await c.post(f"https://127.0.0.1:{bridge.port}/eco", content=b"cuerpo")
            assert r2.text == "pong:cuerpo"
    finally:
        await bridge.stop()
        await back.stop()

    for head in back.heads:
        low = head.lower()
        assert low.count(b"x-forwarded-proto:") == 1
        assert b"x-forwarded-proto: https" in low          # el spoof no pasó
        assert b"6.6.6.6" not in low
        assert low.count(b"\r\nconnection:") == 1 and b"connection: close" in low


async def test_stop_cancela_conexiones_en_vuelo(certs):
    """El shutdown (p.ej. auto-reload) cancela y DRENA las conexiones vivas:
    antes quedaban tasks pendientes al cerrarse el loop y asyncio ensuciaba el
    log con 'Task was destroyed but it is pending!' por cada add-in conectado."""
    back = _DummyBackend()
    await back.start()
    bridge = await _bridge_up(certs, back.port)
    ctx = ssl.create_default_context(cafile=str(certs["ca_cert"]))
    # head INCOMPLETO: _handle queda esperando en readuntil (conexión en vuelo)
    _, w = await asyncio.open_connection("127.0.0.1", bridge.port, ssl=ctx)
    w.write(b"GET /colgada HTTP/1.1\r\n")
    await w.drain()
    for _ in range(50):                      # hasta que el server registre el task
        if bridge._tasks:
            break
        await asyncio.sleep(0.01)
    assert bridge._tasks
    await asyncio.wait_for(bridge.stop(), 5)  # no cuelga y drena todo
    assert not bridge._tasks
    w.close()
    await back.stop()


async def test_bridge_502_si_el_target_no_esta(certs):
    # puerto efímero cerrado: abrir y cerrar un server para reservar uno libre
    tmp = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
    puerto_muerto = tmp.sockets[0].getsockname()[1]
    tmp.close()
    await tmp.wait_closed()

    bridge = await _bridge_up(certs, puerto_muerto)
    try:
        ctx = ssl.create_default_context(cafile=str(certs["ca_cert"]))
        async with httpx.AsyncClient(verify=ctx) as c:
            r = await c.get(f"https://127.0.0.1:{bridge.port}/x")
            assert r.status_code == 502
    finally:
        await bridge.stop()
