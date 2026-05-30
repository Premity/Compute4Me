"""Pydantic models for every WebSocket control-channel message.

Defines the Worker→Master and Master→Worker messages from
docs/architecture/wire-protocol.md §2 as a discriminated union on ``type``. Unknown
message types are tolerated for additive forward-compatibility (wire-protocol.md
§Versioning).

Populated in T04.
"""

from __future__ import annotations
