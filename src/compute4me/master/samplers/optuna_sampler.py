"""Optuna-backed ``Sampler`` (TPE/Bayesian) wrapped behind the ``Sampler`` protocol.

Adapts Optuna's ask/tell study interface to the project's ``Sampler`` protocol so the
search-space DSL stays Compute4Me-namespaced. See ADR-0010.

Populated in T13.
"""

from __future__ import annotations
