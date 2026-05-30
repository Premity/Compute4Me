"""Container runner: launch the user image per the Container Contract.

``run()`` does ``docker run`` of the user image with the ``C4M_*`` env vars (plus any
Job-spec ``env={...}`` forwarded in, stripping ``C4M_*`` overrides with a warning), mounts
inputs/outputs, tails ``progress.jsonl``, reads ``metrics.json``, uploads outputs, and
returns a ``task_result``. See ADR-0006 and docs/architecture/wire-protocol.md §1.

Populated in T17.
"""

from __future__ import annotations
