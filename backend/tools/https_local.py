"""Certificado HTTPS local para el add-in de Excel (funciones custom).

Office EXIGE HTTPS para el runtime de funciones custom: sobre http el
taskpane anda igual (por eso el panel conecta y "Probar" da OK), pero el
runtime de las celdas =OMS.* nunca termina de arrancar — Excel queda en
"Se está iniciando el runtime de los complementos…", re-baja
functions.html/js/json en loop y las celdas dan #N/D. La solución es un
manifest con URLs https, y para eso hace falta un certificado local que la
máquina confíe.

Este módulo hace lo mismo que mkcert, sin instalar nada extra:

  1. genera una CA local propia (una por máquina) y un certificado para
     localhost / 127.0.0.1 / ::1 / la IP LAN, firmado por esa CA;
  2. en Windows, confía la CA en el store DEL USUARIO con
     `certutil -user -addstore -f Root` (no pide admin; WebView2/Edge/Chrome
     leen ese store — es lo que valida el webview de Office).

Con los archivos presentes, el puente TLS (backend/services/tls_bridge.py)
levanta https://localhost:8443 al arrancar la app y el manifest se baja de
ahí. El .bat corre esta herramienta en cada arranque: es idempotente (si el
cert está vigente y cubre los hosts, no toca nada y sale al instante).

    python -m backend.tools.https_local            # generar/renovar si hace falta
    python -m backend.tools.https_local --force    # regenerar sí o sí
    python -m backend.tools.https_local --host 192.168.0.50   # SAN extra

La clave de la CA queda en certs/ (gitignored), igual que con mkcert: no se
comparte; sólo firma hosts locales. El certificado (público) de la CA se
puede bajar de /excel/ca.crt para confiarlo en otra compu de la mesa.
"""
from __future__ import annotations

import argparse
import datetime as dt
import ipaddress
import socket
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

# Nombres fijos: el puente TLS y /excel/ca.crt los buscan tal cual.
CA_CERT = "oms-local-ca.crt"
CA_KEY = "oms-local-ca.key"
LEAF_CERT = "oms-localhost.pem"      # fullchain: hoja + CA
LEAF_KEY = "oms-localhost-key.pem"

_RENOVAR_ANTES_DIAS = 30             # margen antes del vencimiento de la hoja


def default_cert_dir() -> Path:
    """certs/ en la raíz del repo (gitignored por el paradigma whitelist)."""
    return Path(__file__).resolve().parent.parent.parent / "certs"


def _lan_ip() -> Optional[str]:
    """IP LAN primaria (mismo truco UDP-connect que backend.routes.excel.lan_ip,
    copiado acá para que la herramienta no importe el stack de la app)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        finally:
            s.close()
        return ip if ip and not ip.startswith("127.") else None
    except OSError:
        return None


def wanted_hosts(extra: Optional[List[str]] = None) -> List[str]:
    """Hosts que el certificado tiene que cubrir. localhost siempre; la IP LAN
    si existe (para el flujo server centralizado); extras por CLI/env."""
    hosts = ["localhost", "127.0.0.1", "::1"]
    ip = _lan_ip()
    if ip:
        hosts.append(ip)
    hostname = socket.gethostname().lower()
    if hostname and hostname not in hosts:
        hosts.append(hostname)
    for h in extra or []:
        h = h.strip().lower()
        if h and h not in hosts:
            hosts.append(h)
    return hosts


def _san_objects(hosts: List[str]):
    from cryptography import x509
    out = []
    for h in hosts:
        try:
            out.append(x509.IPAddress(ipaddress.ip_address(h)))
        except ValueError:
            out.append(x509.DNSName(h))
    return out


def _leaf_ok(cert_dir: Path, hosts: List[str]) -> Tuple[bool, str]:
    """(vigente_y_cubre_todo, motivo si no)."""
    from cryptography import x509

    leaf_path = cert_dir / LEAF_CERT
    for name in (CA_CERT, CA_KEY, LEAF_CERT, LEAF_KEY):
        if not (cert_dir / name).exists():
            return False, f"falta {name}"
    try:
        cert = x509.load_pem_x509_certificate(leaf_path.read_bytes())
    except Exception:  # noqa: BLE001 — archivo roto ⇒ regenerar
        return False, f"{LEAF_CERT} ilegible"
    limite = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=_RENOVAR_ANTES_DIAS)
    # not_valid_after_utc llegó en cryptography 42; con 41 el naive es UTC.
    vence = getattr(cert, "not_valid_after_utc", None)
    if vence is None:
        vence = cert.not_valid_after.replace(tzinfo=dt.timezone.utc)
    if vence <= limite:
        return False, f"vence {vence:%d/%m/%Y}"
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        have = {str(v).lower() for v in san.get_values_for_type(x509.DNSName)}
        have |= {str(v) for v in san.get_values_for_type(x509.IPAddress)}
    except Exception:  # noqa: BLE001
        return False, "sin SAN"
    faltan = [h for h in hosts if h.lower() not in have and h not in have]
    if faltan:
        return False, f"SAN sin {', '.join(faltan)}"
    return True, ""


def generate(cert_dir: Optional[Path] = None, hosts: Optional[List[str]] = None,
             force: bool = False) -> dict:
    """Genera (si hace falta) CA + certificado hoja. Devuelve un dict con
    `regenerated` y los paths. Lanza ImportError si falta `cryptography`."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    cert_dir = cert_dir or default_cert_dir()
    hosts = hosts or wanted_hosts()
    cert_dir.mkdir(parents=True, exist_ok=True)
    paths = {"ca_cert": cert_dir / CA_CERT, "ca_key": cert_dir / CA_KEY,
             "leaf_cert": cert_dir / LEAF_CERT, "leaf_key": cert_dir / LEAF_KEY}

    if not force:
        ok, motivo = _leaf_ok(cert_dir, hosts)
        if ok:
            return {"regenerated": False, "reason": "vigente", "hosts": hosts, **paths}
    else:
        motivo = "--force"

    now = dt.datetime.now(dt.timezone.utc)
    atras = now - dt.timedelta(days=1)          # margen por relojes corridos

    # CA local (una por máquina; el hostname en el CN la identifica en el store)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, f"OMS Bonos CA local ({socket.gethostname()})"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "OMS Bonos"),
    ])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name).issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(atras).not_valid_after(now + dt.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=False, content_commitment=False,
                                     key_encipherment=False, data_encipherment=False,
                                     key_agreement=False, key_cert_sign=True,
                                     crl_sign=True, encipher_only=False,
                                     decipher_only=False), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),
                       critical=False)
        .sign(ca_key, hashes.SHA256())
    )

    # Certificado hoja para los hosts locales
    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "OMS Bonos local")]))
        .issuer_name(ca_name)
        .public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(atras).not_valid_after(now + dt.timedelta(days=825))
        .add_extension(x509.SubjectAlternativeName(_san_objects(hosts)), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False,
                                     key_encipherment=True, data_encipherment=False,
                                     key_agreement=False, key_cert_sign=False,
                                     crl_sign=False, encipher_only=False,
                                     decipher_only=False), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
                       critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
                       critical=False)
        .sign(ca_key, hashes.SHA256())
    )

    pem = serialization.Encoding.PEM
    paths["ca_cert"].write_bytes(ca_cert.public_bytes(pem))
    paths["ca_key"].write_bytes(ca_key.private_bytes(
        pem, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
    # fullchain (hoja + CA): lo que espera ssl.load_cert_chain / el puente TLS
    paths["leaf_cert"].write_bytes(leaf.public_bytes(pem) + ca_cert.public_bytes(pem))
    paths["leaf_key"].write_bytes(leaf_key.private_bytes(
        pem, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
    return {"regenerated": True, "reason": motivo, "hosts": hosts, **paths}


def trust_ca_windows(ca_cert_path: Path) -> Tuple[bool, str]:
    """Confía la CA en el store Root DEL USUARIO (certutil -user: sin admin;
    WebView2/Edge/Chrome lo leen). Idempotente con -f. Sólo Windows."""
    if sys.platform != "win32":
        return False, "no-windows (confiar a mano si hace falta)"
    try:
        r = subprocess.run(
            ["certutil", "-user", "-addstore", "-f", "Root", str(ca_cert_path)],
            capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:  # certutil siempre está en Windows
        return False, f"certutil no corrió: {e}"
    if r.returncode == 0:
        return True, "CA confiada en el usuario actual (certutil Root)"
    detalle = (r.stderr or r.stdout or "").strip().splitlines()
    return False, f"certutil rc={r.returncode}: {detalle[-1] if detalle else '?'}"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Certificado HTTPS local del add-in de Excel")
    ap.add_argument("--force", action="store_true", help="regenerar aunque esté vigente")
    ap.add_argument("--host", action="append", default=[],
                    help="host/IP extra para el SAN (repetible)")
    ap.add_argument("--dir", default="", help="carpeta destino (default: <repo>/certs)")
    ap.add_argument("--quiet", action="store_true", help="sólo errores")
    args = ap.parse_args(argv)

    def say(msg: str) -> None:
        if not args.quiet:
            print(msg)

    try:
        import cryptography  # noqa: F401
    except ImportError:
        print("[https] falta el paquete `cryptography` → sin HTTPS local; las funciones "
              "=OMS.* de Excel no van a arrancar (el resto de la app sigue igual).")
        print("[https] instalar con:  pip install cryptography")
        return 1

    cert_dir = Path(args.dir) if args.dir else default_cert_dir()
    res = generate(cert_dir, wanted_hosts(args.host), force=args.force)
    if res["regenerated"]:
        say(f"[https] certificado nuevo en {cert_dir} para: {', '.join(res['hosts'])}")
        ok, det = trust_ca_windows(res["ca_cert"])
        say(f"[https] {det}" if ok else f"[https] CA no confiada automáticamente: {det}")
        if not ok and sys.platform == "win32":
            print(f"[https] a mano:  certutil -user -addstore -f Root {res['ca_cert']}")
    else:
        say(f"[https] certificado vigente en {cert_dir} (cubre {', '.join(res['hosts'])}) — nada que hacer")
        # Re-asegurar la confianza es gratis e idempotente (p.ej. certs copiados
        # de otra máquina, o el store del usuario limpiado).
        ok, det = trust_ca_windows(res["ca_cert"])
        if not ok and sys.platform == "win32":
            print(f"[https] OJO, la CA no está confiable: {det}")
    say("[https] el manifest del add-in se baja de https://localhost:8443/excel/manifest.xml "
        "(el puente TLS arranca solo con la app)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
