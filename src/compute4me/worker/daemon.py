"""Worker daemon: outbound WS client, join handshake, heartbeat, task loop.

Builds the Capability Profile on start, sends ``join`` and handles ``join_ack``/
``join_reject``, heartbeats every 10s, reconnects with backoff, and dispatches assigned
Tasks to the container runner. Pins the Master's cert fingerprint from its token
(ADR-0011).

Populated across T06 (cert pinning), T08 (join + heartbeat), T17 (task dispatch).

T06 — cert pinning: the Master's cert is self-signed (no CA to validate against), so the
Worker authenticates it by comparing the presented cert's sha256 fingerprint to the one
carried in its Invite Token, refusing the connection on mismatch.
"""

from __future__ import annotations

import hashlib
import ssl


class CertPinError(Exception):
    """Raised when the Master's presented cert does not match the pinned fingerprint."""


def pinning_ssl_context() -> ssl.SSLContext:
    """A TLS client context for a self-signed Master cert.

    Chain/hostname verification is disabled because the Master cert is self-signed and has
    no domain (ADR-0011); trust is established by fingerprint pinning instead — the caller
    MUST follow a successful handshake with :func:`verify_fingerprint` on the peer cert.
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def fingerprint_of_der(cert_der: bytes) -> str:
    """The sha256 fingerprint (hex) of a DER-encoded cert — matches server.fingerprint_of."""
    return hashlib.sha256(cert_der).hexdigest()


def verify_fingerprint(peer_cert_der: bytes, pinned_fingerprint: str) -> None:
    """Compare the Master's presented cert to the token's pinned fingerprint.

    ``peer_cert_der`` is the DER cert from the completed handshake
    (``SSLSocket.getpeercert(binary_form=True)``). Raises :class:`CertPinError` on mismatch;
    returns ``None`` on a match. Comparison is case-insensitive on the hex.
    """
    actual = fingerprint_of_der(peer_cert_der)
    if actual.lower() != pinned_fingerprint.lower():
        raise CertPinError(
            f"Master cert fingerprint mismatch: pinned {pinned_fingerprint}, got {actual}"
        )
