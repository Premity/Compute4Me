"""Master transport: WebSocket control server + HTTP artifact endpoints.

Hosts one persistent WSS connection per Worker (dispatching inbound messages and pushing
``task_assign``/``task_cancel``/``bandwidth_probe``) plus the HTTP artifact channel.
Owns self-signed-cert generation and fingerprint exposure (ADR-0011).

Populated across T06 (TLS), T07 (WS server), T10 (bandwidth probe).

T06 — TLS: the Master holds a self-signed certificate (no CA, no domain); its sha256
fingerprint rides inside every Invite Token and the Worker pins it on connect. This module
generates and persists that cert and computes the fingerprint the token service embeds.

T07 — WS server: ``ControlServer`` accepts one persistent WSS connection per Worker over
that cert, parses inbound ``WorkerMessage``s, and can push ``MasterMessage``s via a
per-Worker send queue. It does the minimal ``join`` work needed to own a connection's
identity — verify the token and ``admit`` (reserve a slot) — so it can ``release`` on
disconnect; the full handshake (``join_ack``/``join_reject``, worker_id assignment, the
heartbeat/reconnect loop) lands in T08.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import hashlib
import json
import ssl
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from pydantic import ValidationError
from websockets.asyncio.server import Server, ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from compute4me.master.tokens import InvalidToken
from compute4me.proto.messages import Join, parse_worker_message

if TYPE_CHECKING:
    from pydantic import BaseModel

    from compute4me.master.tokens import TokenService

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


# --- WS control server (T07) -----------------------------------------------


@dataclass
class _Conn:
    """A live Worker connection: its socket, jti (once admitted), and outbound queue."""

    ws: ServerConnection
    send_queue: asyncio.Queue[BaseModel] = field(default_factory=asyncio.Queue)
    jti: str | None = None  # set once a valid `join` is admitted; what we release on close


class ControlServer:
    """The Master's WebSocket control plane: one persistent connection per Worker.

    Verifies the Invite Token on ``join`` and reserves a slot via the token service
    (``admit``), tracking the connection so it can ``release`` the slot when the socket
    closes. Inbound ``WorkerMessage``s are parsed and recorded; ``MasterMessage``s are
    pushed through a per-Worker send queue. The full join handshake (ack/reject replies,
    worker_id assignment, heartbeat timeouts) is layered on in T08.
    """

    def __init__(self, tokens: TokenService, cert: MasterCert) -> None:
        self._tokens = tokens
        self._cert = cert
        self._conns: dict[int, _Conn] = {}
        self._server: Server | None = None

    @property
    def connected_count(self) -> int:
        """Number of currently-open Worker connections."""
        return len(self._conns)

    def is_connected(self, jti: str) -> bool:
        """Whether an admitted connection for ``jti`` is currently open."""
        return any(c.jti == jti for c in self._conns.values())

    def push(self, conn_id: int, message: BaseModel) -> None:
        """Enqueue a ``MasterMessage`` to a connected Worker (drained by its writer task)."""
        self._conns[conn_id].send_queue.put_nowait(message)

    async def serve(self, host: str, port: int) -> None:
        """Start listening for WSS connections (runs until the server is closed)."""
        ssl_ctx = server_ssl_context(self._cert)
        self._server = await serve(self._handle, host, port, ssl=ssl_ctx)

    async def close(self) -> None:
        """Stop the listener and drop all connections."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    @property
    def port(self) -> int:
        """The bound port (useful when listening on port 0 / ephemeral)."""
        assert self._server is not None, "serve() must be called before reading port"
        # websockets exposes the underlying asyncio server's sockets.
        sock = next(iter(self._server.sockets))
        return int(sock.getsockname()[1])

    async def _handle(self, ws: ServerConnection) -> None:
        """Per-connection lifecycle: register, read+dispatch until close, then release."""
        conn = _Conn(ws=ws)
        conn_id = id(conn)
        self._conns[conn_id] = conn
        writer = asyncio.create_task(self._writer(conn))
        try:
            async for raw in ws:
                self._dispatch(conn, raw)
        except ConnectionClosed:
            pass
        finally:
            writer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await writer
            # Free the token slot reserved at admit time (T05 release).
            if conn.jti is not None:
                self._tokens.release(conn.jti)
            self._conns.pop(conn_id, None)

    def _dispatch(self, conn: _Conn, raw: str | bytes) -> None:
        """Parse one inbound frame and act on it; malformed/unknown frames are dropped."""
        try:
            data = json.loads(raw)
            message = parse_worker_message(data)
        except (json.JSONDecodeError, ValidationError):
            return  # unknown/garbled message — tolerated (wire-protocol.md §Versioning)
        if isinstance(message, Join):
            self._on_join(conn, message)
        # heartbeat / task_progress / task_result / profile_update: tracked by the mere
        # fact of an open, admitted connection in T07; their handlers arrive in T08+.

    def _on_join(self, conn: _Conn, message: Join) -> None:
        """Minimal join: verify the token and reserve a slot; record the jti for release."""
        try:
            claims = self._tokens.verify(message.token)
        except InvalidToken:
            return  # T08 replies with join_reject; T07 simply doesn't admit.
        if self._tokens.admit(claims):
            conn.jti = claims.jti

    async def _writer(self, conn: _Conn) -> None:
        """Drain the per-Worker send queue to the socket as JSON frames."""
        while True:
            message = await conn.send_queue.get()
            await conn.ws.send(message.model_dump_json())
