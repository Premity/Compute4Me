"""Job decomposer: expand a Job into schedulable Tasks.

``decompose(SearchJobSpec)`` emits N config-Tasks via a Sampler; ``decompose(MapJobSpec)``
emits shard-Tasks per the ShardStrategy. Each Task carries its ``requires`` (min VRAM,
estimated work units).

Populated in T14.
"""

from __future__ import annotations
