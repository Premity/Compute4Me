"""Master state store: SQLite-backed persistence and restart recovery.

Creates the schema on first ``serve``; provides save/load for rooms, tokens, workers,
jobs, tasks, artifacts, and results, plus ``load_open_jobs()`` / ``load_pending_tasks()``
for restart recovery. See docs/architecture/data-model.md §Master State Store.

All durable Master state lives in one SQLite file. Structured sub-records (the Worker's
``CapabilityProfile``, a Job's spec, a Task's input refs) are stored as Pydantic JSON in
TEXT columns and re-validated on read. Writes are upserts keyed by primary key, so save
is idempotent and safe to replay during recovery.
"""

from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING

from compute4me.types import (
    ArtifactRef,
    Job,
    Task,
    TaskRequires,
    TaskResult,
    Worker,
)

if TYPE_CHECKING:
    from pathlib import Path

# The schema is the canonical SQL from data-model.md §Master State Store. Applied once
# on an empty DB; ``CREATE TABLE IF NOT EXISTS`` makes open-existing-DB a no-op.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS rooms (
  id          TEXT PRIMARY KEY,
  name        TEXT UNIQUE NOT NULL,
  created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tokens (
  jti          TEXT PRIMARY KEY,
  room_id      TEXT NOT NULL REFERENCES rooms(id),
  max_workers  INTEGER,
  expires_at   TEXT NOT NULL,
  revoked      INTEGER NOT NULL DEFAULT 0,
  created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workers (
  id              TEXT PRIMARY KEY,
  room_id         TEXT NOT NULL REFERENCES rooms(id),
  token_jti       TEXT NOT NULL REFERENCES tokens(jti),
  host_id         TEXT NOT NULL,
  profile_json    TEXT NOT NULL,
  status          TEXT NOT NULL,
  quarantine_until TEXT,
  last_heartbeat_at TEXT,
  joined_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
  id          TEXT PRIMARY KEY,
  room_id     TEXT NOT NULL REFERENCES rooms(id),
  type        TEXT NOT NULL,
  spec_json   TEXT NOT NULL,
  status      TEXT NOT NULL,
  top_k       INTEGER,
  created_at  TEXT NOT NULL,
  finished_at TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
  id            TEXT PRIMARY KEY,
  job_id        TEXT NOT NULL REFERENCES jobs(id),
  args_json     TEXT NOT NULL,
  input_refs    TEXT NOT NULL,
  requires_json TEXT NOT NULL,
  status        TEXT NOT NULL,
  assigned_worker_id TEXT REFERENCES workers(id),
  attempts      INTEGER NOT NULL DEFAULT 0,
  last_error    TEXT,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS artifacts (
  hash        TEXT PRIMARY KEY,
  name        TEXT,
  version     TEXT,
  kind        TEXT NOT NULL,
  size_bytes  INTEGER NOT NULL,
  origin      TEXT NOT NULL,
  created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS results (
  task_id      TEXT PRIMARY KEY REFERENCES tasks(id),
  metrics_json TEXT,
  output_refs  TEXT,
  finished_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS tasks_job_status_idx ON tasks (job_id, status);
CREATE INDEX IF NOT EXISTS workers_room_status_idx ON workers (room_id, status);
CREATE INDEX IF NOT EXISTS artifacts_name_version_idx ON artifacts (name, version);
"""

# Job statuses that mean "still needs scheduling work" — what load_open_jobs resumes.
_OPEN_JOB_STATUSES = ("queued", "running")

# Task statuses not yet terminal — what load_pending_tasks refills the queue with.
# 'assigned'/'running' Tasks are re-queued on restart because their Worker's liveness
# is re-established by heartbeat, not assumed from the durable record.
_PENDING_TASK_STATUSES = ("pending", "assigned", "running")


class StateStore:
    """A SQLite-backed durable store for all Master control-plane state.

    Open against a file path for a real deployment, or ``":memory:"`` in tests.
    The schema is created on construction, so a fresh DB is immediately usable and
    reopening an existing one is a no-op.
    """

    def __init__(self, db_path: str | Path = "master.db") -> None:
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        # Enforce the REFERENCES constraints in the schema (off by default in SQLite).
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> StateStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- Rooms -------------------------------------------------------------

    def save_room(self, id: str, name: str, created_at: str) -> None:
        self._conn.execute(
            "INSERT INTO rooms (id, name, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, created_at=excluded.created_at",
            (id, name, created_at),
        )
        self._conn.commit()

    # --- Tokens ------------------------------------------------------------

    def save_token(
        self,
        *,
        jti: str,
        room_id: str,
        max_workers: int | None,
        expires_at: str,
        created_at: str,
        revoked: bool = False,
    ) -> None:
        """Persist Invite Token metadata (not the secret — see data-model.md)."""
        self._conn.execute(
            "INSERT INTO tokens (jti, room_id, max_workers, expires_at, revoked, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(jti) DO UPDATE SET "
            "  room_id=excluded.room_id, max_workers=excluded.max_workers, "
            "  expires_at=excluded.expires_at, revoked=excluded.revoked, "
            "  created_at=excluded.created_at",
            (jti, room_id, max_workers, expires_at, int(revoked), created_at),
        )
        self._conn.commit()

    def set_token_revoked(self, jti: str) -> None:
        """Mark a token's jti revoked (idempotent; no-op if the jti is unknown)."""
        self._conn.execute("UPDATE tokens SET revoked = 1 WHERE jti = ?", (jti,))
        self._conn.commit()

    def load_revoked_jtis(self) -> set[str]:
        """All revoked jtis; used on restart to rebuild the in-memory revocation set."""
        rows = self._conn.execute("SELECT jti FROM tokens WHERE revoked = 1").fetchall()
        return {row["jti"] for row in rows}

    # --- Workers -----------------------------------------------------------

    def save_worker(self, worker: Worker) -> None:
        self._conn.execute(
            "INSERT INTO workers "
            "(id, room_id, token_jti, host_id, profile_json, status, "
            " quarantine_until, last_heartbeat_at, joined_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "  room_id=excluded.room_id, token_jti=excluded.token_jti, "
            "  host_id=excluded.host_id, profile_json=excluded.profile_json, "
            "  status=excluded.status, quarantine_until=excluded.quarantine_until, "
            "  last_heartbeat_at=excluded.last_heartbeat_at, joined_at=excluded.joined_at",
            (
                worker.id,
                worker.room_id,
                worker.token_jti,
                worker.host_id,
                worker.profile.model_dump_json(),
                worker.status,
                worker.quarantine_until,
                worker.last_heartbeat_at,
                worker.joined_at,
            ),
        )
        self._conn.commit()

    # --- Jobs --------------------------------------------------------------

    def save_job(self, job: Job) -> None:
        self._conn.execute(
            "INSERT INTO jobs "
            "(id, room_id, type, spec_json, status, top_k, created_at, finished_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "  room_id=excluded.room_id, type=excluded.type, spec_json=excluded.spec_json, "
            "  status=excluded.status, top_k=excluded.top_k, created_at=excluded.created_at, "
            "  finished_at=excluded.finished_at",
            (
                job.id,
                job.room_id,
                job.type,
                _dump_json(job.spec),
                job.status,
                job.top_k,
                job.created_at,
                job.finished_at,
            ),
        )
        self._conn.commit()

    def load_open_jobs(self) -> list[Job]:
        """Jobs still in flight (``queued``/``running``); used on restart to resume."""
        placeholders = ", ".join("?" for _ in _OPEN_JOB_STATUSES)
        rows = self._conn.execute(
            f"SELECT * FROM jobs WHERE status IN ({placeholders}) ORDER BY created_at",
            _OPEN_JOB_STATUSES,
        ).fetchall()
        return [_row_to_job(row) for row in rows]

    # --- Tasks -------------------------------------------------------------

    def save_task(
        self,
        task: Task,
        *,
        status: str = "pending",
        assigned_worker_id: str | None = None,
        last_error: str | None = None,
        created_at: str,
        updated_at: str,
    ) -> None:
        """Persist a Task plus its scheduling state.

        The wire ``Task`` model carries identity, args, inputs, and requirements; the
        durable row adds the scheduling-state columns (status, assignment, error,
        timestamps) the Scheduler owns. They're passed alongside the model rather than
        baked into it so the wire form stays minimal (see data-model.md).
        """
        self._conn.execute(
            "INSERT INTO tasks "
            "(id, job_id, args_json, input_refs, requires_json, status, "
            " assigned_worker_id, attempts, last_error, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "  job_id=excluded.job_id, args_json=excluded.args_json, "
            "  input_refs=excluded.input_refs, requires_json=excluded.requires_json, "
            "  status=excluded.status, assigned_worker_id=excluded.assigned_worker_id, "
            "  attempts=excluded.attempts, last_error=excluded.last_error, "
            "  updated_at=excluded.updated_at",
            (
                task.id,
                task.job_id,
                _dump_json(task.args),
                _dump_refs(task.input_refs),
                task.requires.model_dump_json(),
                status,
                assigned_worker_id,
                task.attempts,
                last_error,
                created_at,
                updated_at,
            ),
        )
        self._conn.commit()

    def load_pending_tasks(self, job_id: str) -> list[Task]:
        """Non-terminal Tasks for a Job; used on restart to refill the queue."""
        placeholders = ", ".join("?" for _ in _PENDING_TASK_STATUSES)
        rows = self._conn.execute(
            f"SELECT * FROM tasks WHERE job_id = ? AND status IN ({placeholders}) "
            "ORDER BY created_at",
            (job_id, *_PENDING_TASK_STATUSES),
        ).fetchall()
        return [_row_to_task(row) for row in rows]

    # --- Results -----------------------------------------------------------

    def save_result(self, result: TaskResult, *, finished_at: str) -> None:
        self._conn.execute(
            "INSERT INTO results (task_id, metrics_json, output_refs, finished_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(task_id) DO UPDATE SET "
            "  metrics_json=excluded.metrics_json, output_refs=excluded.output_refs, "
            "  finished_at=excluded.finished_at",
            (
                result.task_id,
                _dump_json(result.metrics) if result.metrics is not None else None,
                _dump_json(result.output_refs) if result.output_refs is not None else None,
                finished_at,
            ),
        )
        self._conn.commit()


# --- JSON helpers ----------------------------------------------------------
#
# Pydantic owns model (de)serialization; for the free-form JSON columns (a Job's spec,
# a Task's args, a result's metrics) we use stdlib json so there's no implicit schema.


def _dump_json(value: object) -> str:
    return json.dumps(value)


def _dump_refs(refs: list[ArtifactRef]) -> str:
    return json.dumps([ref.model_dump() for ref in refs])


def _row_to_job(row: sqlite3.Row) -> Job:
    return Job(
        id=row["id"],
        room_id=row["room_id"],
        type=row["type"],
        spec=json.loads(row["spec_json"]),
        status=row["status"],
        top_k=row["top_k"],
        created_at=row["created_at"],
        finished_at=row["finished_at"],
    )


def _row_to_task(row: sqlite3.Row) -> Task:
    return Task(
        id=row["id"],
        job_id=row["job_id"],
        args=json.loads(row["args_json"]),
        input_refs=[ArtifactRef.model_validate(r) for r in json.loads(row["input_refs"])],
        requires=TaskRequires.model_validate_json(row["requires_json"]),
        attempts=row["attempts"],
    )
