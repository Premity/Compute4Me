"""Worker daemon: outbound WS client, join handshake, heartbeat, task loop.

Builds the Capability Profile on start, sends ``join`` and handles ``join_ack``/
``join_reject``, heartbeats every 10s, reconnects with backoff, and dispatches assigned
Tasks to the container runner. Pins the Master's cert fingerprint from its token
(ADR-0011).

Populated across T06 (cert pinning), T08 (join + heartbeat), T17 (task dispatch).

T06 — cert pinning: the Master's cert is self-signed (no CA to validate against), so the
Worker authenticates it by comparing the presented cert's sha256 fingerprint to the one
carried in its Invite Token, refusing the connection on mismatch.

T08 — join + heartbeat: ``WorkerDaemon`` opens the outbound WSS connection (pinning the
Master cert), sends ``join`` with its Capability Profile, handles ``join_ack`` (records the
assigned ``worker_id``) / ``join_reject`` (raises), heartbeats on an interval, and
reconnects with exponential backoff after a transient drop. The profile is injected — the
real capability profiler lands in T09.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import ssl
from typing import TYPE_CHECKING

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from compute4me.proto.messages import (
    Heartbeat,
    Join,
    JoinAck,
    JoinReject,
    parse_master_message,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from websockets.asyncio.client import ClientConnection

    from compute4me.types import CapabilityProfile


class CertPinError(Exception):
    """Raised when the Master's presented cert does not match the pinned fingerprint."""


class JoinRejected(Exception):
    """Raised when the Master rejects the join (bad token, capacity, fingerprint)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


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


def _peer_cert_der(ws: ClientConnection) -> bytes:
    """Pull the Master's presented cert (DER) from a connected WSS client for pinning."""
    ssl_object = ws.transport.get_extra_info("ssl_object")
    der: bytes | None = ssl_object.getpeercert(binary_form=True) if ssl_object else None
    if der is None:
        raise CertPinError("no peer certificate presented (connection not TLS?)")
    return der


# --- Worker daemon (T08) ---------------------------------------------------

_INITIAL_BACKOFF = 1.0
_MAX_BACKOFF = 30.0
_HEARTBEAT_INTERVAL = 10.0


class WorkerDaemon:
    """The Worker's outbound control-plane client: join, heartbeat, reconnect.

    Connects to the Master over WSS, pinning its self-signed cert by the fingerprint carried
    in the Invite Token (ADR-0011); sends ``join`` with the Capability Profile and waits for
    ``join_ack`` (recording ``worker_id``) or ``join_reject`` (raises :class:`JoinRejected`);
    then heartbeats every ``heartbeat_interval`` seconds until the socket drops, at which
    point :meth:`run` reconnects with exponential backoff.

    The ``profile`` is injected so the daemon stays testable without real hardware probes;
    T09's capability profiler supplies the real one.
    """

    def __init__(
        self,
        master_url: str,
        token: str,
        cert_fp: str,
        profile: CapabilityProfile,
        *,
        heartbeat_interval: float = _HEARTBEAT_INTERVAL,
    ) -> None:
        self._url = master_url
        self._token = token
        self._cert_fp = cert_fp
        self._profile = profile
        self._heartbeat_interval = heartbeat_interval
        self.worker_id: str | None = None

    async def connect_once(self, on_connected: Callable[[], object] | None = None) -> None:
        """Run one full session: connect, pin, join, then heartbeat until disconnect.

        Raises :class:`JoinRejected` on a ``join_reject`` and :class:`CertPinError` on a
        fingerprint mismatch; returns normally when the Master closes the connection.
        ``on_connected`` (a notify/test hook) fires once the join is acknowledged; it may be
        sync or async (an awaitable return is awaited).
        """
        async with connect(self._url, ssl=pinning_ssl_context()) as ws:
            # Pin the Master's cert before trusting the channel for anything else.
            verify_fingerprint(_peer_cert_der(ws), self._cert_fp)

            await ws.send(Join(token=self._token, profile=self._profile).model_dump_json())
            reply = parse_master_message(_loads(await ws.recv()))
            if isinstance(reply, JoinReject):
                raise JoinRejected(reply.reason)
            if not isinstance(reply, JoinAck):
                raise JoinRejected(f"unexpected reply to join: {type(reply).__name__}")
            self.worker_id = reply.worker_id

            if on_connected is not None:
                result = on_connected()
                if asyncio.iscoroutine(result):
                    await result

            heartbeat = asyncio.create_task(self._heartbeat_loop(ws))
            try:
                async for _ in ws:
                    pass  # task_assign/task_cancel handling lands in T17
            except ConnectionClosed:
                pass
            finally:
                heartbeat.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await heartbeat

    async def run(self, *, max_sessions: int | None = None) -> None:
        """Reconnect loop: run sessions with exponential backoff after transient drops.

        A ``join_reject`` is terminal (the token won't get better by retrying), so it
        propagates. ``max_sessions`` bounds the loop for tests; ``None`` runs forever.
        """
        backoff = _INITIAL_BACKOFF
        sessions = 0
        while max_sessions is None or sessions < max_sessions:
            try:
                await self.connect_once()
                backoff = _INITIAL_BACKOFF  # clean session → reset backoff
            except JoinRejected:
                raise  # not transient
            except (OSError, ConnectionClosed, CertPinError):
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, _MAX_BACKOFF)
            sessions += 1

    async def _heartbeat_loop(self, ws: ClientConnection) -> None:
        """Send a ``heartbeat`` every ``heartbeat_interval`` seconds until cancelled."""
        assert self.worker_id is not None
        while True:
            await ws.send(Heartbeat(worker_id=self.worker_id).model_dump_json())
            await asyncio.sleep(self._heartbeat_interval)


def _loads(raw: str | bytes) -> dict[str, object]:
    import json

    data: dict[str, object] = json.loads(raw)
    return data
