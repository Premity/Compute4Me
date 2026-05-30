# Compute4Me PRD — v0.1 (in development)

> **Status:** v0.1 is the current milestone in active development. When v0.1 ships (`v0.1.0` tag), this document is archived to `docs/archive/prd-v0.1.md` and rewritten for v0.2.
>
> **Scope:** this PRD specifies **v0.1**. Later milestones (v0.2–v1.0) live in [roadmap.md](./roadmap.md).
> **Terminology:** [context.md](./context.md).
> **Architecture:** [architecture/](./architecture/) — durable across versions; this PRD references rather than duplicates.
> **Decisions:** [adr/](./adr/).
> **Workflow:** [../CONTRIBUTING.md](../CONTRIBUTING.md).

---

## 0. How to Use This PRD

This document is split into a **reference half** (§1–§7), the **execution plan** (§8 — the T-task list), and an **execution-adjacent reference half** (§9–§14: eval runbook, testing, risks, acceptance criteria, out of scope, further notes). Each T-task is self-contained — prerequisites, deliverables, file paths, and acceptance criteria — so it can be lifted into its own task file and handed to a coding agent.

Conventions:
- **T-IDs** identify implementation tasks. Format: `T<nn>`, grouped into dependency-ordered phases.
- **Phases** (not time-boxed — this is a solo research build):
  - **P0 — Scaffolding** (T01–T04): repo, types, state store, container image.
  - **P1 — Control-plane bootstrap** (T05–T10): tokens, transport, join, capability profiling. *Tracer bullet: a Worker joins; the Master records its profile.*
  - **P2 — Job execution core** (T11–T17): artifact store, decomposer, cost model, scheduler, container runner. *Tracer bullet: a tiny Search Job runs E2E on fake Workers.*
  - **P3 — Reliability** (T18–T21): heartbeat, retries, quarantine, persistence, cancellation.
  - **P4 — Interfaces & observability** (T22–T24): CLI, Python API, SDK, status view.
  - **P5 — Eval & research harness** (T25–T27): `spacesight` images, 3-arm scheduler experiment, scale simulation.
- **Greenfield repo.** No code exists yet; these tasks establish the patterns.

---

## 1. Vision & Scope

### 1.1 Problem Statement

I'm an ML researcher with limited, scattered compute: a handful of lab GPU machines, a CPU box, and the occasional GPU I could borrow from someone nearby. I want to use all of it together to get my deep-learning work done faster — running many model variants, scoring large datasets, sweeping hyperparameters.

The existing tools don't fit:

- **Ray / Horovod / PyTorch DDP** assume a cluster I administer: nodes I provision, SSH into, configure firewalls for, and add by hand. Getting a friend's machine — or even my own lab machines, which can't freely reach each other on our segmented LAN — into a job is painful.
- **Hivemind / SWARM** can pool internet volunteers, but force me to rewrite my model into their decentralized Mixture-of-Experts framework. Useless for a standard model like my InceptionResNet exoplanet detector.
- All of them treat my heterogeneous hardware as interchangeable — they don't know my RTX 3070 is 4× faster than my GTX 1060, or that one machine already has the dataset cached.

I want something I can actually use, where a machine joins with **one `docker run`**, brings a **standard containerized model** (no framework rewrite), and the system is **smart about my heterogeneous, firewall-constrained fleet**.

### 1.2 Solution

**Compute4Me** is a Docker-native, master-orchestrated compute **Fabric** for embarrassingly-parallel deep-learning work on heterogeneous, firewall-constrained machines. See [architecture/overview.md](./architecture/overview.md) for the one-paragraph description, the high-level diagram, and the end-to-end flow.

v0.1 makes my lab + a friend's GPU usefully poolable for HPO and batch inference, and doubles as the substrate for a research contribution: **automatic, DL-aware, heterogeneity-native scheduling for containerized volunteer fabrics**.

### 1.3 v0.1 Scope (locked)

- **Two Job primitives:** Map and Search ([ADR-0009](./adr/0009-map-search-primitives.md)). No distributed *training* (that's v0.4).
- **Closed-membership Rooms** via signed Invite Tokens; trust established out-of-band ([ADR-0002](./adr/0002-closed-membership-rooms.md)). Admin capability on tokens for Job submission ([ADR-0014](./adr/0014-admin-tokens-for-submission.md)). No Byzantine defenses.
- **Models that fit on a single Worker GPU** ([ADR-0004](./adr/0004-big-models-out-of-scope.md)) — covers ~10B params on a 24 GB card.
- **One Job at a time per Room**, FIFO queue. Multi-Job concurrency is v0.2.
- **Master on the data plane**, Workers outbound-only ([ADR-0003](./adr/0003-master-on-data-plane.md)). Master URL passed separately from token so the Master can be moved without re-issuing tokens ([ADR-0015](./adr/0015-master-url-separate-from-token.md)).
- **Real-time throughput collected for monitoring only** — the scheduler keys off the join-time micro-benchmark.
- **Container Contract** with env-vars-in / files-out, plus `env={...}` Job-spec pass-through so users' model images reach W&B / MLflow / TensorBoard / etc. directly without Compute4Me proxying ([ADR-0006](./adr/0006-black-box-container-contract.md), [wire-protocol.md §1](./architecture/wire-protocol.md)).
- **CLI surface:** flat with one nested `token` group; five-command observability split (`status`, `progress`, `logs`, `events`, `fetch`); foreground-default for `serve`/`worker` ([ADR-0013](./adr/0013-cli-design-and-observability.md)).

### 1.4 Audience

Researchers with lab GPUs + friends' consumer GPUs — the majority of ML work that fits on one card. Compute4Me deliberately does **not** target the train-a-70B-model audience, who have cloud/supercomputer options.

### 1.5 Out of Scope (summary)

Full registry in §13 and [roadmap.md](./roadmap.md). Headlines: distributed training (v0.4), WAN sync regimes (v0.5), big-model inference/training (v0.6/v1.0). **Never in this design:** open/public Rooms, Byzantine-robust aggregation, cryptographic privacy, hierarchical aggregation, Master HA.

---

## 2. Personas & Eval Workload

### 2.1 Hamda — Operator + Researcher (primary)

ML researcher. Owns 4 lab GPU machines (mixed: e.g. RTX 3070, RTX 3060, 2× GTX 1060) on a segmented LAN, plus a CPU box, plus a small VPS to host the Master. Runs HPO sweeps and batch inference for the `spacesight` exoplanet-detection work. Wants: one command to pool everything, smart placement, and a clean results download. Is also the paper author — needs the run to double as an experiment.

### 2.2 Ali — Contributor (secondary)

Friend with an RTX 3070 in his apartment behind a home NAT. Will run a container if it's *one command and touches nothing else on his machine*. Will not configure SSH, port-forwarding, or a firewall rule. Trusted (Hamda vouches for him) but his machine is flaky — he may close his laptop mid-run.

### 2.3 The Lab Fleet — Contributors (batch)

Four lab machines admitted under a single `max_workers=4` token. On a segmented LAN where the machines can reach the VPS Master but not freely reach each other — exactly the case that breaks Ray's peer-to-peer assumptions.

### 2.4 Eval Workload — `spacesight`

The concrete v0.1 workload is the **InceptionResNet exoplanet detector** over Kepler light curves:

- **Search Job:** an Optuna HPO sweep (~32–64 trials) over learning rate, dropout, augmentation strength.
- **Map Job:** batch inference / scoring over a large light-curve dataset, sharded by file-list.

This is also the centerpiece of the research eval (§9).

---

## 3. End-to-End Flow

See [architecture/overview.md §End-to-end flow](./architecture/overview.md) for the ASCII trace through operator startup → token issue → Worker join → Job submit → schedule → run → collect.

### 3.1 Lifecycle states

- **Worker:** `joining → idle → busy → (down | quarantined) → idle`.
- **Task:** `pending → assigned → running → (succeeded | failed-retryable | failed-permanent)`.
- **Job:** `queued → running → (completed | cancelled)`; completes when all Tasks reach a terminal state.

---

## 4. Architecture (reference only)

Architecture is documented separately because it's **durable across versions**. v0.1 establishes it; v0.2+ extends additively.

- **[architecture/overview.md](./architecture/overview.md)** — high-level diagram, component responsibilities, network model, stack.
- **[architecture/data-model.md](./architecture/data-model.md)** — SQLite schema + Pydantic schemas.
- **[architecture/modules.md](./architecture/modules.md)** — interface signatures for every module.
- **[architecture/wire-protocol.md](./architecture/wire-protocol.md)** — Container Contract, WS control channel, HTTP artifact channel, CLI, Python API.

The PRD references these rather than duplicating them. When v0.2 begins, this section's links stay; the architecture docs receive additive amendments.

---

## 5. Repo Layout (planned)

```
compute4me/
├── README.md                       # public-facing intro
├── LICENSE
├── CONTRIBUTING.md                 # dev workflow (branching, commits, PRs, tests, manual phase)
├── CHANGELOG.md
├── SECURITY.md
├── .pre-commit-config.yaml         # local hooks (ruff + mypy + md link check)
├── .github/
│   ├── workflows/ci.yml            # ci-test + ci-lint + ci-types jobs
│   ├── PULL_REQUEST_TEMPLATE.md
│   └── ISSUE_TEMPLATE/{polish,bug}.md, config.yml
├── pyproject.toml                  # uv-managed; Python 3.13
├── Dockerfile                      # single image: `serve` and `worker` entrypoints
├── docker-compose.dev.yml          # local: 1 master + 2 fake workers for E2E smoke test
├── Makefile                        # make dev / test / image / e2e
├── docs/                           # everything in this folder
│   ├── README.md
│   ├── prd.md  (this file)
│   ├── context.md
│   ├── roadmap.md
│   ├── adr/
│   ├── architecture/
│   ├── research/
│   └── archive/                    # archived PRDs of past versions
├── src/compute4me/
│   ├── __init__.py                 # public API
│   ├── types.py                    # Pydantic models (CapabilityProfile, Job specs, Task, ...)
│   ├── proto/messages.py           # WS wire message models
│   ├── cli.py                      # serve / worker / token / status / progress / logs / events / fetch / jobs / cancel
│   ├── master/
│   │   ├── server.py               # WS + HTTP app
│   │   ├── tokens.py
│   │   ├── scheduler.py
│   │   ├── cost_model.py
│   │   ├── decomposer.py
│   │   ├── failure.py
│   │   ├── artifacts.py
│   │   ├── state.py
│   │   └── samplers/{base.py, optuna_sampler.py}
│   ├── worker/
│   │   ├── daemon.py
│   │   ├── profiler.py
│   │   ├── runner.py
│   │   └── cache.py
│   ├── sdk/__init__.py             # c4m.config / input_dir / output_dir / report / progress
│   └── client/api.py               # Client.submit_search / submit_map / wait / download
├── scripts/
│   └── check_md_links.py
├── tests/
│   ├── INDEX.md                    # map of T-task → test files
│   ├── unit/                       # cost_model, scheduler, decomposer, tokens, failure, artifacts
│   ├── fakes/                      # FakeWorker, fake hw probes, fake container runner
│   └── integration/test_e2e_search.py
└── examples/
    └── resnet18_hpo/               # sample user container honoring the Container Contract
```

---

## 6. User Stories

### Joining and membership
1. As an operator, I want to start a Master and open a named Room, so that Workers have something to join.
2. As an operator, I want to issue an Invite Token for a Room, so that I can admit a specific contributor.
3. As an operator, I want to set `max_workers` on a token (or leave it unlimited), so that I can cap how many concurrent Workers a token admits.
4. As an operator, I want tokens to expire (default 30 days), so that a leaked or forgotten token doesn't stay valid forever.
5. As an operator, I want to issue multiple tokens for the same Room with different limits, so that I can give my lab a 4-worker token and a guest a single-use one.
6. As an operator, I want to revoke a token, so that I can kick a contributor without disrupting the others.
7. As a contributor, I want to join a Room with a single `docker run ... --token ...`, so that I don't have to configure SSH, firewalls, or open ports.
8. As a contributor, I want my machine to connect outbound only, so that I can contribute from behind a NAT or corporate firewall without special permission.
9. As a contributor, I want to run one container per GPU, so that I can contribute multiple cards from one host.
10. As a contributor, I want the Master's identity verified automatically when I join, so that my token can't be replayed against an impostor Master.

### Capability discovery
11. As the Scheduler, I want each Worker to advertise GPU model, total/free VRAM, CPU cores, and RAM on join, so that I can filter out Workers that can't run a Task.
12. As the Scheduler, I want each Worker to run a fixed throughput micro-benchmark on join, so that I have a comparable speed estimate before any real work runs.
13. As the Scheduler, I want each Worker to report which datasets it already has cached, so that I can prefer placing data-heavy Tasks where the data already is.
14. As the Scheduler, I want each Worker to report free disk and bandwidth/latency to the Master, so that I can avoid sending huge datasets to Workers that can't hold them or fetch them quickly.
15. As an operator, I want Workers to refresh their profile periodically, so that the Scheduler reacts to changing free VRAM or measured throughput.

### Submitting and running work
16. As a researcher, I want to submit a Search Job describing a model image, a search space, and a metric, so that the Fabric runs my hyperparameter sweep across the Room.
17. As a researcher, I want to express the search space with Optuna, so that I get TPE/Bayesian sampling without learning a new DSL.
18. As a researcher, I want to alternatively pass a plain list of configs, so that I can run a simple grid without Optuna.
19. As a researcher, I want to submit a Map Job describing a model image, an input dataset, and a shard strategy, so that the Fabric runs inference/eval/preprocessing over shards in parallel.
20. As a researcher, I want to keep only the top-K results of a Search, so that I'm not drowned in artifacts from a 64-trial sweep.
21. As a researcher, I want my model container to receive its config and inputs via env vars and mounted directories, so that I don't have to import any Compute4Me library into my model code.
22. As a researcher, I want my container to report results by writing files to an output directory, so that the contract is debuggable and language-agnostic.
23. As a researcher, I want to optionally use a small SDK helper to read config and report metrics, so that I get ergonomics when I want them without being forced into them.
24. As a researcher, I want to run my container locally with the same env vars, so that I can reproduce exactly what a Worker does when debugging.

### Scheduling behavior
25. As the Scheduler, I want to hand a free Worker the best-fit eligible Task rather than the next one in line, so that fast Workers get the heaviest Tasks.
26. As the Scheduler, I want to estimate each Task's runtime per Worker from a coarse cost model, so that I can minimize overall makespan on a heterogeneous fleet.
27. As the Scheduler, I want to prefer Workers that already cache a Task's inputs, so that I minimize data transfer.
28. As the Scheduler, I want to refuse to place a Task on a Worker without enough VRAM, so that the model can actually fit.
29. As an operator, I want one Job to run at a time per Room with others queued FIFO, so that v0.1 behavior is predictable.
30. As a researcher, I want a fast Worker to naturally pull more Tasks than a slow one, so that the fleet self-balances without manual tuning.

### Artifacts
31. As a researcher, I want to push a dataset to the Master from my laptop or from an external URL, so that the Fabric can distribute it.
32. As the Fabric, I want artifacts identified by content hash, so that Workers can cache, dedup, and verify them.
33. As a Worker, I want to fetch only the shard I'm assigned, so that I don't download an 80 GB dataset to process 1/20th of it.
34. As a Worker, I want to skip downloading an artifact I already have cached, so that repeated Jobs on the same data are fast.
35. As a researcher, I want to download my Job's results from the Master via the CLI, so that I can collect metrics and checkpoints.

### Reliability
36. As an operator, I want a Worker that stops responding to be detected within ~30s and its Task re-queued, so that one machine dropping doesn't stall the Job.
37. As an operator, I want a failed Task retried up to 3 times, so that transient failures self-heal.
38. As the Scheduler, I want an OOM-failed Task retried on a Worker with more VRAM, so that a too-big trial lands somewhere it fits.
39. As an operator, I want a permanently-failed Task surfaced without blocking the rest of the Job, so that one bad trial doesn't sink a 64-trial sweep.
40. As an operator, I want a Worker that fails repeatedly to be quarantined briefly then auto-restored, so that a flaky machine doesn't poison the run but isn't permanently lost.
41. As the Fabric, I want returned metrics validated as finite and outputs validated against a schema, so that buggy Workers' garbage results are caught.
42. As an operator, I want the Master to persist its state, so that restarting it (or my laptop) resumes the Job instead of losing it.
43. As a researcher, I want to cancel a running Job and still get the results collected so far, so that I can stop early without losing partial progress.

### Observability
44. As an operator, I want a status view of the Room — connected Workers, their profiles, live throughput, quarantine events — so that I can see what's happening.
45. As a researcher, I want live progress from running Tasks, so that I can watch a sweep proceed.

---

## 7. Implementation Decisions (ADR Index)

All architectural decisions recorded in [adr/](./adr/). Headline list:

- **Closed-membership Rooms via signed Invite Tokens.** ([ADR-0002](./adr/0002-closed-membership-rooms.md))
- **Master on the data plane; Workers connect outbound only.** ([ADR-0003](./adr/0003-master-on-data-plane.md))
- **Flat single Master.** Hierarchy held as later-additive via three rules. ([ADR-0001](./adr/0001-flat-master-not-hierarchical.md))
- **Roll our own orchestration, not Ray.** ([ADR-0005](./adr/0005-roll-our-own-orchestration.md))
- **Two primitives — Map and Search.** Pipeline arrives in v0.6. ([ADR-0009](./adr/0009-map-search-primitives.md))
- **Black-box container contract (env-vars-in / files-out), optional SDK sugar.** ([ADR-0006](./adr/0006-black-box-container-contract.md))
- **Smart-pull scheduling** with a coarse DL-aware cost model. ([ADR-0008](./adr/0008-smart-pull-scheduling.md))
- **Wrap Optuna behind a pluggable Sampler interface.** ([ADR-0010](./adr/0010-wrap-optuna.md))
- **Content-addressed Artifacts, Master as origin.** ([ADR-0012](./adr/0012-content-addressed-artifacts.md))
- **WebSocket control channel + HTTP artifacts, not gRPC.** ([ADR-0007](./adr/0007-websocket-http-transport.md))
- **TLS via self-signed cert fingerprint pinned in the Invite Token.** ([ADR-0011](./adr/0011-tls-fingerprint-in-token.md))
- **Models must fit on a single Worker's GPU** in v0.1–v0.5. ([ADR-0004](./adr/0004-big-models-out-of-scope.md))

---

## 8. Implementation Tasks (T01–T27)

Each task is self-contained: prerequisites, deliverables, file paths, and acceptance criteria. Phases are dependency-ordered (§0). For execution discipline (branches, commits, PRs, tests, manual phase), see [../CONTRIBUTING.md](../CONTRIBUTING.md).

---

### P0 — Scaffolding

#### T01 — Repo skeleton + packaging + image
**Prereqs:** none.
**Deliverables:** `pyproject.toml` (uv, Python 3.13), `src/compute4me/` package per §5, single `Dockerfile` with `serve` and `worker` entrypoints, `Makefile` (`dev`, `test`, `image`, `e2e`). Empty module files with docstrings.
**Acceptance:** `uv sync` resolves; `docker build` produces an image; `compute4me --help` lists `serve/token/status/results/cancel/worker`.

#### T02 — Core types (`types.py`)
**Prereqs:** T01.
**Deliverables:** Pydantic models per [architecture/data-model.md](./architecture/data-model.md) — `CapabilityProfile`/`GpuInfo`, `SearchJobSpec`/`MapJobSpec`/`ShardStrategy`, `TokenClaims`, internal `Task`, `TaskResult`, `TaskError`, `ShardDescriptor`.
**Acceptance:** models round-trip JSON; invalid payloads raise `ValidationError`; `n_shards>0` enforced for non-`whole` strategies.

#### T03 — Master state store (`master/state.py`)
**Prereqs:** T02.
**Deliverables:** SQLite schema per [architecture/data-model.md §Master State Store](./architecture/data-model.md) created on first `serve`; save/load for rooms, tokens, workers, jobs, tasks, artifacts, results; `load_open_jobs()` / `load_pending_tasks()` for restart recovery.
**Acceptance:** schema applies on empty DB; a Job + its Tasks survive a process restart; indices present.

#### T04 — Wire message models (`proto/messages.py`)
**Prereqs:** T02.
**Deliverables:** Pydantic models for every WS message in [architecture/wire-protocol.md §2](./architecture/wire-protocol.md), discriminated union on `type`.
**Acceptance:** each message serializes/deserializes; unknown `type` rejected; `join` carries a full `CapabilityProfile`.

---

### P1 — Control-plane bootstrap *(tracer bullet: a Worker joins; the Master records its profile)*

#### T05 — Token service (`master/tokens.py`)
**Prereqs:** T02, T03.
**Deliverables:** `issue/verify/revoke/admit/release` per [architecture/modules.md §Token service](./architecture/modules.md); JWT sign/verify with a Master-held key; in-memory revocation set + per-`jti` live worker counter; metadata persisted via T03.
**Acceptance:** issue→verify round-trips; expired token rejected; revoked `jti` rejected; `admit` allows up to `max_workers` then refuses; `release` frees a slot; `master_cert_fp` present in claims.

#### T06 — Self-signed TLS + fingerprint (`master/server.py`, `worker/daemon.py`)
**Prereqs:** T05.
**Deliverables:** Master generates/persists a self-signed cert; its sha256 fingerprint is embedded in issued tokens; Worker pins the fingerprint from its token and refuses a mismatched cert.
**Acceptance:** Worker connects over WSS when fingerprint matches; connection refused on mismatch; no CA / domain required. ([ADR-0011](./adr/0011-tls-fingerprint-in-token.md))

#### T07 — WebSocket transport server (`master/server.py`)
**Prereqs:** T04, T06.
**Deliverables:** WS server accepting one persistent connection per Worker; dispatches inbound messages; can push `task_assign`/`task_cancel`/`bandwidth_probe`; per-Worker send queue.
**Acceptance:** a test client opens a connection, exchanges a ping/heartbeat, and the Master tracks it as connected; closing the socket marks the Worker disconnected and calls `release`.

#### T08 — Worker daemon + join handshake (`worker/daemon.py`)
**Prereqs:** T07.
**Deliverables:** outbound WS client; on start, builds profile (T09), sends `join`, handles `join_ack`/`join_reject`; heartbeat loop every 10s; reconnect-with-backoff.
**Acceptance:** Worker joins a running Master and receives `worker_id`; bad token → `join_reject` with reason; Worker reconnects after a transient drop.

#### T09 — Capability profiler + micro-benchmark (`worker/profiler.py`)
**Prereqs:** T02.
**Deliverables:** `profile()` gathering GPU (nvidia-smi or `cpu`), CPU/RAM/disk (psutil/shutil), `datasets_cached`; `run_micro_benchmark()` (fixed 30s ResNet18 fwd/bwd → samples/sec); persistent `host_id`.
**Acceptance:** on a GPU host reports real `gpu.model` + VRAM; on CPU-only reports `model='cpu'`; micro-benchmark returns a positive `throughput_ref`; `host_id` stable across restarts; testable with injected fake probes.

#### T10 — Bandwidth/RTT probe + periodic profile refresh
**Prereqs:** T07, T09.
**Deliverables:** Master-initiated `bandwidth_probe`; Worker sends `profile_update` every ~10 min; state store updated.
**Acceptance:** profile shows non-zero `bandwidth_to_master_mbps`/`rtt_to_master_ms`; a refresh after freeing VRAM updates `vram_free_mb` in the Master's view.

---

### P2 — Job execution core *(tracer bullet: a tiny Search Job runs E2E on a fake Worker)*

#### T11 — Artifact store, Master origin (`master/artifacts.py`)
**Prereqs:** T03.
**Deliverables:** `put(bytes|url)→hash`, `get`, content-addressed storage on disk; HTTP `GET /artifacts/{hash}` (Range) + `POST /artifacts`; name/version alias resolution.
**Acceptance:** same bytes → same hash; upload then GET returns identical bytes; URL ingest fetches and hashes; alias `name/version` resolves to the hash.

#### T12 — Shard serving + Worker cache (`master/artifacts.py`, `worker/cache.py`)
**Prereqs:** T11.
**Deliverables:** `serve_shard` for `index-range`/`file-list`; Worker `ensure_cached(hash, shard)` fetch+verify, skip-if-present; `datasets_cached` reflects the local cache.
**Acceptance:** a Worker fetches only its shard (asserted bytes transferred ≈ 1/N); a second Task on cached data does zero transfer; hash mismatch → re-fetch + error.

#### T13 — Sampler interface + Optuna + raw list (`master/samplers/`)
**Prereqs:** T02.
**Deliverables:** `Sampler` protocol; `OptunaSampler` (ask/tell, TPE); `RawListSampler`.
**Acceptance:** with a seeded Optuna sampler, `ask()` is deterministic; `tell()` influences subsequent asks; raw-list yields exactly the provided configs in order. ([ADR-0010](./adr/0010-wrap-optuna.md))

#### T14 — Job decomposer (`master/decomposer.py`)
**Prereqs:** T13, T02.
**Deliverables:** `decompose(SearchJobSpec)` → N config-Tasks via Sampler; `decompose(MapJobSpec)` → shard-Tasks per ShardStrategy; each Task carries `requires` (min_vram, est_work_units).
**Acceptance:** seeded Search emits the expected set of config-Tasks; Map emits exactly `n_shards` Tasks with non-overlapping, exhaustive shard descriptors; `whole` emits 1 Task.

#### T15 — Cost model (`master/cost_model.py`)
**Prereqs:** T02.
**Deliverables:** `estimate(task, worker)` = `work_units / rate(worker)`; `feasible(task, worker)` VRAM/GPU filter. Pure functions.
**Acceptance:** for two Workers differing only in `throughput_ref`, the faster gets the lower estimate in proportion; a Task needing more VRAM than a Worker has is `feasible=False`. Estimates within ~2× on the eval workload (calibration deferred to v0.2).

#### T16 — Smart-pull scheduler (`master/scheduler.py`)
**Prereqs:** T14, T15.
**Deliverables:** pending-Task priority queue; `next_task_for(worker)` returns best-fit eligible Task (feasibility filter → cached-input locality preference → fast-Worker-gets-biggest); one Job at a time per Room, FIFO. ([ADR-0008](./adr/0008-smart-pull-scheduling.md))
**Acceptance (no network):** given fixed Tasks + profiles — fast Worker is assigned the biggest pending Task; VRAM-infeasible Tasks are never assigned; a Worker caching a Task's inputs is preferred for it; queue empties exactly once.

#### T17 — Container Contract runner + dispatch (`worker/runner.py`, wire into `server.py`/`daemon.py`)
**Prereqs:** T08, T12, T16.
**Deliverables:** Master `task_assign` → Worker `runner.run()`: `docker run` user image with `C4M_*` env per [architecture/wire-protocol.md §1](./architecture/wire-protocol.md), plus any `env={...}` from the Job spec forwarded into the user container; mount inputs/outputs, tail `progress.jsonl`, read `metrics.json`, `POST /tasks/{id}/outputs`, send `task_result`. Reject `C4M_*` overrides from the Job's `env` with a warning. Sample `examples/resnet18_hpo/` image.
**Acceptance:** **E2E smoke test** — Master + 2 **fake Workers** + a tiny Search Job (4 trials over the sample image): all trials complete, `task_result`s validated, results retrievable. Job spec `env` values land in the user container; `C4M_*` overrides are stripped. (`tests/integration/test_e2e_search.py`)

---

### P3 — Reliability

#### T18 — Heartbeat + failure controller (`master/failure.py`)
**Prereqs:** T07, T16.
**Deliverables:** heartbeat tracking; `tick()` detects 30s timeout → mark Worker `down`, re-queue its Task; retry policy (≤3 attempts); OOM classification → promote retry to a Worker with ≥2× VRAM; permanent-fail surfaced without blocking the Job.
**Acceptance:** simulated heartbeat timeout re-queues the in-flight Task; a 3×-failing Task ends `failed` while siblings continue; an OOM failure's retry targets a higher-VRAM Worker when available.

#### T19 — Quarantine + result validation
**Prereqs:** T18.
**Deliverables:** Worker failing ≥3 Tasks in 10 min → quarantined 5 min → auto-restored; `validate_result` (finite Search metric / Map output schema) — invalid counts as a Task failure.
**Acceptance:** a flaky fake Worker enters and exits quarantine on schedule; a `NaN` metric is rejected and the Task retried; a missing declared output fails validation.

#### T20 — Master persistence + restart recovery
**Prereqs:** T03, T16.
**Deliverables:** all scheduling state durable; on restart, `load_open_jobs()` resumes the queue; Workers re-heartbeat and re-attach.
**Acceptance:** kill the Master mid-Job, restart it → the Job resumes (remaining Tasks scheduled), already-collected results preserved, no duplicate top-K beyond idempotent re-runs.

#### T21 — Job cancellation
**Prereqs:** T17, T20.
**Deliverables:** `compute4me cancel JOB_ID` → `task_cancel` to Workers running that Job; SIGTERM(30s)→SIGKILL on user containers; partial Task results discarded; collected Task results returned. `cancel` prompts by default (`--yes` skips); see [wire-protocol.md §4.7](./architecture/wire-protocol.md).
**Acceptance:** cancel mid-sweep stops running containers within ~30s; `fetch` still returns the trials that had completed.

---

### P4 — Interfaces & observability

#### T22 — Operator CLI (`cli.py`)
**Prereqs:** T05, T11, T20.
**Deliverables:** the full CLI surface per [architecture/wire-protocol.md §4](./architecture/wire-protocol.md) and [ADR-0013](./adr/0013-cli-design-and-observability.md): mode commands (`serve`, `worker`), token group (`token issue/revoke/list` with `--admin` flag per [ADR-0014](./adr/0014-admin-tokens-for-submission.md)), five-command observability (`status` with `--watch`, `progress`, `logs`, `events`, `fetch`), Job lifecycle (`jobs`, `cancel`), and `version`/`help`. Rendering modes (default unicode, `--ascii`, `--slop`), exit-code policy ([error-handling.md](./architecture/error-handling.md)), env-var precedence (`C4M_*`), foreground/`-d` for daemon modes with non-TTY auto-switch to JSON-lines.
**Acceptance:** full operator loop from a clean machine: `serve` → `token issue --admin` → (worker joins) → submit → `status --watch` shows the Worker + live throughput → `fetch --out` downloads top-K. `--ascii` and `--slop` render correctly. `cancel` prompts unless `--yes`. Stdout-not-a-TTY emits JSON-lines.

#### T23 — Python submission API + SDK (`client/api.py`, `sdk/__init__.py`, `errors.py`)
**Prereqs:** T14, T17.
**Deliverables:** `Client.from_token/from_env/__init__` + `submit_search/submit_map` + `JobHandle` (`wait/status/progress/results/fetch/cancel`) + `list_jobs/get_job/fleet` per [architecture/wire-protocol.md §5](./architecture/wire-protocol.md). Submission requires an admin token ([ADR-0014](./adr/0014-admin-tokens-for-submission.md)). `env={...}` parameter forwards env vars to user containers (W&B / MLflow / HF). Search-space DSL re-exports (`loguniform`, `uniform`, `categorical`). Exception hierarchy (`Compute4MeError`/`ConnectionError`/`AuthError`/`SubmissionError`/`JobFailedError`/`TaskFailedError`/`CancelledError`) per [error-handling.md](./architecture/error-handling.md). Context-manager auto-cancel. `c4m.config/input_dir/output_dir/report/progress` sugar over the file contract.
**Acceptance:** a Search Job submitted purely via Python completes and downloads; the sample image runs identically with and without the SDK; running the image locally with the four `C4M_*` env vars reproduces a Worker run. A non-admin token raises `AuthError` on submit. `env={"WANDB_API_KEY": ...}` reaches the trial container. `with c.submit_search(...) as job: raise` triggers `job.cancel()`.

#### T24 — Observability commands + live progress display
**Prereqs:** T10, T17.
**Deliverables:** the five observability commands' implementations: `status` (Workers + Jobs snapshot; `--watch` live via `rich.live.Live`, 1s default, `--interval Ns` override; explicit numerals beside progress bars), `progress JOB_ID` (live `progress.jsonl` stream with per-Worker color and `wandb_url` surfacing), `logs <target>` (Master/Worker/Task/Job streams; `--tail`, `--since`, `-f`), `events` (logfmt structured stream; `--since`, `--type`, `--json`, `-f`), and the foreground display for `serve`/`worker` (banner + event stream + sticky status bar).
**Acceptance:** `status` reflects join/leave/quarantine within a heartbeat interval; `status --watch` refreshes in place without flicker; a running trial's `progress.jsonl` lines appear in `progress JOB_ID` with color per Worker; `events --type task_failed -f` streams only failure events; `logs task t_xxx -f` streams the user container's stdout/stderr.

---

### P5 — Eval & research harness

#### T25 — `spacesight` workload images
**Prereqs:** T17, T23.
**Deliverables:** containerized InceptionResNet exoplanet model honoring the Container Contract — a `train` image (Search/HPO) and an `infer` image (Map); Kepler light-curve dataset ingested as an Artifact.
**Acceptance:** a 32-trial Optuna sweep and a file-list Map inference both complete on the real fleet and produce sane metrics/outputs.

#### T26 — 3-arm scheduler experiment harness
**Prereqs:** T22, T25.
**Deliverables:** a runbook + scripts comparing the same HPO workload on the same heterogeneous fleet under **(a)** Ray default scheduler, **(b)** Ray with manually-labeled custom resources, **(c)** Compute4Me — reporting **makespan** and **operator effort** (lines of manual hardware config). Captures fleet profiles for reproducibility.
**Acceptance:** one command runs all three arms and emits a results table (makespan per arm, config-LoC per arm); numbers reproducible across two runs within noise.

#### T27 — Scale simulation
**Prereqs:** T16, T26.
**Deliverables:** a simulator that replays the scheduler against synthetic fleets of 10/50/200 Workers with controllable heterogeneity skew and churn; shows the advantage over round-robin/Ray-style grows with skew and scale.
**Acceptance:** produces makespan-vs-skew and makespan-vs-scale curves; the smart-pull arm dominates round-robin as skew increases; deterministic under a fixed seed.

---

## 9. Eval / Research Runbook

v0.1 is the substrate for the first research artifact: a measurement of **DL-aware, automatic-capability-discovery, heterogeneity-native scheduling** ([roadmap.md research thread #1](./roadmap.md)).

- **Centerpiece — 3-arm comparison** (T26): the same HPO workload on the same heterogeneous fleet under (a) Ray default scheduler, (b) Ray with manually-labeled custom resources, (c) Compute4Me. Report both **makespan** and **operator effort** (lines of manual hardware config). The operator-effort column is the differentiator vs Ray — Compute4Me discovers capabilities automatically.
- **Scale simulation** (T27): extend to fleets of 10/50/200 Workers to show the advantage grows with skew and scale.
- **Real workload** (T25): the `spacesight` exoplanet-detection InceptionResNet — HPO sweeps and batch inference over Kepler light curves.
- **Baselines:** round-robin, random, Ray-default, Ray-with-manual-labels.

---

## 10. Testing Strategy

A good test exercises **external behavior, not implementation detail** — given inputs to a module's interface, assert on its outputs/observable effects, so the test survives refactors. Full conventions (layout, markers, CI selection) live in [../CONTRIBUTING.md](../CONTRIBUTING.md).

Highest-value modules to test in isolation (all designed to be pure or easily faked):

- **Cost model** (T15) — pure function; assert ordering/ratios of estimates across heterogeneous Workers.
- **Scheduler** (T16) — given fixed pending Tasks + Capability Profiles, assert best-fit decisions. No network.
- **Job decomposer** (T14) — seeded sampler → assert the emitted Task configs; Map → assert shard boundaries are exhaustive and non-overlapping.
- **Token service** (T05) — issue→verify round-trips, expiry, revocation, `max_workers` enforcement.
- **Failure controller** (T18/T19) — simulate heartbeat timeouts and Task failures; assert state transitions.
- **Artifact store** (T11/T12) — content-addressing, cache-hit skipping, hash-verification failure.

**Integration smoke test** (T17): Master + 2 fake Workers running a tiny Search Job end-to-end. Greenfield repo — these tests establish the patterns. **Fakes** in `tests/fakes/`: `FakeWorker`, fake hw probes, fake container runner — so the E2E test runs on GitHub-hosted CI without GPU or Docker.

---

## 11. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Firewall/proxy mangles WSS or HTTP/2 | Workers can't join | WebSocket over 443-style WSS, not gRPC; outbound-only; HTTP fallback for artifacts. ([ADR-0007](./adr/0007-websocket-http-transport.md)) |
| Master uplink saturates as fleet grows | Slow artifact distribution | v0.1 targets small fleets; content-addressed cache means repeat data is free; P2P artifact distribution is v0.5. |
| Cost-model estimate badly wrong (>2×) | Suboptimal placement, longer makespan | Coarse model is *enough to beat round-robin*; smart-pull self-corrects (free Workers pull more); calibration is v0.2. |
| Flaky volunteer (Ali closes laptop) | Task lost | 30s heartbeat timeout → re-queue; ≤3 retries; quarantine. Mid-Task checkpointing deferred to v0.3. |
| Buggy Worker returns garbage metrics | Corrupt sweep results | `validate_result` (finite/schema); not adversarial defense (Byzantine is out of scope). |
| Token leaked | Unwanted Worker joins | TTL (default 30d), `max_workers` cap, in-memory revocation. Closed-membership only. ([ADR-0002](./adr/0002-closed-membership-rooms.md)) |
| Master crash mid-Job | Lost run | SQLite persistence + restart recovery (T20). |
| Model doesn't fit one GPU | Out of v0.1 scope | Explicitly excluded ([ADR-0004](./adr/0004-big-models-out-of-scope.md)); pipeline parallelism is v0.6/v1.0. |

---

## 12. Acceptance Criteria (v0.1 "done")

v0.1 is complete when:

1. `docker run compute4me serve --room R` brings up a Master; `compute4me token issue` prints a usable token.
2. `docker run -e C4M_MASTER=... -e C4M_TOKEN=... compute4me worker` joins from behind a NAT with **no inbound ports / SSH / firewall config**; the Master shows the Worker's Capability Profile.
3. A single `max_workers=4` token admits exactly four Workers and refuses the fifth.
4. A Search Job (Optuna and raw-list) and a Map Job (whole / index-range / file-list) each run end-to-end across ≥2 heterogeneous Workers and return collected results.
5. The Scheduler demonstrably gives the faster Worker the heavier Tasks and never places a Task on a Worker without enough VRAM (asserted by the scheduler unit tests + observed on the real fleet).
6. A Worker that drops mid-Task is detected within ~30s and its Task re-queued; a 3×-failing Task is surfaced without blocking the Job; a flaky Worker is quarantined then restored.
7. Killing and restarting the Master resumes the running Job from persisted state.
8. `compute4me cancel` stops a running Job and still returns results collected so far.
9. The user model image runs unmodified (no `import compute4me`) and reproduces locally with the four `C4M_*` env vars.
10. The 3-arm scheduler experiment (T26) runs and emits a makespan + operator-effort table.

---

## 13. Out of Scope (v0.1)

Deferred to later milestones (full registry in [roadmap.md](./roadmap.md)):

- **v0.2 — Scheduler maturity:** multi-Job concurrency + fairness, real-time-throughput rebalancing, dynamic re-sharding, calibrated cost model.
- **v0.3 — Fabric ergonomics & robustness:** mid-Task checkpointing, B2 live-RPC sidecar, streaming partial artifact transfer, external result sinks, disk-cache GC, custom sharders, Master-mediated image distribution, additional Samplers.
- **v0.4 — Distributed data-parallel training:** parameter-server aggregation, gradient compression, capability-weighted aggregation, async-for-stragglers, gradient-norm sanity checks.
- **v0.5 — WAN:** local SGD / DiLoCo, async-with-staleness, direct worker-to-worker links, P2P artifact distribution.
- **v0.6 — Big-model inference:** the Pipeline Job primitive.
- **v1.0 — Big-model training:** master-orchestrated pipeline parallelism (the marquee research contribution).
- **Never in this design (separate mode if ever):** open/public Rooms, Byzantine-robust aggregation, cryptographic privacy, hierarchical multi-tier aggregation, Master HA.

---

## 14. Further Notes

- **Eval / research framing.** v0.1 is the substrate for the first research artifact: a measurement of DL-aware, automatic-capability-discovery, heterogeneity-native scheduling. The centerpiece is the 3-arm comparison (§9) reporting makespan and operator effort, plus a simulation arm at 10/50/200 Workers.
- **Real workload.** The exoplanet-detection InceptionResNet model (the operator's `spacesight` work) is the concrete eval workload — HPO sweeps and batch inference over Kepler light curves.
- **Audience.** Compute4Me targets researchers with lab GPUs + friends' consumer GPUs — the majority of ML work that fits on one card. It deliberately does not target the train-a-70B-model audience, who have cloud/supercomputer options.

---

*End of PRD (v0.1).*
