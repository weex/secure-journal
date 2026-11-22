"""Self-signed certificate for the journal on the LAN.

Browsers will warn because the certificate is not from a public authority.
The name on the certificate is journal.local (and the hostname). Using the
raw IP address may add a name-mismatch warning if that address was not
present when the certificate was created.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID


def generate_certificate(
    directory: Path,
    *,
    hostnames: list[str],
    ips: list[str],
    days: int = 825,
) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    names = []
    seen: set[str] = set()
    for name in hostnames:
        cleaned = name.strip().rstrip(".")
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            names.append(x509.DNSName(cleaned))
    alt_ips = []
    for raw in ips:
        try:
            alt_ips.append(x509.IPAddress(ipaddress.ip_address(raw)))
        except ValueError:
            continue
    if not names:
        names.append(x509.DNSName("journal.local"))
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, names[0].value)])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=days))
        .add_extension(x509.SubjectAlternativeName(names + alt_ips), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    key_path = directory / "key.pem"
    cert_path = directory / "cert.pem"
    key_bytes = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    cert_bytes = cert.public_bytes(serialization.Encoding.PEM)
    _write(key_path, key_bytes, 0o640)
    _write(cert_path, cert_bytes, 0o644)
    return cert_path, key_path


def local_names() -> list[str]:
    host = socket.gethostname().split(".")[0].strip() or "journal"
    names = ["journal.local", host]
    if f"{host}.local" not in names:
        names.append(f"{host}.local")
    return names


def _write(path: Path, data: bytes, mode: int) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.chmod(tmp, mode)
    tmp.replace(path)
