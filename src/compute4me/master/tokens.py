"""Invite Token service: issue / verify / revoke / admit / release.

Signs and verifies JWT-style Invite Tokens with a Master-held key, maintains the
in-memory revocation set and per-``jti`` live-Worker counter, and persists token metadata
via the state store. See ADR-0002 and docs/architecture/modules.md §Token service.

Populated in T05.
"""

from __future__ import annotations
