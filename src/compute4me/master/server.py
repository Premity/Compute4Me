"""Master transport: WebSocket control server + HTTP artifact endpoints.

Hosts one persistent WSS connection per Worker (dispatching inbound messages and pushing
``task_assign``/``task_cancel``/``bandwidth_probe``) plus the HTTP artifact channel.
Owns self-signed-cert generation and fingerprint exposure (ADR-0011).

Populated across T06 (TLS), T07 (WS server), T10 (bandwidth probe).

T06 — TLS: the Master holds a self-signed certificate (no CA, no domain); its sha256
fingerprint rides inside every Invite Token and the Worker pins it on connect. This module
generates and persists that cert and computes the fingerprint the token service embeds.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import ssl
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

_CERT_FILE = "master-cert.pem"
_KEY_FILE = "master-key.pem"

# A self-signed cert needs a subject; there's no domain (ADR-0011), so a stable placeholder
# CN is fine — the Worker authenticates by fingerprint, not by name.
_COMMON_NAME = "compute4me-master"
_VALIDITY_DAYS = 3650  # 10y; rotation is an ops action (operations.md), not an expiry concern


@dataclass(frozen=True)
class MasterCert:
    """A Master's self-signed cert on disk plus its pinned fingerprint."""

    cert_path: Path
    key_path: Path
    fingerprint: str  # sha256 hex of the DER cert; what the Worker pins (ADR-0011)


def ensure_cert(data_dir: str | Path) -> MasterCert:
    """Load the Master's self-signed cert from ``data_dir``, generating it on first run.

    Idempotent: subsequent calls load the existing cert (wire-protocol.md §4.10), so the
    fingerprint is stable across restarts and the tokens that embed it stay valid.
    """
    data = Path(data_dir)
    data.mkdir(parents=True, exist_ok=True)
    cert_path = data / _CERT_FILE
    key_path = data / _KEY_FILE

    if not (cert_path.exists() and key_path.exists()):
        _generate_cert(cert_path, key_path)

    return MasterCert(
        cert_path=cert_path,
        key_path=key_path,
        fingerprint=fingerprint_of(cert_path),
    )


def fingerprint_of(cert_path: str | Path) -> str:
    """The sha256 fingerprint (hex) of a PEM cert's DER body — the value pinned in tokens."""
    cert = x509.load_pem_x509_certificate(Path(cert_path).read_bytes())
    der = cert.public_bytes(serialization.Encoding.DER)
    return hashlib.sha256(der).hexdigest()


def server_ssl_context(cert: MasterCert) -> ssl.SSLContext:
    """A TLS server context presenting the Master's self-signed cert."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=str(cert.cert_path), keyfile=str(cert.key_path))
    return ctx


def _generate_cert(cert_path: Path, key_path: Path) -> None:
    """Write a fresh 2048-bit RSA key + self-signed cert to the given paths."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, _COMMON_NAME)])
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)  # self-signed: subject == issuer
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=1))  # small skew tolerance
        .not_valid_after(now + dt.timedelta(days=_VALIDITY_DAYS))
        .sign(key, hashes.SHA256())
    )

    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    # The key authenticates the Master; keep it owner-only.
    key_path.chmod(0o600)
