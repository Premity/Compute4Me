# System Overview

A narrative view of how Compute4Me is structured. Detailed data, module, and protocol references live in the sibling files in this folder.

## One-paragraph summary

A **Master** process opens a **Room** and issues **Invite Tokens**. A contributor runs one Docker container with a token and becomes a **Worker** — connecting *outbound only* to the Master, with no inbound ports or SSH or firewall changes. Each Worker advertises a **Capability Profile** (GPU, VRAM, throughput micro-benchmark, cached datasets, bandwidth/RTT). The researcher submits a **Job** — either a **Map** (containerized batch over data shards) or a **Search** (containerized batch over config space). The Master's **Decomposer** expands the Job into **Tasks**; the **Scheduler** assigns Tasks to Workers via best-fit-eligible placement (DL-aware: VRAM-feasibility, locality, faster-Worker-gets-bigger-Task). Workers run user images per the **Container Contract** (env-vars-in, files-out — no `import compute4me`), report results back through the Master, and stay idle waiting for more work. Failures heartbeat-detected within ~30s and retried; flaky Workers quarantined; Master state persisted to SQLite for restart recovery.

## High-level diagram

```
┌───────────────────────────────────────────────────────────────────┐
│                          MASTER (one container)                     │
│                                                                     │
│   ┌──────────────┐   WSS control     ┌───────────────────────────┐ │
│   │  Transport   │◄──────────────────│  per-Worker control conn  │ │
│   │  (WS server  │   HTTP artifacts  │  (heartbeat, dispatch,    │ │
│   │   + HTTP)    │◄──────────────────│   progress, cancel)       │ │
│   └──────┬───────┘                   └───────────────────────────┘ │
│          │                                                          │
│   ┌──────▼───────┐  ┌────────────┐  ┌────────────┐  ┌───────────┐  │
│   │   Token      │  │  Scheduler │  │   Job      │  │  Failure  │  │
│   │   service    │  │ + Cost     │  │ Decomposer │  │ controller│  │
│   │ (JWT/jti)    │  │   Model    │  │ (Map/Srch) │  │ (HB/retry │  │
│   └──────────────┘  └─────┬──────┘  └─────┬──────┘  │ /quaran.) │  │
│                           │               │         └───────────┘  │
│   ┌──────────────┐  ┌─────▼───────────────▼─────┐  ┌────────────┐  │
│   │  Artifact    │  │   Master State Store      │  │  Samplers  │  │
│   │  store       │  │   (SQLite: rooms, tokens, │  │  (Optuna / │  │
│   │  (origin)    │  │   workers, jobs, tasks,   │  │   raw list)│  │
│   └──────────────┘  │   artifacts, results)     │  └────────────┘  │
│                     └───────────────────────────┘                  │
└───────────────────────────────────────────────────────────────────┘
        ▲ outbound only                         ▲ outbound only
        │ WSS + HTTP                             │ WSS + HTTP
┌───────┴────────────────┐            ┌──────────┴─────────────────┐
│   WORKER (container)    │            │   WORKER (container)        │
│  ┌──────────────────┐   │            │   one per GPU per host      │
│  │ Worker daemon    │   │            │                             │
│  │  (WS client,     │   │            └─────────────────────────────┘
│  │   task loop)     │   │
│  ├──────────────────┤   │     ┌──────────────────────────────────┐
│  │ Capability       │   │     │ USER MODEL CONTAINER (black box)  │
│  │  profiler        │   │     │  reads C4M_CONFIG / C4M_INPUT_DIR │
│  ├──────────────────┤   │ run │  writes C4M_OUTPUT_DIR/metrics.json│
│  │ Container runner │───┼────►│  optional: progress.jsonl, c4m SDK│
│  ├──────────────────┤   │     └──────────────────────────────────┘
│  │ Artifact cache   │   │
│  └──────────────────┘   │
└─────────────────────────┘
```

## End-to-end flow

```
OPERATOR (Hamda)                          CONTRIBUTOR (Ali / lab)
─────────────────                         ───────────────────────
docker run compute4me serve --room R
  → Master up, SQLite state, self-signed cert
        │
compute4me token issue --room R --max-workers 1 --ttl 24h
  → prints Invite Token (room + cap + expiry + master_cert_fp + sig)
        │  (token handed over out of band: Signal, email)
        └──────────────────────────────────────────────►  docker run compute4me worker --token <T>
                                                                │ outbound WSS connect to master_cert_fp
                                                                │ pin cert, send join{token, profile}
        Master verifies token sig + cap ◄───────────────────────┘
        join_ack{worker_id}  ──────────────────────────────►  Worker idle, heartbeating every 10s
        │
SUBMIT (Python or CLI)
  submit_search(image, space, metric, n_trials, top_k)
        │
   Job Decomposer → N config-Tasks (Optuna ask)         Artifact Store (Master = origin)
        │                                                  ▲  HTTP GET /artifacts/<hash> (shard ranges)
   Scheduler (smart-pull, cost model, VRAM filter)         │
        │  on Worker pull → best-fit Task                  │
        └── task_assign{task_id, code_ref, args, inputs} ──┴─►  Worker: ensure_cached(inputs)
                                                                │ docker run user-image (Container Contract)
                                                                │   C4M_CONFIG / C4M_INPUT_DIR / C4M_OUTPUT_DIR
        task_result{metrics, output_refs} ◄─────────────────────┘ writes metrics.json + result artifacts
        │  (validate finite/schema; retry≤3; OOM→bigger Worker)
        ▼
   Failure controller (heartbeat 30s timeout → re-queue; quarantine flaky)
        │
COLLECT
  compute4me results <job_id> --out ./out   (top-K retained for Search)
```

## Lifecycle states

- **Worker:** `joining → idle → busy → (down | quarantined) → idle`
- **Task:** `pending → assigned → running → (succeeded | failed-retryable | failed-permanent)`
- **Job:** `queued → running → (completed | cancelled)` — completes when all Tasks reach a terminal state

## Component responsibilities

Each component is a deep module with a small, stable interface — see [modules.md](./modules.md) for signatures.

- **Transport** — persistent outbound WebSocket (control) + HTTP (artifacts). The seam behind which a future Sub-Master or P2P transport can slot. See [ADR-0007](../adr/0007-websocket-http-transport.md).
- **Token service** — issue/verify/revoke Invite Tokens; in-memory revocation + live per-token Worker counts.
- **Capability profiler** (Worker side) — gather GPU/CPU/RAM/disk facts, run the throughput micro-benchmark, list cached artifacts.
- **Cost model** — estimate per-`(Task, Worker)` runtime. Pure function.
- **Scheduler** — pending-Task priority queue; on a Worker pull, return best-fit eligible Task. See [ADR-0008](../adr/0008-smart-pull-scheduling.md).
- **Job decomposer** — expand a Map Job into shard-Tasks and a Search Job into config-Tasks (via Sampler).
- **Artifact store** — content-addressed blob storage; HTTP serve + ingest; Worker-side cache with hash verification. See [ADR-0012](../adr/0012-content-addressed-artifacts.md).
- **Master state store** — SQLite-backed persistence of Room/Worker/Job/Task/result records; recover on restart.
- **Failure controller** — heartbeat tracking, retry policy, OOM-promotion, quarantine, result validation.
- **Samplers** — pluggable search-space sampling. See [ADR-0010](../adr/0010-wrap-optuna.md).
- **Container runner** (Worker side) — launch the user image per the Container Contract. See [ADR-0006](../adr/0006-black-box-container-contract.md).

## Stack

- **Python throughout** — Master, Worker daemon, client lib; matches PyTorch/Optuna ecosystem; Master relays/schedules rather than number-crunches.
- **SQLite** for Master state.
- **WebSocket + HTTP** transport (not gRPC — firewall survival; see [ADR-0007](../adr/0007-websocket-http-transport.md)).
- **TLS via self-signed cert fingerprint pinned in the Invite Token** (no CA, no domain; see [ADR-0011](../adr/0011-tls-fingerprint-in-token.md)).
- Container images pulled from an accessible registry (Docker Hub / GHCR).
- Master ships as a container too (`docker run compute4me serve`), symmetric with Workers.

## Network model

- **Workers connect outbound-only to the Master.** No inbound ports, no Worker-to-Worker links by default. See [ADR-0003](../adr/0003-master-on-data-plane.md).
- **Master must be reachable from every Worker.** For a lab-only deployment, one lab machine on a routable interface; for cross-internet, a small VPS.
- **One Worker = one container.** A host with two GPUs runs two Worker containers if it wants both contributed.
- Direct Worker-to-Worker links and gossip-style aggregation are deferred — see [ROADMAP v0.5](../roadmap.md#v05--wan) and [ADR-0001](../adr/0001-flat-master-not-hierarchical.md).

## What this architecture is *not* designed for

These exclusions are deliberate and recorded in ADRs:

- **Open/public Rooms** where anyone joins without a token — see [ADR-0002](../adr/0002-closed-membership-rooms.md).
- **Byzantine-robust gradient aggregation** for untrusted Workers — trust is established out-of-band via Token issuance.
- **Models that don't fit on a single Worker's GPU** in v0.1–v0.5 — pipeline parallelism is a v0.6/v1.0 thread; see [ADR-0004](../adr/0004-big-models-out-of-scope.md).
- **Hierarchical multi-tier aggregation** (Sub-Masters per network tier) — held as later-additive via three rules in [ADR-0001](../adr/0001-flat-master-not-hierarchical.md).
- **Master HA / multi-process** — single-process Master + SQLite is the steady-state design for the target scale.

## Where to go from here

- **Want the data layer?** → [data-model.md](./data-model.md)
- **Want the module interfaces?** → [modules.md](./modules.md)
- **Want the wire protocol / API?** → [wire-protocol.md](./wire-protocol.md)
- **Want the decision rationale?** → [../adr/](../adr/)
- **Want the current milestone scope?** → [../prd.md](../prd.md)
- **Want what's coming next?** → [../roadmap.md](../roadmap.md)
