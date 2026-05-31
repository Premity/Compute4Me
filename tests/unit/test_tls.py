"""T06 acceptance: self-signed cert gen/persist + fingerprint pinning over a real TLS handshake.

The handshake tests stand up a real TLS server (stdlib `ssl`, background thread) presenting
the Master's self-signed cert, then connect a client that pins the fingerprint the way the
Worker daemon will: chain verification off, identity established by comparing the presented
cert's sha256 to the token's pinned value. No CA, no domain, no WebSocket/app layer.
"""

from __future__ import annotations

import socket
import ssl
import threading
from pathlib import Path

import pytest

from compute4me.master.server import ensure_cert, fingerprint_of, server_ssl_context
from compute4me.worker.daemon import CertPinError, verify_fingerprint


@pytest.mark.unit
@pytest.mark.task("T06")
def test_ensure_cert_generates_files_and_fingerprint(tmp_path: Path) -> None:
    cert = ensure_cert(tmp_path)

    assert cert.cert_path.exists()
    assert cert.key_path.exists()
    # sha256 hex is 64 chars.
    assert len(cert.fingerprint) == 64
    assert cert.fingerprint == fingerprint_of(cert.cert_path)


@pytest.mark.unit
@pytest.mark.task("T06")
def test_ensure_cert_is_idempotent_across_restart(tmp_path: Path) -> None:
    first = ensure_cert(tmp_path)
    cert_bytes = first.cert_path.read_bytes()

    # A "restart" reopening the same data dir must reuse the cert, not regenerate it —
    # else every restart would invalidate already-issued tokens.
    second = ensure_cert(tmp_path)

    assert second.fingerprint == first.fingerprint
    assert second.cert_path.read_bytes() == cert_bytes


@pytest.mark.unit
@pytest.mark.task("T06")
def test_distinct_data_dirs_get_distinct_fingerprints(tmp_path: Path) -> None:
    a = ensure_cert(tmp_path / "a")
    b = ensure_cert(tmp_path / "b")

    assert a.fingerprint != b.fingerprint


@pytest.mark.unit
@pytest.mark.task("T06")
def test_verify_fingerprint_matches_and_mismatches(tmp_path: Path) -> None:
    cert = ensure_cert(tmp_path)
    der = ssl.PEM_cert_to_DER_cert(cert.cert_path.read_text())

    # Match: no raise.
    verify_fingerprint(der, cert.fingerprint)
    # Case-insensitive on the hex.
    verify_fingerprint(der, cert.fingerprint.upper())
    # Mismatch: raises.
    with pytest.raises(CertPinError):
        verify_fingerprint(der, "00" * 32)


def _serve_one_tls_connection(ctx: ssl.SSLContext, ready: threading.Event) -> int:
    """Bind a TLS server on an ephemeral port, signal readiness, accept one connection."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]

    def _accept() -> None:
        ready.wait(timeout=5)
        try:
            raw, _ = listener.accept()
            with ctx.wrap_socket(raw, server_side=True) as tls:
                tls.recv(16)  # complete the handshake; drain a byte
        except (OSError, ssl.SSLError):
            pass  # client refused after inspecting the cert — expected in the mismatch case
        finally:
            listener.close()

    threading.Thread(target=_accept, daemon=True).start()
    return port


@pytest.mark.unit
@pytest.mark.task("T06")
def test_worker_connects_when_fingerprint_matches(tmp_path: Path) -> None:
    cert = ensure_cert(tmp_path)
    ready = threading.Event()
    port = _serve_one_tls_connection(server_ssl_context(cert), ready)

    client_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    client_ctx.check_hostname = False
    client_ctx.verify_mode = ssl.CERT_NONE
    ready.set()
    with (
        socket.create_connection(("127.0.0.1", port), timeout=5) as raw,
        client_ctx.wrap_socket(raw, server_hostname="compute4me-master") as tls,
    ):
        peer_der = tls.getpeercert(binary_form=True)

    assert peer_der is not None
    # Matching fingerprint: the Worker accepts the connection.
    verify_fingerprint(peer_der, cert.fingerprint)


@pytest.mark.unit
@pytest.mark.task("T06")
def test_worker_refuses_when_fingerprint_mismatches(tmp_path: Path) -> None:
    # The Master presents cert A; the Worker's token pins cert B's fingerprint.
    master = ensure_cert(tmp_path / "master")
    impostor_fp = ensure_cert(tmp_path / "impostor").fingerprint
    ready = threading.Event()
    port = _serve_one_tls_connection(server_ssl_context(master), ready)

    client_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    client_ctx.check_hostname = False
    client_ctx.verify_mode = ssl.CERT_NONE
    ready.set()
    with (
        socket.create_connection(("127.0.0.1", port), timeout=5) as raw,
        client_ctx.wrap_socket(raw, server_hostname="compute4me-master") as tls,
    ):
        peer_der = tls.getpeercert(binary_form=True)

    assert peer_der is not None
    # Pinned fingerprint doesn't match the presented cert -> the Worker refuses.
    with pytest.raises(CertPinError):
        verify_fingerprint(peer_der, impostor_fp)
