"""Core Pydantic models shared across Master, Worker, and client.

Defines the validation-boundary types from docs/architecture/data-model.md:
``CapabilityProfile``/``GpuInfo``, ``SearchJobSpec``/``MapJobSpec``/``ShardStrategy``,
``TokenClaims``, and the internal ``Task``/``TaskResult``/``TaskError``/``ShardDescriptor``.

Populated in T02.
"""

from __future__ import annotations
