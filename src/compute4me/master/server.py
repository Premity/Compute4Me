"""Master transport: WebSocket control server + HTTP artifact endpoints.

Hosts one persistent WSS connection per Worker (dispatching inbound messages and pushing
``task_assign``/``task_cancel``/``bandwidth_probe``) plus the HTTP artifact channel.
Owns self-signed-cert generation and fingerprint exposure (ADR-0011).

Populated across T06 (TLS), T07 (WS server), T10 (bandwidth probe).
"""

from __future__ import annotations
