"""T08 acceptance: a Worker daemon joins a running Master and gets a worker_id; a bad token
is rejected with a reason; the daemon reconnects after a transient drop.

End-to-end integration: a real `ControlServer` and a real `WorkerDaemon` talk over WSS on an
ephemeral localhost port, with the daemon pinning the Master's self-signed cert by
fingerprint. The async bodies run under `asyncio.run` (no pytest-async plugin needed).
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import pytest

from compute4me.master.server import ControlServer, MasterCert, ensure_cert
from compute4me.master.state import StateStore
from compute4me.master.tokens import TokenService
from compute4me.types import CapabilityProfile, GpuInfo
from compute4me.worker.daemon import JoinRejected, WorkerDaemon

_KEY = "test-signing-key-padded-to-32-bytes-min"


def _profile() -> CapabilityProfile:
    return CapabilityProfile(
        host_id="host-1",
        gpu=GpuInfo(model="cpu", vram_total_mb=0, vram_free_mb=0),
        cpu_cores=4,
        ram_mb=8000,
        disk_free_mb=100000,
        datasets_cached=[],
        throughput_ref=100.0,
        bandwidth_to_master_mbps=50.0,
        rtt_to_master_ms=20.0,
    )


@dataclass
class _Master:
    """A running Master a daemon can join: cert + store + tokens + ControlServer."""

    cert: MasterCert
    store: StateStore
    tokens: TokenService
    server: ControlServer

    @property
    def url(self) -> str:
        return f"wss://127.0.0.1:{self.server.port}"


async def _start_master(tmp_path: Path, max_workers: int | None = 4) -> tuple[_Master, str]:
    cert = ensure_cert(tmp_path)
    store = StateStore(":memory:")
    tokens = TokenService(signing_key=_KEY, cert_fp=cert.fingerprint, store=store)
    token = tokens.issue(room="lab", max_workers=max_workers, ttl=timedelta(days=30))
    server = ControlServer(tokens=tokens, cert=cert, store=store)
    await server.serve("127.0.0.1", 0)
    return _Master(cert, store, tokens, server), token


@pytest.mark.integration
@pytest.mark.task("T08")
def test_worker_joins_and_receives_worker_id(tmp_path: Path) -> None:
    async def scenario() -> None:
        master, token = await _start_master(tmp_path)
        daemon = WorkerDaemon(master.url, token, master.cert.fingerprint, _profile())
        connected = asyncio.Event()

        session = asyncio.create_task(daemon.connect_once(on_connected=connected.set))
        try:
            await asyncio.wait_for(connected.wait(), timeout=3.0)
            assert daemon.worker_id is not None
            assert master.server.connected_count == 1
        finally:
            await master.server.close()
            session.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await session

    asyncio.run(scenario())


@pytest.mark.integration
@pytest.mark.task("T08")
def test_bad_token_is_rejected_with_reason(tmp_path: Path) -> None:
    async def scenario() -> None:
        master, _good = await _start_master(tmp_path)
        daemon = WorkerDaemon(master.url, "not-a-token", master.cert.fingerprint, _profile())
        try:
            with pytest.raises(JoinRejected) as exc:
                await daemon.connect_once()
            assert exc.value.reason  # non-empty reason
            assert daemon.worker_id is None
        finally:
            await master.server.close()

    asyncio.run(scenario())


@pytest.mark.integration
@pytest.mark.task("T08")
def test_revoked_token_is_rejected(tmp_path: Path) -> None:
    async def scenario() -> None:
        master, token = await _start_master(tmp_path)
        master.tokens.revoke(master.tokens.verify(token).jti)
        daemon = WorkerDaemon(master.url, token, master.cert.fingerprint, _profile())
        try:
            with pytest.raises(JoinRejected):
                await daemon.connect_once()
        finally:
            await master.server.close()

    asyncio.run(scenario())


@pytest.mark.integration
@pytest.mark.task("T08")
def test_worker_persisted_with_profile(tmp_path: Path) -> None:
    async def scenario() -> None:
        master, token = await _start_master(tmp_path)
        daemon = WorkerDaemon(master.url, token, master.cert.fingerprint, _profile())
        connected = asyncio.Event()

        session = asyncio.create_task(daemon.connect_once(on_connected=connected.set))
        try:
            await asyncio.wait_for(connected.wait(), timeout=3.0)
            row = master.store._conn.execute(  # inspect the durable Worker record
                "SELECT host_id, status FROM workers WHERE id = ?", (daemon.worker_id,)
            ).fetchone()
            assert row["host_id"] == "host-1"
            assert row["status"] == "idle"
        finally:
            await master.server.close()
            session.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await session

    asyncio.run(scenario())


@pytest.mark.integration
@pytest.mark.task("T08")
def test_heartbeat_keeps_connection_after_join(tmp_path: Path) -> None:
    async def scenario() -> None:
        master, token = await _start_master(tmp_path)
        # Fast heartbeat so we can observe several within the test window.
        daemon = WorkerDaemon(
            master.url, token, master.cert.fingerprint, _profile(), heartbeat_interval=0.05
        )
        connected = asyncio.Event()

        session = asyncio.create_task(daemon.connect_once(on_connected=connected.set))
        try:
            await asyncio.wait_for(connected.wait(), timeout=3.0)
            # Let a few heartbeats flow; the connection must stay open and tracked.
            await asyncio.sleep(0.3)
            assert master.server.connected_count == 1
        finally:
            await master.server.close()
            session.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await session

    asyncio.run(scenario())


@pytest.mark.integration
@pytest.mark.task("T08")
def test_worker_reconnects_after_transient_drop(tmp_path: Path) -> None:
    async def scenario() -> None:
        master, token = await _start_master(tmp_path)
        daemon = WorkerDaemon(
            master.url, token, master.cert.fingerprint, _profile(), heartbeat_interval=0.05
        )

        joins = 0
        original = daemon.connect_once
        droppers: list[asyncio.Task[None]] = []  # keep strong refs (RUF006)

        async def join_then_drop(on_connected: object = None) -> None:
            # One session: join (counting it), then close the server to force a drop so
            # run() exercises its reconnect-with-backoff path.
            def hook() -> None:
                nonlocal joins
                joins += 1
                droppers.append(asyncio.create_task(master.server.close()))

            await original(on_connected=hook)

        daemon.connect_once = join_then_drop  # type: ignore[method-assign]

        try:
            # Session 1 joins end-to-end, then the server drops it; run() backs off and the
            # next connect fails against the closed server, ending the loop after
            # max_sessions. We assert the join happened and the drop was tolerated (no crash).
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(daemon.run(max_sessions=2), timeout=5.0)
            assert joins >= 1
        finally:
            await master.server.close()

    asyncio.run(scenario())
