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


async def test_stop_no_deadlockea_con_respuesta_en_vuelo(certs):
    """Regresión del deadlock de shutdown: en Python ≥3.12 Server.wait_closed()
    espera a que TODOS los handlers terminen, y stop() lo llamaba ANTES de
    cancelarlos — con una conexión a mitad de respuesta (p.ej. el webview de
    Office suspendido mientras el add-in descargaba algo) el shutdown quedaba
    eterno y el auto-reload de uvicorn nunca relevaba el proceso (join sin
    timeout): la app no volvía hasta matarla a mano. stop() debe cancelar
    primero y volver acotado. En 3.11 wait_closed() no espera handlers, así
    que el deadlock sólo se manifiesta corriendo 3.12+ (la máquina real)."""
    mudos: list = []

    async def _mudo(r, w):
        # target que lee el head y NUNCA responde: el handler del puente queda
        # en el pump target→cliente, que no tiene (ni debe tener) timeout.
        mudos.append(asyncio.current_task())
        try:
            await r.readuntil(b"\r\n\r\n")
            await asyncio.sleep(3600)
        except (asyncio.IncompleteReadError, asyncio.CancelledError, OSError):
            pass

    tgt = await asyncio.start_server(_mudo, "127.0.0.1", 0)
    bridge = await _bridge_up(certs, tgt.sockets[0].getsockname()[1])
    try:
        ctx = ssl.create_default_context(cafile=str(certs["ca_cert"]))
        _, w = await asyncio.open_connection("127.0.0.1", bridge.port, ssl=ctx)
        w.write(b"GET /lenta HTTP/1.1\r\nHost: x\r\n\r\n")   # head COMPLETO
        await w.drain()
        for _ in range(100):                 # handler registrado y pumpeando
            if bridge._tasks and mudos:
                break
            await asyncio.sleep(0.01)
        assert bridge._tasks
        await asyncio.wait_for(bridge.stop(), 5)   # acá deadlockeaba en 3.12+
        assert not bridge._tasks
        w.close()
    finally:
        tgt.close()
        for t in mudos:
            t.cancel()
        await asyncio.gather(*mudos, return_exceptions=True)


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


# ── macOS: hostname con acento y clave del keychain sólo cuando hace falta ───
def test_hostname_con_acento_no_entra_al_san_ni_regenera_en_loop(tmp_path, monkeypatch):
    """Un hostname que no puede ir al SAN (Mac "MacBook-de-…-Corvalán.local")
    se filtra en wanted_hosts. Antes quedaba en `hosts` sin entrar al SAN y
    `_leaf_ok` regeneraba la hoja en CADA arranque — en macOS, pedir la clave
    del keychain cada vez."""
    monkeypatch.setattr(https_local.socket, "gethostname", lambda: "MacBook-de-Rodrigo-Corvalán.local")
    monkeypatch.setattr(https_local, "_lan_ip", lambda: None)
    hosts = https_local.wanted_hosts(["otra-máquina.local", "10.0.0.7"])
    assert hosts == ["localhost", "127.0.0.1", "::1", "10.0.0.7"]
    assert not https_local._san_ok("macbook-de-rodrigo-corvalán.local")
    assert https_local._san_ok("macbook-de-rodrigo.local") and https_local._san_ok("::1")
    res = https_local.generate(tmp_path, hosts)
    assert res["regenerated"]
    res2 = https_local.generate(tmp_path, https_local.wanted_hosts(["otra-máquina.local", "10.0.0.7"]))
    assert not res2["regenerated"] and res2["reason"] == "vigente"


def test_macos_no_pide_la_clave_si_la_ca_ya_esta_confiada(tmp_path, monkeypatch, capsys):
    """En macOS `security add-trusted-cert` abre el diálogo de la clave del
    usuario. Con la CA reusada y ya confiada (hoja nueva por cambio de red /
    IP) no se llama; con la CA nueva o no confiada, sí."""
    llamadas = []
    confiada = {"ok": True}

    class _R:
        def __init__(self, rc):
            self.returncode, self.stdout, self.stderr = rc, "", ""

    def fake_run(argv, **kw):
        llamadas.append(argv)
        if argv[:2] == ["security", "verify-cert"]:
            return _R(0 if confiada["ok"] else 1)
        return _R(0)

    monkeypatch.setattr(https_local, "_PLATFORM", "darwin")
    monkeypatch.setattr(https_local.subprocess, "run", fake_run)
    monkeypatch.setattr(https_local, "wanted_hosts", lambda extra=None: ["localhost", "127.0.0.1"])
    # CA nueva (primer arranque): se instala sí o sí
    assert https_local.main(["--dir", str(tmp_path), "--quiet"]) == 0
    assert any(a[:2] == ["security", "add-trusted-cert"] for a in llamadas)
    # hoja nueva con la MISMA CA, ya confiada: ni un diálogo
    llamadas.clear()
    assert https_local.main(["--dir", str(tmp_path), "--force"]) == 0
    assert any(a[:2] == ["security", "verify-cert"] for a in llamadas)
    assert not any(a[:2] == ["security", "add-trusted-cert"] for a in llamadas)
    assert "no se pide la clave" in capsys.readouterr().out
    # misma CA pero NO confiada (el usuario canceló el diálogo): se vuelve a pedir
    confiada["ok"] = False
    llamadas.clear()
    assert https_local.main(["--dir", str(tmp_path), "--force"]) == 0
    assert any(a[:2] == ["security", "add-trusted-cert"] for a in llamadas)
    # fuera de macOS la sonda no corre nunca
    monkeypatch.setattr(https_local, "_PLATFORM", "linux")
    assert https_local.ca_trusted_macos(tmp_path / "x") is False
    assert https_local.trust_ca_macos(tmp_path / "x") == (False, "no-macos")


def test_cn_de_la_ca_acotado_a_64_bytes_con_hostname_largo(tmp_path, monkeypatch):
    """El CN de la CA lleva el hostname y RFC 5280 lo acota a 64 bytes:
    cryptography lo valida y con un nombre largo (runner de macOS de CI, una
    Mac con nombre de equipo largo) generate() reventaba → sin HTTPS local, el
    add-in de Excel no arrancaba en esa máquina."""
    largo = "MacBook-Pro-de-Rodrigo-Corvalan-del-trabajo-con-nombre-larguisimo-1759020000.local"
    assert len(largo) > https_local._CN_MAX
    cn = https_local._ca_common_name(largo)
    assert cn.startswith("OMS Bonos CA local (MacBook-Pro-de-Rodrigo") and cn.endswith(")")
    assert len(cn.encode("utf-8")) <= https_local._CN_MAX
    assert https_local._ca_common_name("corta.local") == "OMS Bonos CA local (corta.local)"
    assert https_local._ca_common_name("") == "OMS Bonos CA local"
    assert len(https_local._ca_common_name("ñ" * 80).encode("utf-8")) <= https_local._CN_MAX   # bytes, no chars
    monkeypatch.setattr(https_local.socket, "gethostname", lambda: largo)
    res = https_local.generate(tmp_path, ["localhost", "127.0.0.1"])
    assert res["regenerated"] and res["ca_cert"].exists()
    from cryptography import x509
    ca = x509.load_pem_x509_certificate(res["ca_cert"].read_bytes())
    cn_emitido = ca.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)[0].value
    assert cn_emitido == cn
