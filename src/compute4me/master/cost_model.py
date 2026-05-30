"""Coarse DL-aware cost model for per-(Task, Worker) runtime estimation.

Pure functions: ``estimate(task, worker) = work_units / rate(worker)`` and
``feasible(task, worker)`` (VRAM / GPU filter). Deliberately coarse in v0.1 — enough to
beat round-robin; calibration is deferred to v0.2. See ADR-0008.

Populated in T15.
"""

from __future__ import annotations
