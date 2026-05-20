# Compute4Me

A Docker-native, master-orchestrated distributed deep learning fabric for heterogeneous, internet-connected machines. Workers join a closed-membership "room" with a single `docker run` and an invite token; the master decides how to split data, trials, or model parts across them based on their advertised capabilities.

## Language

**Fabric**:
The whole running system: one master plus the set of workers currently connected to it.
_Avoid_: cluster (implies admin-provisioned), swarm (overloaded with Docker Swarm and SWARM-parallelism).

**Master**:
The single logical orchestrator. Issues **Invite Tokens**, accepts **Worker** joins, holds **Capability Profiles**, decides task placement, and (in v0.1) aggregates gradients. **Workers** only ever connect *outbound* to the **Master** — there are no worker-to-worker connections by default. This makes the system work through any firewall/NAT without special config, at the cost of putting the **Master** on the data plane.
_Avoid_: head node, server, coordinator (ambiguous), controller (overloaded with k8s).

**Worker**:
A containerized process running on a contributor's machine that has joined a **Room** and executes assigned DL tasks. One container = one **Worker**, regardless of host. A host with two GPUs runs two Workers if it wants to contribute both.
_Avoid_: slave, node (a node is a host; a host can run multiple workers), agent.

**Room**:
A closed-membership compute pool owned by exactly one **Master**. Workers in one **Room** are isolated from other rooms on the same master. A job is submitted to a **Room** and runs on its current **Workers**.
_Avoid_: cluster, group, project.

**Invite Token**:
A JWT-style signed credential issued by the **Master**, and a *complete bootstrap credential*: it identifies the **Room**, authorizes the holder to join as a **Worker**, and authenticates the **Master** (it carries the Master's self-signed-cert fingerprint, which the Worker pins). Fields: `room`, `max_workers` (cap on concurrent workers using this token; nullable for unlimited), `expires_at` (default 30 days), `master_cert_fp`. The Master verifies the token signature offline and tracks live worker counts per token in memory.
_Avoid_: invite code, join key (acceptable as user-facing UX wording, but the canonical term is **Invite Token**).

**Capability Profile**:
A per-Worker record advertised on join and refreshed periodically (every ~10 min). Used by the **Master**'s scheduler to make heterogeneity-aware placement decisions. v0.1 fields:

- `host_id` — UUID, persisted in container volume, stable across restarts
- `gpu.model`, `gpu.vram_total_mb`, `gpu.vram_free_mb` — from `nvidia-smi`, or `"cpu"` if absent
- `cpu.cores`, `ram_mb` — from `os` / `psutil`
- `disk.free_mb` — `shutil.disk_usage` of the data volume
- `datasets.cached` — list of `(dataset_id, version_hash)` already unpacked locally, for **data locality** scheduling
- `throughput_ref` — samples/sec on a fixed 30s ResNet18 micro-benchmark. Standard yardstick across all Workers; this is the field the v0.1 scheduler keys off
- `bandwidth_to_master_mbps`, `rtt_to_master_ms` — Master-initiated probe

_Avoid_: spec, resources (too generic), node info.

**Job**:
A unit of work submitted to a **Room**. A **Job** is always one of two primitives:

- **Map Job** — run `code_ref` on N shards of input `D`, write results to `O`. Covers batch inference, preprocessing, feature extraction, evaluation. Sharding strategy is part of the submission.
- **Search Job** — run `code_ref` with N configurations sampled from a search space `S`, collect metric `M`, optionally retain top-K. Covers hyperparameter search, ablations, ensemble training.

Both decompose into **Tasks**. The **Worker** is agnostic to which primitive produced its Task. Distributed training (one model, N synchronized workers) is a separate primitive landing in v0.4.

**Task**:
The unit of scheduling and assignment. Has `code_ref` (container image + entrypoint), `args` (config), `inputs` (artifact refs), `outputs` (artifact refs), and `requires` (resource constraints: min VRAM, GPU required, est runtime). The **Master**'s scheduler matches Tasks to **Workers** based on Task `requires` and Worker **Capability Profile**.

**Artifact**:
A content-addressed blob (bytes + SHA-256 + metadata) — a dataset, a model checkpoint, or a Task output. The hash is the canonical identifier; a human name+version (`kepler-q1-q17/v3`) is a friendly alias resolving to a hash. The **Master** is the origin/source of truth; **Workers** pull Artifacts via HTTP and cache them content-addressed locally (advertised back via `datasets.cached`). Ingested via CLI upload or external-URL pull. Sharded into Tasks by **whole**, **index-range**, or **file-list** strategy.
_Avoid_: file, blob (acceptable internally), dataset (a dataset is one *kind* of Artifact).

**Real-time Throughput**:
A live samples/sec measurement maintained on the **Master** by exponential-moving-average over the **Worker**'s training-step heartbeats. **Collected in v0.1 for monitoring and health alerts only**; the scheduler does not yet re-assign work based on it. Mid-training re-balancing on this signal is a v0.2 feature.

**Scheduler**:
The component on the **Master** that assigns **Tasks** to **Workers**. v0.1 is **smart-pull**: the Master holds a priority queue of pending Tasks; when a Worker becomes free it is handed the *best-fit* eligible Task (enough VRAM, prefer cached inputs, give a fast Worker the biggest pending Task). Frames the problem as scheduling on *unrelated parallel machines* — a Task's runtime depends on which Worker runs it. Uses a coarse (within ~2×) DL-aware **Cost Model** to estimate per-`(Task, Worker)` runtime. Runs **one Job at a time per Room** in v0.1; Jobs queue FIFO. This heterogeneity-aware placement (vs Ray's "any node with a free GPU") is the project's primary novelty.
_Avoid_: placer, dispatcher, allocator.

**Container Contract**:
The model-agnostic interface between **Master** and a user's **Task** container. The container speaks **env-vars-in, files-out** — no `compute4me` import required in model code. Master launches the container with `C4M_CONFIG` (path to a JSON of Task args), `C4M_INPUT_DIR` (mounted input Artifacts), `C4M_OUTPUT_DIR` (where the container writes `metrics.json` and result Artifacts), and `C4M_TASK_ID`. Process exit code signals success (0) or failure. Optional `progress.jsonl` is tailed for live metrics. An optional **SDK** (`c4m.config()`, `c4m.report(...)`) is pure sugar over this contract. v0.1 assumes container images are pullable from an accessible registry (Docker Hub / GHCR).
_Avoid_: API, protocol (too generic), harness.

**Cost Model**:
The **Scheduler**'s estimate of how long a **Task** will take on a given **Worker**: `work_units(Task) / rate(Worker)`, where work is a flops estimate from the Task config and rate derives from the Worker's `throughput_ref`. Deliberately coarse in v0.1 — enough to beat round-robin; sharpened by **Real-time Throughput** in v0.2.

## Relationships

- A **Master** owns one or more **Rooms**.
- A **Room** has many **Invite Tokens** and many **Workers**.
- An **Invite Token** belongs to exactly one **Room** and admits up to `max_workers` concurrent **Workers**.
- A **Job** belongs to exactly one **Room**; it decomposes into many **Tasks**.
- A **Task** is assigned to at most one **Worker** at a time (failed Tasks may be re-assigned).
- A **Worker** joins exactly one **Room** via exactly one **Invite Token** and publishes a **Capability Profile** to its **Master**.
- A **Worker** is one container; a host may run multiple **Workers** (typically one per GPU).

## Example dialogue

> **Hamda:** "I want to let Ali use his RTX 3070 on tonight's training run."
> **Reviewer:** "Issue him an **Invite Token** for the `exoplanet-search` **Room**, `max_workers=1`, expires in 24h. He runs the container, the **Master** verifies the token, profiles his card, and he becomes a **Worker** in that **Room**."
> **Hamda:** "What if my whole lab wants in?"
> **Reviewer:** "Issue one **Invite Token** for the lab with `max_workers=4`. Each of the four machines runs the container with the same token; the **Master** lets all four in and refuses the fifth."

## Flagged ambiguities

- "node" vs "worker" — resolved: a **Node** (host) can run multiple **Workers** (containers). The unit of scheduling and accounting is the **Worker**.
- "cluster" — avoided throughout because it implies admin-provisioned static membership; we use **Room** for the membership boundary and **Fabric** for the live system.
- "slave" — not used; **Worker**.

## Network assumptions

- **Workers only make outbound connections to the Master.** No inbound ports, no worker-to-worker connections, no NAT traversal in v0.1. Justified by the observation that many LAN environments (and all NAT'd home networks) forbid the alternatives.
- **Master must be reachable from every Worker.** For a lab-only deployment this is one of the lab machines on a routable interface; for cross-internet deployments this is a small VPS.
- Direct worker-to-worker links and gossip-style aggregation are deferred to later versions.

## Implementation stack (v0.1)

- **Python throughout** (Master, Worker daemon, client lib) — matches the PyTorch/Optuna ecosystem; the Master relays and schedules rather than number-crunches, so no perf case for Go/Rust.
- **Transport**: a single persistent *outbound* **WebSocket** Worker→Master for the control channel (heartbeats, Task dispatch, cancellation, progress); separate **HTTP** GETs for bulk Artifact pulls. WebSocket chosen over gRPC because HTTP/2 is frequently mangled by proxies/firewalls — and surviving firewalls is the whole premise (see [ADR-0003](./docs/adr/0003-master-on-data-plane.md)).
- **TLS**: Master holds a self-signed cert; its fingerprint rides in every **Invite Token** and the Worker pins it. No CA, no domain, no Let's Encrypt. Not mutual — the token already authenticates the Worker.
- **Master state**: SQLite file.
- **Interfaces**: Python API primary for job submission (`from compute4me import submit`); CLI primary for ops (`compute4me serve` / token issue / status / results). Shared client library.
- **Master** ships as a container too (`docker run compute4me serve`), symmetric with Workers.

## Failure handling (v0.1)

- **Heartbeat**: Workers send a liveness ping to the Master every 10s carrying current Task ID. No heartbeat for 30s ⇒ Worker marked `down`; its assigned Task is re-queued.
- **Task retries**: 3 attempts total. On OOM, the second retry must go to a Worker with ≥ 2× the original VRAM if one is available. After 3 failures, the Task is permanently `failed` and surfaced to the user — it does not block other Tasks in the Job.
- **Result validation**: Search Job returned metric must be a finite float; Map Job output artifact must exist and match the declared schema. Failures here count as Task failures. We do **not** attempt to detect adversarial outputs (that's Byzantine, out of scope).
- **Quarantine**: a Worker that fails ≥ 3 Tasks in a 10-minute window is quarantined for 5 minutes, then auto-returned to the pool. No permanent blacklist.
- **Master persistence**: Master state (Room, Worker registry, Job/Task state, result refs) is persisted to a local SQLite file. On Master restart, Workers re-heartbeat and scheduling resumes.
- **Cancellation**: User-issued Job cancel triggers SIGTERM (30s grace) then SIGKILL on Worker containers running Tasks for that Job. Partial Task results are discarded; collected Task results are returned.
- **Out of scope for v0.1**: mid-Task checkpointing (a dying Worker loses its in-progress work), exactly-once Task execution (idempotent Tasks may run twice if a Worker reported success but the heartbeat was lost — fine for v0.1 workloads).

## Out of scope (v0.1–v0.5)

- **Models that do not fit on a single Worker's GPU.** v0.1–v0.5 assumes each **Worker** holds the entire model. This covers research models up to ~10B params on consumer 24 GB cards — essentially the entire space of "models trainable on consumer hardware." Supporting larger models requires model parallelism (FSDP, tensor parallel, pipeline parallel), which is a separate research thread sketched for v1.0+ as **master-orchestrated pipeline parallelism over a hub topology** (the layer-assignment cousin of SWARM Parallelism).
- Byzantine-robust aggregation. Trust is established out-of-band via **Invite Token** issuance; bug-level defenses (gradient-norm sanity checks) are sufficient for closed-membership rooms.
- Fully-open / public **Rooms** where anyone can join without a token.
- Cryptographic privacy (secure aggregation, differential privacy, homomorphic encryption).
- Multi-tier / hierarchical aggregation (see [ADR-0001](./docs/adr/0001-flat-master-not-hierarchical.md)).
