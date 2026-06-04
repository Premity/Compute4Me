"""T07 acceptance: a client connects over WSS, exchanges a heartbeat, is tracked connected,
and closing the socket marks it disconnected and frees the token slot (release).

This is a network-touching integration test: a real `ControlServer` listens on an ephemeral
localhost port over the T06 self-signed cert, and a real websockets client drives the wire
protocol. The async body runs under `asyncio.run` so no pytest-async plugin is needed.
"""

from __future__ import annotations

import asyncio
import ssl
from datetime import timedelta
from pathlib import Path

import pytest
from websockets.asyncio.client import connect

from compute4me.master.server import ControlServer, ensure_cert
from compute4me.master.state import StateStore
from compute4me.master.tokens import TokenService
from compute4me.proto.messages import Heartbeat, Join, JoinAck

_KEY = "test-signing-key-padded-to-32-bytes-min"


def _client_ssl() -> ssl.SSLContext:
    # Self-signed Master cert: skip chain/hostname checks (the Worker pins by fingerprint;
    # the pinning check itself is covered in T06's test_tls.py).
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


async def _wait_until(predicate: object, timeout: float = 2.0) -> bool:
    """Poll `predicate()` until true or timeout (the server updates state on another task)."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if predicate():  # type: ignore[operator]
            return True
        await asyncio.sleep(0.01)
    return False


@pytest.mark.integration
@pytest.mark.task("T07")
def test_client_connects_heartbeats_and_release_on_close(tmp_path: Path) -> None:
    async def scenario() -> None:
        cert = ensure_cert(tmp_path)
        store = StateStore(":memory:")
        tokens = TokenService(signing_key=_KEY, cert_fp=cert.fingerprint, store=store)
        token = tokens.issue(room="lab", max_workers=1, ttl=timedelta(days=30))
        jti = tokens.verify(token).jti

        server = ControlServer(tokens=tokens, cert=cert, store=store)
        await server.serve("127.0.0.1", 0)
        url = f"wss://127.0.0.1:{server.port}"

        try:
            async with connect(url, ssl=_client_ssl()) as ws:
                await ws.send(Join(token=token, profile=_profile_json()).model_dump_json())
                await ws.send(Heartbeat(worker_id="w1", task_id="t1").model_dump_json())

                # Master tracks the connection, and the admitted slot is taken.
                assert await _wait_until(lambda: server.is_connected(jti))
                assert server.connected_count == 1
                # max_workers=1 was consumed by the join → a second admit is refused.
                assert tokens.admit(tokens.verify(token)) is False

            # Socket closed: the Master deregisters and releases the slot.
            assert await _wait_until(lambda: server.connected_count == 0)
            assert await _wait_until(lambda: not server.is_connected(jti))
            # release() ran → the freed slot admits again.
            assert tokens.admit(tokens.verify(token)) is True
        finally:
            await server.close()

    asyncio.run(scenario())


@pytest.mark.integration
@pytest.mark.task("T07")
def test_server_can_push_to_connected_worker(tmp_path: Path) -> None:
    async def scenario() -> None:
        from compute4me.proto.messages import BandwidthProbe, parse_master_message

        cert = ensure_cert(tmp_path)
        store = StateStore(":memory:")
        tokens = TokenService(signing_key=_KEY, cert_fp=cert.fingerprint, store=store)
        token = tokens.issue(room="lab", max_workers=1, ttl=timedelta(days=30))
        jti = tokens.verify(token).jti

        server = ControlServer(tokens=tokens, cert=cert, store=store)
        await server.serve("127.0.0.1", 0)
        url = f"wss://127.0.0.1:{server.port}"

        try:
            async with connect(url, ssl=_client_ssl()) as ws:
                await ws.send(Join(token=token, profile=_profile_json()).model_dump_json())
                # The handshake reply (join_ack) arrives first; drain it.
                ack = await asyncio.wait_for(ws.recv(), timeout=2.0)
                assert isinstance(parse_master_message(_loads(ack)), JoinAck)
                assert await _wait_until(lambda: server.is_connected(jti))

                # Push a MasterMessage through the per-Worker send queue.
                conn_id = next(iter(server._conns))  # test inspects the connection registry
                server.push(conn_id, BandwidthProbe())

                raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                assert isinstance(parse_master_message(_loads(raw)), BandwidthProbe)
        finally:
            await server.close()

    asyncio.run(scenario())


def _profile_json() -> object:
    from compute4me.types import CapabilityProfile, GpuInfo

    return CapabilityProfile(
        host_id="h1",
        gpu=GpuInfo(model="cpu", vram_total_mb=0, vram_free_mb=0),
        cpu_cores=4,
        ram_mb=8000,
        disk_free_mb=100000,
        datasets_cached=[],
        throughput_ref=100.0,
        bandwidth_to_master_mbps=50.0,
        rtt_to_master_ms=20.0,
    )


def _loads(raw: object) -> dict[str, object]:
    import json

    return json.loads(raw)  # type: ignore[arg-type]
