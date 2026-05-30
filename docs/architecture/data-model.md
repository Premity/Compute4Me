# Data Model

Two layers: the **Master State Store** (durable SQLite) and the **wire/in-memory schemas** (Pydantic). All cross-process data is JSON-serialized via Pydantic; the SQLite columns hold Pydantic JSON for structured fields.

## Master State Store (SQLite)

Single SQLite file (`master.db` in the Master's data volume). All durable Master state lives here; recovered on restart. JSON columns hold structured sub-records validated by Pydantic on read/write.

```sql
-- Rooms: a closed-membership compute pool owned by one Master
CREATE TABLE rooms (
  id          TEXT PRIMARY KEY,            -- uuid
  name        TEXT UNIQUE NOT NULL,
  created_at  TEXT NOT NULL                -- ISO-8601
);

-- Invite Tokens: complete bootstrap credentials (signed; we store metadata, not the secret)
CREATE TABLE tokens (
  jti          TEXT PRIMARY KEY,           -- JWT id; what we revoke by
  room_id      TEXT NOT NULL REFERENCES rooms(id),
  max_workers  INTEGER,                    -- NULL = unlimited
  expires_at   TEXT NOT NULL,
  revoked      INTEGER NOT NULL DEFAULT 0, -- 0/1
  created_at   TEXT NOT NULL
);

-- Workers: one container = one Worker
CREATE TABLE workers (
  id              TEXT PRIMARY KEY,        -- uuid, assigned at join
  room_id         TEXT NOT NULL REFERENCES rooms(id),
  token_jti       TEXT NOT NULL REFERENCES tokens(jti),
  host_id         TEXT NOT NULL,           -- stable per host volume
  profile_json    TEXT NOT NULL,           -- CapabilityProfile (see below)
  status          TEXT NOT NULL,           -- joining|idle|busy|down|quarantined
  quarantine_until TEXT,                   -- ISO-8601 or NULL
  last_heartbeat_at TEXT,
  joined_at       TEXT NOT NULL
);

-- Jobs: one of two primitives, submitted to a Room
CREATE TABLE jobs (
  id          TEXT PRIMARY KEY,
  room_id     TEXT NOT NULL REFERENCES rooms(id),
  type        TEXT NOT NULL,               -- 'map' | 'search'
  spec_json   TEXT NOT NULL,               -- full submission (image, space/dataset, metric, top_k, sampler...)
  status      TEXT NOT NULL,               -- queued|running|completed|cancelled
  top_k       INTEGER,                     -- search only; NULL = keep all
  created_at  TEXT NOT NULL,
  finished_at TEXT
);

-- Tasks: the unit of scheduling/assignment
CREATE TABLE tasks (
  id            TEXT PRIMARY KEY,
  job_id        TEXT NOT NULL REFERENCES jobs(id),
  args_json     TEXT NOT NULL,             -- config passed to the container
  input_refs    TEXT NOT NULL,             -- JSON list of artifact hashes (+ shard descriptor)
  requires_json TEXT NOT NULL,             -- {min_vram_mb, gpu_required, est_work_units}
  status        TEXT NOT NULL,             -- pending|assigned|running|succeeded|failed
  assigned_worker_id TEXT REFERENCES workers(id),
  attempts      INTEGER NOT NULL DEFAULT 0,
  last_error    TEXT,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);

-- Artifacts: content-addressed blobs (datasets, checkpoints, outputs)
CREATE TABLE artifacts (
  hash        TEXT PRIMARY KEY,            -- sha256 hex; canonical id
  name        TEXT,                        -- friendly alias, e.g. 'kepler-q1-q17'
  version     TEXT,                        -- e.g. 'v3'
  kind        TEXT NOT NULL,               -- dataset|checkpoint|output
  size_bytes  INTEGER NOT NULL,
  origin      TEXT NOT NULL,               -- 'upload' | 'url' | 'task-output'
  created_at  TEXT NOT NULL
);

-- Results: per-Task outputs (Search metrics, Map output refs)
CREATE TABLE results (
  task_id      TEXT PRIMARY KEY REFERENCES tasks(id),
  metrics_json TEXT,                       -- {metric_name: finite_float, ...}
  output_refs  TEXT,                       -- JSON list of artifact hashes
  finished_at  TEXT NOT NULL
);

CREATE INDEX tasks_job_status_idx ON tasks (job_id, status);
CREATE INDEX workers_room_status_idx ON workers (room_id, status);
CREATE INDEX artifacts_name_version_idx ON artifacts (name, version);
```

### Why SQLite

- The Master is a single-process control plane at the target scale (≤50 Workers per Room).
- ACID + file-as-database makes restart-recovery trivial: open the file, query, resume.
- Zero ops cost — no external service to manage.
- When the scale exceeds SQLite's comfort zone (50+ concurrent writers, multi-process Master, replication), the schema is portable to Postgres without semantic change.

## Capability Profile

Pydantic, advertised by Workers on `join` and refreshed periodically (~10 min):

```python
class GpuInfo(BaseModel):
    model: str                    # 'NVIDIA GeForce RTX 3070' or 'cpu'
    vram_total_mb: int            # 0 if cpu
    vram_free_mb: int

class CapabilityProfile(BaseModel):
    host_id: str                  # UUID, persisted in container volume, stable across restarts
    gpu: GpuInfo                  # from nvidia-smi, or model='cpu'
    cpu_cores: int                # psutil
    ram_mb: int
    disk_free_mb: int             # shutil.disk_usage of the data volume
    datasets_cached: list[tuple[str, str]]   # (dataset_id, version_hash) for data-locality
    throughput_ref: float         # samples/sec on fixed 30s ResNet18 micro-benchmark
                                  #   (the scheduling key — see ADR-0008)
    bandwidth_to_master_mbps: float   # Master-initiated probe
    rtt_to_master_ms: float
```

`throughput_ref` is the single scalar the Scheduler keys off in current implementations. Future versions may add per-architecture profiles (e.g., separate ResNet, BERT, ViT benchmarks) for sharper cost-model estimates — see [ROADMAP v0.2](../roadmap.md#v02--scheduler-maturity--concurrency).

## Job submission schemas

Pydantic, used by the Python submission API and CLI:

```python
class SearchJobSpec(BaseModel):
    image: str                    # user model container, e.g. 'ghcr.io/hamda/spacesight-train:latest'
    metric: str                   # name of the scalar to optimize, read from metrics.json
    direction: Literal["minimize", "maximize"] = "maximize"
    n_trials: int
    top_k: Optional[int] = None
    sampler: Literal["optuna", "raw"] = "optuna"
    search_space: dict            # Optuna distribution spec, OR (sampler='raw') a list[dict] of configs
    inputs: list[str] = []        # artifact names/hashes mounted into every trial
    env: dict[str, str] = {}      # extra env vars forwarded to every trial container
                                  #   (W&B/MLflow/HF keys etc.); C4M_* names are reserved

class ShardStrategy(BaseModel):
    kind: Literal["whole", "index-range", "file-list"]
    n_shards: int                 # ignored for 'whole'

class MapJobSpec(BaseModel):
    image: str
    dataset: str                  # artifact name/hash to shard over
    shard: ShardStrategy
    inputs: list[str] = []        # additional artifacts mounted into every shard
    env: dict[str, str] = {}      # extra env vars forwarded to every shard container (same rules)
```

The `env` field is the integration point for external observability / model-registry tooling (W&B, MLflow, Comet, TensorBoard, HuggingFace). Compute4Me forwards the strings opaquely; the user container talks to the upstream service directly over outbound HTTPS. See [wire-protocol.md §1 Job-supplied environment variables](./wire-protocol.md#job-supplied-environment-variables-env) for the contract and the trust-model note.

A third primitive — `PipelineJobSpec` — arrives in v0.6 for big-model inference. See [ROADMAP v0.6](../roadmap.md#v06--big-model-inference) and [ADR-0009](../adr/0009-map-search-primitives.md).

## Invite Token claims (signed)

```python
class TokenClaims(BaseModel):
    jti: str                      # unique token id (revocation key)
    room: str
    max_workers: Optional[int]    # nullable = unlimited
    expires_at: str               # ISO-8601; default issuance ttl = 30 days
    master_cert_fp: str           # sha256 fingerprint of Master's self-signed cert
                                  #   (pinned by Worker — see ADR-0011)
    admin: bool = False           # admin capability: may submit/cancel/list Jobs via the
                                  #   Python API (default False = Worker-only — see ADR-0014)
    # NB: no `master_url` field. URL is passed separately via `--master` / C4M_MASTER
    #     so the Master can be moved without re-issuing tokens — see ADR-0015.
    # + HMAC/RS signature over the above
```

The Token authenticates the holder and identifies the Room + cert; the Master URL is passed alongside it (`--master URL` flag or `C4M_MASTER` env var) so deployment topology stays decoupled from credentials. See [ADR-0011](../adr/0011-tls-fingerprint-in-token.md) for cert pinning and [ADR-0015](../adr/0015-master-url-separate-from-token.md) for the URL-separate decision.

The `admin` bit reuses the token machinery for Job submission instead of inventing a parallel auth scheme. See [ADR-0014](../adr/0014-admin-tokens-for-submission.md) (amends [ADR-0002](../adr/0002-closed-membership-rooms.md)).

## Internal task representation

```python
class Task(BaseModel):
    id: str
    job_id: str
    args: dict                    # passed via C4M_CONFIG
    input_refs: list[ArtifactRef] # ArtifactRef = (hash, optional ShardDescriptor)
    requires: TaskRequires        # min_vram_mb, gpu_required, est_work_units
    attempts: int = 0

class TaskRequires(BaseModel):
    min_vram_mb: int
    gpu_required: bool
    est_work_units: float         # input to the cost model (samples * passes, or similar)

class TaskResult(BaseModel):
    task_id: str
    status: Literal["succeeded", "failed"]
    metrics: Optional[dict]       # for Search
    output_refs: Optional[list[str]]  # artifact hashes (for Map outputs / checkpoints)
    error: Optional[str]
```

## Versioning of the data model

- **Additive changes only.** New columns, new optional fields, new tables — never break existing readers.
- **Schema migrations** via lightweight versioned `_meta` table once the first version ships. v0.1 ships the schema as-is with no migration history.
- **JSON columns are explicitly typed by Pydantic.** Adding fields to `profile_json` or `spec_json` is a Pydantic schema change, validated on read with `extra='ignore'` so older Masters tolerate newer Workers.

## What's not in the data model

These are deliberate omissions per the architecture:

- **No per-Worker secrets** beyond the token (Workers don't authenticate with passwords or keypairs in v0.1).
- **No gradient state** (v0.1 has no distributed training; v0.4 adds gradient-related tables — see [ROADMAP v0.4](../roadmap.md#v04--distributed-data-parallel-training-the-big-paradigm)).
- **No user accounts / multi-tenancy** (one operator owns each Master).
- **No audit log** (the SQLite changelog itself + git history of artifact outputs is the audit trail).
