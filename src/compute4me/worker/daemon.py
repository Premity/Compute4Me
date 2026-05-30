"""Worker daemon: outbound WS client, join handshake, heartbeat, task loop.

Builds the Capability Profile on start, sends ``join`` and handles ``join_ack``/
``join_reject``, heartbeats every 10s, reconnects with backoff, and dispatches assigned
Tasks to the container runner. Pins the Master's cert fingerprint from its token
(ADR-0011).

Populated across T06 (cert pinning), T08 (join + heartbeat), T17 (task dispatch).
"""

from __future__ import annotations
