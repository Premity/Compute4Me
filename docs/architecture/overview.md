# System overview

How Compute4Me is structured, in pictures. Data, module and protocol detail live in the sibling files in this folder; terms are defined in [context.md](../context.md).

## One-paragraph summary

A **Master** process opens a **Room** and issues **Invite Tokens**. A contributor runs one Docker container with the Master's URL and a token, and becomes a **Worker**, connecting *outbound only*: no inbound ports, SSH or firewall changes. Each Worker advertises a **Capability Profile** (GPU, VRAM, a measured throughput benchmark, cached datasets, bandwidth/RTT). A researcher submits a **Job**: a **Map** (one container image over data shards) or a **Search** (one container image over a configuration space). The Master's **Decomposer** expands the Job into **Tasks**; the **Scheduler** hands each free Worker its best-fit eligible Task (VRAM-feasible, cached inputs first, faster Worker gets the bigger Task). Workers run user images under the **Container Contract** (env-vars-in, files-out, no `import compute4me`), report results through the Master, and wait for more. Dead Workers are detected within ~30 s and their Tasks retried; flaky Workers are quarantined; Master state is persisted in SQLite for restart recovery. Every state change is recorded as an **Event**.

## System context

*Concept; stable across versions.* Who uses Compute4Me and what it touches outside itself.

```mermaid
flowchart TB
    OP(["Operator<br/>runs the Master, issues tokens"])
    RS(["Researcher<br/>submits Jobs, reads results"])
    CT(["Contributor<br/>lends a GPU host"])
    subgraph SYS["Compute4Me"]
        M["Master<br/>one container"]
        W["Workers<br/>one container per GPU"]
    end
    DOCK["Worker host's Docker daemon<br/>plus the NVIDIA runtime"]
    REG[("Container registry<br/>user images, compute4me, compute4me-bench")]
    EXT["Experiment trackers<br/>W&B, MLflow, … (optional)"]
    OP -->|"serve, token issue, status"| M
    RS -->|"Python API or CLI, admin token"| M
    CT -->|"docker run … worker + Invite Token"| W
    W -->|"outbound WSS + HTTPS only"| M
    W -->|"docker run through the socket"| DOCK
    DOCK -->|"docker pull"| REG
    DOCK -.->|"user container talks to them directly,<br/>credentials via Job env"| EXT
```

Compute4Me never talks to an experiment tracker itself; it only forwards the Job's `env` ([wire-protocol.md §1](./wire-protocol.md#job-supplied-environment-variables-env)).

## Components

```mermaid
flowchart LR
    subgraph MASTER["Master container"]
        TR["Transport<br/>WSS control + HTTPS artifacts"]
        TOK["Token service<br/>JWT, jti, max_workers"]
        DEC["Job decomposer<br/>Map / Search plans"]
        SAM["Samplers<br/>Optuna, raw list"]
        SCH["Scheduler + cost model<br/>smart pull"]
        FC["Failure controller<br/>heartbeat, retry, quarantine"]
        ART["Artifact store<br/>content-addressed origin"]
        DB[("State store<br/>SQLite: rooms, tokens, workers,<br/>jobs, tasks, artifacts, results, events")]
    end
    subgraph WORKER["Worker container (one per GPU)"]
        DMN["Worker daemon<br/>WS client, task loop"]
        PRF["Capability profiler"]
        RUN["Container runner"]
        CCH["Artifact cache"]
    end
    subgraph HOST["Sibling containers on the Worker's host (via the host Docker socket)"]
        BENCH["Bench container<br/>ResNet18 benchmark"]
        USER["User model container<br/>reads C4M_CONFIG, C4M_INPUT_DIR<br/>writes C4M_OUTPUT_DIR"]
    end

    DMN -->|"outbound WSS"| TR
    CCH -->|"outbound HTTPS"| TR
    TR --> TOK
    TR --> SCH
    TR --> FC
    TR --> ART
    DEC --> SAM
    DEC --> SCH
    SCH --> DB
    FC --> DB
    TOK --> DB
    ART --> DB
    DMN --> PRF
    DMN --> RUN
    RUN --> CCH
    PRF -->|"docker run"| BENCH
    RUN -->|"docker run"| USER
```

| Component | Side | Responsibility | Interface |
|---|---|---|---|
| Transport | Master | One persistent WSS connection per Worker (control) and HTTP routes (artifacts); the seam where a Sub-Master or P2P transport could slot in later | [modules.md](./modules.md#master-transport--masterserverpy), [ADR-0007](../adr/0007-websocket-http-transport.md) |
| Token service | Master | Issue, verify and revoke Invite Tokens; live per-token Worker counts | [modules.md](./modules.md#token-service--mastertokenspy) |
| Job decomposer + Samplers | Master | Map Job → shard-Tasks; Search Job → config-Tasks, asked lazily from the Sampler | [modules.md](./modules.md#job-decomposer--masterdecomposerpy), [ADR-0010](../adr/0010-wrap-optuna.md) |
| Scheduler + cost model | Master | On a Worker pull, return the best-fit eligible Task | [modules.md](./modules.md#scheduler--masterschedulerpy), [ADR-0008](../adr/0008-smart-pull-scheduling.md) |
| Failure controller | Master | Heartbeat timeouts, retries, OOM promotion, quarantine, result validation | [modules.md](./modules.md#failure-controller--masterfailurepy) |
| Artifact store | Master | Content-addressed blobs; shard serving | [modules.md](./modules.md#artifact-store-master-side--masterartifactspy), [ADR-0012](../adr/0012-content-addressed-artifacts.md) |
| State store | Master | Durable SQLite state; restart recovery; the event log | [data-model.md](./data-model.md) |
| Worker daemon | Worker | Connect, pin the cert, join, heartbeat, run assigned Tasks, reconnect | [modules.md](./modules.md#worker-daemon--workerdaemonpy) |
| Capability profiler | Worker | Hardware facts, cached datasets, the benchmark (as a sibling container) | [modules.md](./modules.md#capability-profiler--workerprofilerpy), [ADR-0016](../adr/0016-benchmark-runs-as-a-container.md) |
| Container runner | Worker | Run the user image under the Container Contract via the host Docker socket | [modules.md](./modules.md#container-runner--workerrunnerpy), [ADR-0006](../adr/0006-black-box-container-contract.md) |
| Artifact cache | Worker | Fetch, verify and cache inputs; build shard directories | [modules.md](./modules.md#artifact-cache--workercachepy) |

## End-to-end flow

### Join

```mermaid
sequenceDiagram
    autonumber
    actor Op as Operator
    participant M as Master container
    actor C as Contributor
    participant W as Worker container
    participant B as Bench container
    Op->>M: docker run … serve --room R
    Note over M: create or load master.db, self-signed cert, signing key, Room R
    Op->>M: docker exec … token issue --room R --max-workers 1 --ttl 24h
    M-->>Op: Invite Token (room, cap, expiry, master_cert_fp, admin, jti)
    Op-->>C: Master URL + token (out of band)
    C->>W: docker run … -e C4M_MASTER=wss://host:8443 -e C4M_TOKEN=… worker
    W->>B: docker run bench image (host socket, same GPU)
    B-->>W: samples/sec (or failure → throughput_ref = None)
    W->>M: open WSS (outbound), pin cert by fingerprint from the token
    W->>M: join {token, CapabilityProfile}
    Note over M: verify signature, expiry, revocation, admit under max_workers
    M-->>W: join_ack {worker_id}
    Note over M: persist Worker (idle), event worker_joined
    M->>W: bandwidth probe (T10), RTT via ping
    loop every 10 s
        W->>M: heartbeat {worker_id, task_id?}
    end
```

### Submit, schedule, run, collect

```mermaid
sequenceDiagram
    autonumber
    actor R as Researcher
    participant M as Master
    participant W as Worker
    participant U as User container
    R->>M: submit_search(image, space, metric, n_trials, top_k) with an admin token
    Note over M: Decomposer: Search plan asks the Sampler lazily
    W->>M: (idle) heartbeat / previous task_result
    Note over M: Scheduler: feasible → cached inputs first → rank match by speed
    M->>W: task_assign {task_id, image, args, input_refs, requires}
    W->>M: GET /artifacts/… (only missing blobs of its shard)
    W->>U: docker run image with C4M_CONFIG, C4M_INPUT_DIR (ro), C4M_OUTPUT_DIR, C4M_TASK_ID, Job env
    loop while running
        U-->>W: progress.jsonl lines, stdout/stderr
        W->>M: task_progress, task_log
    end
    U-->>W: exit 0 + metrics.json
    W->>M: POST /tasks/{id}/outputs
    W->>M: task_result {status, metrics, output_refs}
    Note over M: validate (finite metric), persist, tell Sampler, keep top-K
    R->>M: fetch JOB_ID / job.results()
    M-->>R: top-K metrics and artifacts
```

### A Worker dies mid-Task

```mermaid
sequenceDiagram
    autonumber
    participant W1 as Worker A (busy)
    participant M as Master
    participant W2 as Worker B (idle)
    W1->>M: heartbeat {task_id: t7}
    Note over W1: laptop lid closed: no more heartbeats
    Note over M: failure controller tick: 30 s since last heartbeat
    Note over M: Worker A → down, t7 attempts += 1 → pending, event worker_down, task_retry
    W2->>M: idle pull
    M->>W2: task_assign t7
    Note over M: after 3 failed attempts: t7 → failed (siblings continue), event task_failed
```

### The Master restarts

*Planned (T20); the store's `load_*` calls exist since T03.*

```mermaid
sequenceDiagram
    autonumber
    participant M as Master (restarted)
    participant DB as master.db
    participant W as Worker
    M->>DB: load the cert (same fingerprint), signing key, revoked jtis
    M->>DB: load_open_jobs(), then load_pending_tasks(job) for each
    Note over M: assigned and running Tasks go back to pending, liveness is re-proved by heartbeat
    Note over M: Search Jobs rebuild the Sampler from the results table
    W->>M: reconnect with backoff, join again with the same token
    M-->>W: join_ack {worker_id}
    Note over M: today every join gets a new worker_id, T20 settles re-attach
    Note over M: scheduling resumes
```

## Lifecycle states

### Worker

```mermaid
stateDiagram-v2
    [*] --> joining: WSS open, join sent
    joining --> idle: join_ack
    joining --> [*]: join_reject
    idle --> busy: task_assign
    busy --> idle: task_result
    idle --> down: no heartbeat for 30 s
    busy --> down: no heartbeat for 30 s (Task re-queued)
    down --> idle: re-joins
    idle --> quarantined: ≥ 3 failed Tasks in 10 min
    busy --> quarantined: ≥ 3 failed Tasks in 10 min
    quarantined --> idle: after 5 min
```

### Task

```mermaid
stateDiagram-v2
    [*] --> pending: decomposed
    pending --> assigned: scheduled
    assigned --> running: Worker starts the container
    running --> succeeded: exit 0 and valid result
    running --> pending: failure, attempts < 3 (OOM → bigger Worker)
    assigned --> pending: Worker down
    running --> pending: Worker down
    running --> failed: failure, attempts = 3
    pending --> failed: Job cancelled
    running --> failed: Job cancelled (container stopped)
    succeeded --> [*]
    failed --> [*]
```

### Job

```mermaid
stateDiagram-v2
    [*] --> queued: submitted (admin token)
    queued --> running: first in the Room's FIFO
    running --> completed: every Task terminal
    running --> cancelled: compute4me cancel
    queued --> cancelled: compute4me cancel
    completed --> [*]
    cancelled --> [*]
```

The `tasks.status` column stores `pending | assigned | running | succeeded | failed` ([data-model.md](./data-model.md)); a retryable failure returns the Task to `pending` with `attempts + 1`.

## Network model

- **Workers connect outbound only to the Master** (control channel and artifacts). No inbound ports and no Worker-to-Worker links ([ADR-0003](../adr/0003-master-on-data-plane.md)).
- **The Master must be reachable from every Worker:** one lab machine on a routable interface, or a small VPS.
- **The Master URL and the token travel separately** ([ADR-0015](../adr/0015-master-url-separate-from-token.md)); the token's cert fingerprint authenticates whichever host answers ([ADR-0011](../adr/0011-tls-fingerprint-in-token.md)).
- **One Worker = one container.** A host with two GPUs runs two Worker containers to contribute both.
- **The Worker drives the host's Docker daemon** through the mounted socket to run bench and user containers. They are siblings on the host, which matters for GPU selection and volume paths ([deployment.md](./deployment.md)).

## Stack

- **Python 3.13 throughout** (Master, Worker daemon, client), pinned with uv ([ADR-0017](../adr/0017-python-toolchain.md)); the Master relays and schedules rather than computing.
- **SQLite** for Master state.
- **WebSocket + HTTP** over TLS, not gRPC ([ADR-0007](../adr/0007-websocket-http-transport.md)); TLS by fingerprint pinning, no CA or domain ([ADR-0011](../adr/0011-tls-fingerprint-in-token.md)).
- **One Docker image** for Master and Worker; no ML framework inside it ([ADR-0016](../adr/0016-benchmark-runs-as-a-container.md)).
- **stdlib logging + a persisted event table** ([ADR-0018](../adr/0018-logging-and-events.md)).
- User images come from an accessible registry (Docker Hub, GHCR).

## What this architecture is *not* designed for

Deliberate exclusions, each recorded in an ADR:

- **Open/public Rooms** without tokens ([ADR-0002](../adr/0002-closed-membership-rooms.md)).
- **Byzantine-robust aggregation** for untrusted Workers; trust is established out of band.
- **Models that don't fit one Worker's GPU** in v0.1–v0.5 ([ADR-0004](../adr/0004-big-models-out-of-scope.md)).
- **Hierarchical multi-tier aggregation** ([ADR-0001](../adr/0001-flat-master-not-hierarchical.md)).
- **Master HA / multi-process**: single-process Master + SQLite is the design at the target scale.

## Where to go from here

| Want | Read |
|---|---|
| The data layer | [data-model.md](./data-model.md) |
| Module interfaces | [modules.md](./modules.md) |
| Wire protocol, CLI, Python API | [wire-protocol.md](./wire-protocol.md) |
| Why a choice was made | [../adr/](../adr/README.md) |
| What v0.1 must do | [../prd.md](../prd.md) |
| What to build next | [../plan.md](../plan.md) |
