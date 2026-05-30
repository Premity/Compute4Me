"""Artifact store: content-addressed blob storage, Master as origin.

``put(bytes|url) -> hash`` / ``get`` over on-disk content-addressed storage, the HTTP
``GET /artifacts/{hash}`` (Range) + ``POST /artifacts`` endpoints, shard serving for
``index-range``/``file-list``, and name/version alias resolution. See ADR-0012.

Populated across T11 (store + origin) and T12 (shard serving).
"""

from __future__ import annotations
