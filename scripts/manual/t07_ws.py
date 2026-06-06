"""Manual T07 check: stand up a real ControlServer and connect a client by hand.

From the repo root:  uv run python scripts/manual/t07_ws.py

Expect: the Master reports the Worker connected after `join`, a pushed BandwidthProbe
arrives at the client, and the slot is released after the socket closes.
"""

from __future__ import annotations

import asyncio
import ssl
import tempfile
from datetime import timedelta

from websockets.asyncio.client import connect

from compute4me.master.server import ControlServer, ensure_cert
from compute4me.master.state import StateStore
from compute4me.master.tokens import TokenService
from compute4me.proto.messages import BandwidthProbe, Heartbeat, Join
from compute4me.types import CapabilityProfile, GpuInfo

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


def client_ssl() -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


async def main() -> None:
    cert = ensure_cert(tempfile.mkdtemp(prefix="c4m-t07-"))
    store = StateStore(":memory:")
    tokens = TokenService(signing_key=KEY, cert_fp=cert.fingerprint, store=store)
    token = tokens.issue(room="lab", max_workers=1, ttl=timedelta(days=1))
    jti = tokens.verify(token).jti

    server = ControlServer(tokens=tokens, cert=cert, store=store)
    await server.serve("127.0.0.1", 0)
    print(f"[master] listening on wss://127.0.0.1:{server.port}")
    print(f"[master] cert fp {cert.fingerprint[:12]}…")

    async with connect(f"wss://127.0.0.1:{server.port}", ssl=client_ssl()) as ws:
        await ws.send(Join(token=token, profile=profile()).model_dump_json())
        await ws.recv()  # drain join_ack
        await ws.send(Heartbeat(worker_id="w1").model_dump_json())
        await asyncio.sleep(0.2)
        print(
            f"[master] connected_count={server.connected_count} "
            f"is_connected(jti)={server.is_connected(jti)}"
        )

        conn_id = next(iter(server._conns))
        server.push(conn_id, BandwidthProbe())
        pushed = await asyncio.wait_for(ws.recv(), timeout=2.0)
        print(f"[worker] received push: {pushed}")

    await asyncio.sleep(0.2)
    print(f"[master] after close: connected_count={server.connected_count}")
    print(f"[master] slot freed (admit succeeds again)? {tokens.admit(tokens.verify(token))}")
    await server.close()
    print("[done]")


if __name__ == "__main__":
    asyncio.run(main())
