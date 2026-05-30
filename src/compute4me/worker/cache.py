"""Worker-side content-addressed artifact cache.

``ensure_cached(hash, shard)`` fetches the needed bytes over HTTP, verifies the sha256,
and skips the fetch when a valid copy is already present. The cache contents back the
``datasets_cached`` field of the Capability Profile for locality scheduling.

Populated in T12.
"""

from __future__ import annotations
