"""The ``Sampler`` protocol: ``ask()`` for the next config, ``tell()`` to report a result.

Defines the pluggable interface every sampler backend implements, keeping the Job
decomposer and submission API independent of any specific HPO library. See ADR-0010.

Populated in T13.
"""

from __future__ import annotations
