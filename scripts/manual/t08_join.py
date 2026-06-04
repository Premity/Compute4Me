"""Manual T08 check (the first tracer bullet — a Worker joins a Master).

Runs the real WorkerDaemon against the real ControlServer over WSS. From the repo root:
    uv run python scripts/manual/t08_join.py

Expect: the daemon pins the cert, joins, gets a worker_id, the Master persists + tracks it,
a heartbeat flows, and a deliberately-bad token is rejected with a reason.
"""

from __future__ import annotations

import asyncio
import contextlib
import tempfile
from datetime import timedelta

from compute4me.master.server import ControlServer, ensure_cert
from compute4me.master.state import StateStore
from compute4me.master.tokens import TokenService
from compute4me.types import CapabilityProfile, GpuInfo
from compute4me.worker.daemon import JoinRejected, WorkerDaemon

KEY = "manual-signing-key-padded-to-32-bytes!!"


def profile() -> CapabilityProfile:
    return CapabilityProfile(
        host_id="manual-host",
        gpu=GpuInfo(model="cpu", vram_total_mb=0, vram_free_mb=0),
        cpu_cores=4,
        ram_mb=8000,
        disk_free_mb=100000,
        datasets_cached=[],
        throughput_ref=100.0,
        bandwidth_to_master_mbps=50.0,
        rtt_to_master_ms=20.0,
    )


async def main() -> None:
    cert = ensure_cert(tempfile.mkdtemp(prefix="c4m-t08-"))
    store = StateStore(":memory:")
    tokens = TokenService(signing_key=KEY, cert_fp=cert.fingerprint, store=store)
    token = tokens.issue(room="lab", max_workers=2, ttl=timedelta(days=1))

    server = ControlServer(tokens=tokens, cert=cert, store=store)
    await server.serve("127.0.0.1", 0)
    url = f"wss://127.0.0.1:{server.port}"
    print(f"[master] listening on {url}  (cert fp {cert.fingerprint[:12]}…)")

    # --- good token: join, heartbeat, observe persistence ---
    daemon = WorkerDaemon(url, token, cert.fingerprint, profile(), heartbeat_interval=0.1)
    joined = asyncio.Event()
    session = asyncio.create_task(daemon.connect_once(on_connected=joined.set))
    await asyncio.wait_for(joined.wait(), timeout=3.0)
    print(f"[worker] joined → worker_id={daemon.worker_id}")
    print(f"[master] connected_count={server.connected_count}")
    row = store._conn.execute(
        "SELECT host_id, status FROM workers WHERE id = ?", (daemon.worker_id,)
    ).fetchone()
    print(f"[master] persisted worker: host_id={row['host_id']} status={row['status']}")
    await asyncio.sleep(0.3)  # let a few heartbeats flow
    print(f"[master] still connected after heartbeats: {server.connected_count == 1}")

    # --- bad token: rejected with reason ---
    bad = WorkerDaemon(url, "not-a-real-token", cert.fingerprint, profile())
    try:
        await bad.connect_once()
        print("[worker] BUG: bad token was NOT rejected")
    except JoinRejected as exc:
        print(f"[worker] bad token rejected → reason: {exc.reason!r}")

    session.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await session
    await server.close()
    print("[done]")


if __name__ == "__main__":
    asyncio.run(main())
