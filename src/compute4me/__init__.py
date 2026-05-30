"""Compute4Me — a Docker-native, master-orchestrated distributed deep-learning fabric.

Public API surface. Researchers import the submission client and search-space DSL from
here; the operator CLI is exposed via the ``compute4me`` console script (see ``cli``).

The concrete symbols (``Client``, ``loguniform``, ``uniform``, ``categorical``,
``ShardStrategy``) land with their implementing T-tasks (T23, T13/T14). Until then this
module documents the intended surface without re-exporting unbuilt code.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
