"""Failure controller: heartbeat tracking, retries, OOM-promotion, quarantine.

``tick()`` detects 30s heartbeat timeouts and re-queues in-flight Tasks; applies the
retry policy (≤3 attempts), promotes OOM retries to higher-VRAM Workers, quarantines
flaky Workers, and validates results (finite metric / output schema).

Populated across T18 (heartbeat + retries) and T19 (quarantine + validation).
"""

from __future__ import annotations
