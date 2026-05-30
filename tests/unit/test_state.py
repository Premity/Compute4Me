"""T03 acceptance: schema applies on empty DB, Job+Tasks survive restart, indices present.

A "process restart" is simulated by closing the StateStore and reopening a fresh one
against the same on-disk file (``tmp_path``) — the durable bytes are all that carry over.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from compute4me.master.state import StateStore
from compute4me.types import (
    ArtifactRef,
    CapabilityProfile,
    GpuInfo,
    Job,
    ShardDescriptor,
    Task,
    TaskRequires,
    TaskResult,
    Worker,
)


def _profile() -> CapabilityProfile:
    return CapabilityProfile(
        host_id="h1",
        gpu=GpuInfo(model="NVIDIA GeForce RTX 3070", vram_total_mb=8192, vram_free_mb=8000),
        cpu_cores=8,
        ram_mb=32000,
        disk_free_mb=500000,
        datasets_cached=[("kepler-q1-q17", "abc123")],
        throughput_ref=412.5,
        bandwidth_to_master_mbps=94.0,
        rtt_to_master_ms=12.0,
    )


def _seed_room(store: StateStore) -> None:
    store.save_room(id="r1", name="lab", created_at="2026-05-30T00:00:00Z")


@pytest.mark.unit
@pytest.mark.task("T03")
def test_schema_applies_on_empty_db(tmp_path: Path) -> None:
    db = tmp_path / "master.db"

    StateStore(db).close()

    conn = sqlite3.connect(db)
    try:
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        conn.close()
    assert {"rooms", "tokens", "workers", "jobs", "tasks", "artifacts", "results"} <= tables


@pytest.mark.unit
@pytest.mark.task("T03")
def test_declared_indices_present(tmp_path: Path) -> None:
    db = tmp_path / "master.db"

    StateStore(db).close()

    conn = sqlite3.connect(db)
    try:
        indices = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        }
    finally:
        conn.close()
    assert {
        "tasks_job_status_idx",
        "workers_room_status_idx",
        "artifacts_name_version_idx",
    } <= indices


@pytest.mark.unit
@pytest.mark.task("T03")
def test_reopening_existing_db_is_a_noop(tmp_path: Path) -> None:
    db = tmp_path / "master.db"
    with StateStore(db) as store:
        _seed_room(store)

    # Reopening must not wipe or error on the already-applied schema.
    with StateStore(db) as store:
        store.save_room(id="r2", name="lab2", created_at="2026-05-30T00:00:00Z")

    conn = sqlite3.connect(db)
    try:
        count = conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0]
    finally:
        conn.close()
    assert count == 2


@pytest.mark.unit
@pytest.mark.task("T03")
def test_job_and_tasks_survive_restart(tmp_path: Path) -> None:
    db = tmp_path / "master.db"
    job = Job(
        id="j1",
        room_id="r1",
        type="search",
        spec={"image": "img:latest", "metric": "val_auc", "n_trials": 8},
        status="running",
        top_k=3,
        created_at="2026-05-30T01:00:00Z",
    )
    task = Task(
        id="t1",
        job_id="j1",
        args={"lr": 0.01},
        input_refs=[
            ArtifactRef(hash="h1", shard=ShardDescriptor(kind="index-range", start=0, end=100))
        ],
        requires=TaskRequires(min_vram_mb=4096, gpu_required=True, est_work_units=1000.0),
        attempts=1,
    )

    with StateStore(db) as store:
        _seed_room(store)
        store.save_job(job)
        store.save_task(
            task,
            status="assigned",
            created_at="2026-05-30T01:00:01Z",
            updated_at="2026-05-30T01:00:02Z",
        )

    # Fresh process: only the file carried over.
    with StateStore(db) as reopened:
        open_jobs = reopened.load_open_jobs()
        pending = reopened.load_pending_tasks("j1")

    assert open_jobs == [job]
    assert pending == [task]


@pytest.mark.unit
@pytest.mark.task("T03")
def test_load_open_jobs_excludes_terminal(tmp_path: Path) -> None:
    db = tmp_path / "master.db"
    base = dict(room_id="r1", type="map", spec={}, created_at="2026-05-30T00:00:00Z")
    with StateStore(db) as store:
        _seed_room(store)
        store.save_job(Job(id="open", status="queued", **base))
        store.save_job(Job(id="done", status="completed", **base))
        store.save_job(Job(id="killed", status="cancelled", **base))

        open_ids = {j.id for j in store.load_open_jobs()}
    assert open_ids == {"open"}


@pytest.mark.unit
@pytest.mark.task("T03")
def test_load_pending_tasks_excludes_terminal_and_other_jobs(tmp_path: Path) -> None:
    db = tmp_path / "master.db"
    requires = TaskRequires(min_vram_mb=1024, gpu_required=False, est_work_units=1.0)

    def _task(tid: str, jid: str) -> Task:
        return Task(id=tid, job_id=jid, args={}, input_refs=[], requires=requires)

    with StateStore(db) as store:
        _seed_room(store)
        store.save_job(
            Job(
                id="j1",
                room_id="r1",
                type="map",
                spec={},
                status="running",
                created_at="2026-05-30T00:00:00Z",
            )
        )
        store.save_job(
            Job(
                id="j2",
                room_id="r1",
                type="map",
                spec={},
                status="running",
                created_at="2026-05-30T00:00:00Z",
            )
        )
        ts = "2026-05-30T00:00:00Z"
        store.save_task(_task("pend", "j1"), status="pending", created_at=ts, updated_at=ts)
        store.save_task(_task("run", "j1"), status="running", created_at=ts, updated_at=ts)
        store.save_task(_task("ok", "j1"), status="succeeded", created_at=ts, updated_at=ts)
        store.save_task(_task("other", "j2"), status="pending", created_at=ts, updated_at=ts)

        pending_ids = {t.id for t in store.load_pending_tasks("j1")}
    assert pending_ids == {"pend", "run"}


@pytest.mark.unit
@pytest.mark.task("T03")
def test_save_is_idempotent_upsert(tmp_path: Path) -> None:
    db = tmp_path / "master.db"
    job = Job(
        id="j1",
        room_id="r1",
        type="map",
        spec={"v": 1},
        status="queued",
        created_at="2026-05-30T00:00:00Z",
    )
    with StateStore(db) as store:
        _seed_room(store)
        store.save_job(job)
        # Re-save with a changed status: should update, not duplicate or error.
        store.save_job(job.model_copy(update={"status": "running"}))

        jobs = store.load_open_jobs()
    assert len(jobs) == 1
    assert jobs[0].status == "running"


@pytest.mark.unit
@pytest.mark.task("T03")
def test_worker_round_trips_through_db(tmp_path: Path) -> None:
    db = tmp_path / "master.db"
    worker = Worker(
        id="w1",
        room_id="r1",
        token_jti="jti1",
        host_id="h1",
        profile=_profile(),
        status="idle",
        joined_at="2026-05-30T00:00:00Z",
    )
    with StateStore(db) as store:
        _seed_room(store)
        # workers.token_jti REFERENCES tokens(jti); insert the referenced token directly.
        store._conn.execute(
            "INSERT INTO tokens (jti, room_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
            ("jti1", "r1", "2026-07-01T00:00:00Z", "2026-05-30T00:00:00Z"),
        )
        store.save_worker(worker)

        row = store._conn.execute(
            "SELECT profile_json, status FROM workers WHERE id = ?", ("w1",)
        ).fetchone()
    restored = CapabilityProfile.model_validate_json(row["profile_json"])
    assert restored == worker.profile
    assert row["status"] == "idle"


@pytest.mark.unit
@pytest.mark.task("T03")
def test_result_persists(tmp_path: Path) -> None:
    db = tmp_path / "master.db"
    requires = TaskRequires(min_vram_mb=1024, gpu_required=False, est_work_units=1.0)
    with StateStore(db) as store:
        _seed_room(store)
        store.save_job(
            Job(
                id="j1",
                room_id="r1",
                type="search",
                spec={},
                status="running",
                created_at="2026-05-30T00:00:00Z",
            )
        )
        ts = "2026-05-30T00:00:00Z"
        store.save_task(
            Task(id="t1", job_id="j1", args={}, input_refs=[], requires=requires),
            status="succeeded",
            created_at=ts,
            updated_at=ts,
        )
        store.save_result(
            TaskResult(task_id="t1", status="succeeded", metrics={"val_auc": 0.91}),
            finished_at="2026-05-30T00:05:00Z",
        )

        row = store._conn.execute(
            "SELECT metrics_json, finished_at FROM results WHERE task_id = ?", ("t1",)
        ).fetchone()
    assert row["finished_at"] == "2026-05-30T00:05:00Z"
    assert '"val_auc"' in row["metrics_json"]
