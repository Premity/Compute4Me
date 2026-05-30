"""Python submission API: ``Client`` + ``JobHandle``.

Implements ``Client.from_token``/``from_env``/``__init__``, ``submit_search``/
``submit_map``, the ``JobHandle`` (``wait``/``status``/``progress``/``results``/``fetch``/
``cancel``), and ``list_jobs``/``get_job``/``fleet`` per docs/architecture/wire-protocol.md
§5. Submission requires an admin token (ADR-0014).

Populated in T23.
"""

from __future__ import annotations
