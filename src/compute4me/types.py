"""Core Pydantic models shared across Master, Worker, and client.

The validation-boundary types from docs/architecture/data-model.md: the Capability
Profile advertised on join, the Invite Token claims, the two Job submission specs, and the
internal Task representation the Scheduler and runner pass around. Everything that crosses
a process or host boundary is one of these models, JSON-serialized.

See docs/architecture/data-model.md for the canonical field reference and the SQLite
schema these back.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, model_validator

# Free-form JSON objects: sampled configs, Optuna search-space specs, and reported
# metrics. Their inner shape is user-defined (it's the user's model config / metrics),
# so the values are genuinely Any — Compute4Me forwards them opaquely.
JsonObject = dict[str, Any]

# --- Capability Profile (Worker → Master on join; refreshed ~10 min) ---


class GpuInfo(BaseModel):
    """A Worker's GPU facts, or model='cpu' on a CPU-only host."""

    model: str
    vram_total_mb: int
    vram_free_mb: int


class CapabilityProfile(BaseModel):
    """Per-Worker hardware + locality record the Scheduler keys off. See ADR-0008."""

    host_id: str
    gpu: GpuInfo
    cpu_cores: int
    ram_mb: int
    disk_free_mb: int
    datasets_cached: list[tuple[str, str]]
    throughput_ref: float
    bandwidth_to_master_mbps: float
    rtt_to_master_ms: float


# --- Invite Token claims (signed; see ADR-0011, ADR-0014, ADR-0015) ---


class TokenClaims(BaseModel):
    """The signed claims inside an Invite Token.

    No ``master_url`` field — the Master URL is passed separately (``--master`` /
    ``C4M_MASTER``) so the Master can move without re-issuing tokens (ADR-0015).
    """

    jti: str
    room: str
    max_workers: int | None
    expires_at: str
    master_cert_fp: str
    admin: bool = False


# --- Job submission schemas (Python API + CLI) ---


class SearchJobSpec(BaseModel):
    """A hyperparameter / config sweep: run ``image`` over N sampled configs."""

    image: str
    metric: str
    direction: Literal["minimize", "maximize"] = "maximize"
    n_trials: int
    top_k: int | None = None
    sampler: Literal["optuna", "raw"] = "optuna"
    search_space: JsonObject
    inputs: list[str] = []
    env: dict[str, str] = {}


class ShardStrategy(BaseModel):
    """How a Map Job's dataset is split into shard-Tasks."""

    kind: Literal["whole", "index-range", "file-list"]
    n_shards: int

    @model_validator(mode="after")
    def _check_n_shards(self) -> ShardStrategy:
        # 'whole' is a single shard regardless of n_shards; the split kinds need a real count.
        if self.kind != "whole" and self.n_shards <= 0:
            raise ValueError(f"n_shards must be > 0 for kind={self.kind!r}")
        return self


class MapJobSpec(BaseModel):
    """A sharded batch over a dataset: run ``image`` on each shard. See ADR-0009."""

    image: str
    dataset: str
    shard: ShardStrategy
    inputs: list[str] = []
    env: dict[str, str] = {}


# --- Durable Master records (master/state.py; see data-model.md §Master State Store) ---


class Room(BaseModel):
    """A closed-membership compute pool owned by one Master."""

    id: str
    name: str
    created_at: str


class Worker(BaseModel):
    """A joined Worker (one container = one Worker) and its advertised profile."""

    id: str
    room_id: str
    token_jti: str
    host_id: str
    profile: CapabilityProfile
    status: Literal["joining", "idle", "busy", "down", "quarantined"]
    quarantine_until: str | None = None
    last_heartbeat_at: str | None = None
    joined_at: str


class Job(BaseModel):
    """A submitted Job (Map or Search) and its lifecycle status.

    ``spec`` holds the raw submission (a ``MapJobSpec`` or ``SearchJobSpec`` dump);
    it's stored opaquely as JSON and re-validated by the submitting layer, so the
    durable record keeps it as a free-form object.
    """

    id: str
    room_id: str
    type: Literal["map", "search"]
    spec: JsonObject
    status: Literal["queued", "running", "completed", "cancelled"]
    top_k: int | None = None
    created_at: str
    finished_at: str | None = None


# --- Internal task representation (Master ↔ Worker) ---


class ShardDescriptor(BaseModel):
    """The slice of an Artifact a Map Task is assigned.

    ``index-range`` uses ``[start, end)``; ``file-list`` uses ``files``; ``whole`` uses
    neither. Backs the ``/artifacts/{hash}/shard`` query in wire-protocol.md §3.
    """

    kind: Literal["whole", "index-range", "file-list"]
    start: int | None = None
    end: int | None = None
    files: list[str] | None = None


class ArtifactRef(BaseModel):
    """A reference to an input Artifact, optionally narrowed to one shard."""

    hash: str
    shard: ShardDescriptor | None = None


class TaskRequires(BaseModel):
    """Resource constraints the Scheduler filters and estimates against."""

    min_vram_mb: int
    gpu_required: bool
    est_work_units: float


class Task(BaseModel):
    """The unit of scheduling and assignment, derived from a Job by the Decomposer."""

    id: str
    job_id: str
    args: JsonObject
    input_refs: list[ArtifactRef]
    requires: TaskRequires
    attempts: int = 0


class TaskError(BaseModel):
    """A Task failure, classified for the retry policy.

    ``oom`` drives OOM-promotion (retry on a Worker with >=2x VRAM); ``exit_code`` is the
    user container's exit status when the failure came from the process. See
    docs/architecture/modules.md ``classify_failure``.
    """

    message: str
    oom: bool = False
    exit_code: int | None = None


class TaskResult(BaseModel):
    """A completed Task's outcome reported by the Worker."""

    task_id: str
    status: Literal["succeeded", "failed"]
    metrics: JsonObject | None = None
    output_refs: list[str] | None = None
    error: str | None = None
