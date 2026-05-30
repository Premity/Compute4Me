"""Master state store: SQLite-backed persistence and restart recovery.

Creates the schema on first ``serve``; provides save/load for rooms, tokens, workers,
jobs, tasks, artifacts, and results, plus ``load_open_jobs()`` / ``load_pending_tasks()``
for restart recovery. See docs/architecture/data-model.md §Master State Store.

Populated in T03.
"""

from __future__ import annotations
