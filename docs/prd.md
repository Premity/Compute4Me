# Compute4Me PRD — v0.1

| | |
|---|---|
| **Milestone** | v0.1 (in development) |
| **Status** | Accepted; the single source of truth for *what* v0.1 is and *when it is done* |
| **Last revised** | 2026-11-10 (planning rewrite: task specs moved to [plan.md](./plan.md) and [tasks/](./tasks/README.md); NFRs and open items added) |
| **Progress** | P0 done; P1 in progress (T01–T09 merged). Live status: [plan.md](./plan.md#task-index) |

> **What this document is for.** It says **what** v0.1 builds, **why**, and **what counts as done**. **How and in what order** is in [plan.md](./plan.md) and the task cards in [tasks/](./tasks/README.md). Terminology is in [context.md](./context.md), durable structure in [architecture/](./architecture/README.md), the reasons for structural choices in [adr/](./adr/README.md), and what comes after v0.1 in [roadmap.md](./roadmap.md). If this PRD and another document disagree, **this PRD wins**; fix the other document in a PR.
>
> **Lifecycle.** When v0.1 ships (`v0.1.0` tag), this file is archived to `docs/archive/prd-v0.1.md` and rewritten for v0.2.

---

## 1. Vision and scope

### 1.1 Problem

An ML researcher has limited, scattered compute: a handful of lab GPU machines, a CPU box, and the occasional GPU borrowed from someone nearby. They want to use all of it together to get deep-learning work done faster: running many model variants, scoring large datasets, sweeping hyperparameters.

The existing tools don't fit:

- **Ray / Horovod / PyTorch DDP** assume a cluster you administer: nodes you provision, SSH into, configure firewalls for, and add by hand. Getting a friend's machine, or even your own lab machines on a segmented LAN where they can't reach each other, into a job is painful.
- **Hivemind / SWARM** can pool internet volunteers, but force the model into their decentralised Mixture-of-Experts framework. That is useless for a standard model such as an InceptionResNet exoplanet detector.
- All of them treat heterogeneous hardware as interchangeable. They don't know an RTX 3070 is several times faster than a GTX 1060, or that one machine already has the dataset cached.

The goal: a machine joins with **one `docker run`**, brings a **standard containerised model** (no framework rewrite), and the system is **smart about a heterogeneous, firewall-constrained fleet**.

### 1.2 Solution

**Compute4Me** is a Docker-native, master-orchestrated compute **Fabric** for embarrassingly parallel deep-learning work on heterogeneous, firewall-constrained machines. [architecture/overview.md](./architecture/overview.md) has the one-paragraph description, the diagram and the end-to-end flow.

v0.1 makes a lab plus a friend's GPU usefully poolable for hyperparameter search and batch inference, and doubles as the substrate for a research contribution: **automatic, DL-aware, heterogeneity-native scheduling for containerised volunteer fabrics** ([research/novelty.md](./research/novelty.md)).

### 1.3 v0.1 scope (locked)

- **Two Job primitives:** Map and Search ([ADR-0009](./adr/0009-map-search-primitives.md)). No distributed *training* (v0.4).
- **Closed-membership Rooms** via signed Invite Tokens; trust established out of band ([ADR-0002](./adr/0002-closed-membership-rooms.md)); an admin capability for Job submission ([ADR-0014](./adr/0014-admin-tokens-for-submission.md)). No Byzantine defences.
- **Models that fit on a single Worker GPU** ([ADR-0004](./adr/0004-big-models-out-of-scope.md)).
- **One Job at a time per Room**, FIFO. Multi-Job concurrency is v0.2.
- **Master on the data plane, Workers outbound-only** ([ADR-0003](./adr/0003-master-on-data-plane.md)); the Master URL is passed separately from the token ([ADR-0015](./adr/0015-master-url-separate-from-token.md)).
- **Measured capability:** each Worker runs a fixed throughput benchmark at join, as its own container ([ADR-0016](./adr/0016-benchmark-runs-as-a-container.md)). Real-time throughput is collected for monitoring only.
- **Container Contract:** env-vars-in, files-out, plus `env={...}` pass-through for W&B / MLflow / TensorBoard ([ADR-0006](./adr/0006-black-box-container-contract.md), [wire-protocol.md §1](./architecture/wire-protocol.md#1-container-contract-masterworker--user-image)).
- **CLI:** flat, one nested `token` group, five observability commands, foreground by default ([ADR-0013](./adr/0013-cli-design-and-observability.md)), built on structured logs and a persisted event stream ([ADR-0018](./adr/0018-logging-and-events.md)).

### 1.4 Audience

Researchers with lab GPUs and friends' consumer GPUs: the majority of ML work that fits on one card. Compute4Me deliberately does **not** target people training 70B-parameter models, who have cloud and supercomputer options.

### 1.5 Out of scope (summary)

Full list in §14 and [roadmap.md](./roadmap.md). Headlines: distributed training (v0.4), WAN sync regimes (v0.5), big-model inference and training (v0.6, v1.0). **Never in this design:** open/public Rooms, Byzantine-robust aggregation, cryptographic privacy, hierarchical aggregation, Master HA.

---

## 2. Personas and eval workload

### 2.1 Hamda: operator and researcher (primary)

ML researcher. Owns four lab GPU machines (mixed, e.g. RTX 3070, RTX 3060, 2× GTX 1060) on a segmented LAN, plus a CPU box, plus a small VPS to host the Master. Runs hyperparameter sweeps and batch inference for the `spacesight` exoplanet-detection work. Wants one command to pool everything, smart placement, and a clean results download. Also the paper author, so each eval run must double as an experiment record ([ADR-0019](./adr/0019-experiment-run-records.md)).

### 2.2 Ali: contributor (secondary)

A friend with an RTX 3070 at home behind a NAT. Will run a container if it is *one command and touches nothing else on the machine*. Will not configure SSH, port forwarding or a firewall rule. Trusted (the operator vouches for him), but the machine is flaky: the laptop may close mid-run.

### 2.3 The lab fleet: contributors (batch)

Four lab machines admitted under one `max_workers=4` token. They can reach the VPS Master but not each other: exactly the case that breaks Ray's peer-to-peer assumptions.

### 2.4 Eval workload: `spacesight`

The **InceptionResNet exoplanet detector** over Kepler light curves:

- **Search Job:** an Optuna sweep (~32–64 trials) over learning rate, dropout and augmentation strength.
- **Map Job:** batch inference over a large light-curve dataset, sharded by file list.

This is also the centrepiece of the research eval (§9).

---

## 3. End-to-end flow and lifecycle states

[architecture/overview.md](./architecture/overview.md#end-to-end-flow) traces operator start-up → token issue → Worker join → Job submit → schedule → run → collect, with sequence diagrams.

| Object | States |
|---|---|
| **Worker** | `joining → idle → busy → (down \| quarantined) → idle` |
| **Task** | `pending → assigned → running → (succeeded \| failed)`; a failed Task with attempts left returns to `pending` |
| **Job** | `queued → running → (completed \| cancelled)`; completes when every Task is terminal |

State diagrams: [overview.md §Lifecycle states](./architecture/overview.md#lifecycle-states).

---

## 4. Architecture (reference only)

The architecture docs are **durable across versions**; this PRD links rather than duplicates.

| Doc | Covers |
|---|---|
| [overview.md](./architecture/overview.md) | Components, network model, end-to-end flow, state machines |
| [data-model.md](./architecture/data-model.md) | SQLite schema, Pydantic models |
| [modules.md](./architecture/modules.md) | Interface of every module |
| [wire-protocol.md](./architecture/wire-protocol.md) | Container Contract, control channel, artifact channel, CLI, Python API |
| [error-handling.md](./architecture/error-handling.md) | Error format, exit codes, exception hierarchy |
| [deployment.md](./architecture/deployment.md), [operations.md](./architecture/operations.md) | Running and maintaining a deployment |
| [test-map.md](./architecture/test-map.md) | Which checks run where |

---

## 5. Repository layout

```text
Compute4Me/
├── README.md  CONTRIBUTING.md  CHANGELOG.md  SECURITY.md  CLAUDE.md  LICENSE
├── pyproject.toml  uv.lock  .python-version  Makefile
├── Dockerfile                  # one image: `serve` and `worker`
├── docker-compose.dev.yml      # Master + Worker for the join smoke test
├── bench/                      # the benchmark image (T30, ADR-0016)
├── src/compute4me/
│   ├── __init__.py  types.py  errors.py  cli.py  log.py  events.py
│   ├── proto/messages.py       # control-channel messages
│   ├── master/                 # server, tokens, state, artifacts, decomposer, cost_model,
│   │                           #   scheduler, failure, samplers/
│   ├── worker/                 # daemon, profiler, docker, runner, cache
│   ├── client/api.py           # Python submission API
│   └── sdk/__init__.py         # optional sugar for user containers
├── tests/                      # unit/, integration/, fakes/, conftest.py, INDEX.md
├── examples/                   # sample user images (Container Contract)
├── scripts/                    # check_md_links.py, smoke/, manual/
└── docs/                       # prd, plan, tasks/, context, roadmap, architecture/, adr/,
                                #   background/, research/, archive/, style-guide
```

Files that don't exist yet are created by the task named in [plan.md](./plan.md).

---

## 6. User stories

### Joining and membership

1. As an operator, I want to start a Master and open a named Room, so that Workers have something to join.
2. As an operator, I want to issue an Invite Token for a Room, so that I can admit a specific contributor.
3. As an operator, I want to set `max_workers` on a token (or leave it unlimited), so that I can cap how many concurrent Workers a token admits.
4. As an operator, I want tokens to expire (default 30 days), so that a leaked or forgotten token doesn't stay valid forever.
5. As an operator, I want to issue several tokens for the same Room with different limits, so that I can give my lab a 4-Worker token and a guest a single-use one.
6. As an operator, I want to revoke a token, so that I can remove a contributor without disrupting the others.
7. As a contributor, I want to join a Room with a single `docker run`, so that I don't have to configure SSH, firewalls or open ports.
8. As a contributor, I want my machine to connect outbound only, so that I can contribute from behind a NAT or corporate firewall.
9. As a contributor, I want to run one container per GPU, so that I can contribute several cards from one host.
10. As a contributor, I want the Master's identity verified automatically when I join, so that my token can't be replayed against an impostor Master.
11. As a contributor, I want one command that tells me whether my host can be a Worker (Docker, GPU, network), so that I find problems before joining. *(Added 2026-11-10, T33.)*

### Capability discovery

12. As the Scheduler, I want each Worker to advertise GPU model, total/free VRAM, CPU cores and RAM on join, so that I can filter out Workers that can't run a Task.
13. As the Scheduler, I want each Worker to run a fixed throughput benchmark on join, so that I have a comparable speed estimate before any real work runs.
14. As the Scheduler, I want each Worker to report which datasets it already has cached, so that I can prefer placing data-heavy Tasks where the data already is.
15. As the Scheduler, I want each Worker's free disk and bandwidth/latency to the Master, so that I avoid sending huge datasets to Workers that can't hold or fetch them quickly.
16. As an operator, I want Workers to refresh their profile periodically, so that the Scheduler reacts to changing free VRAM.

### Submitting and running work

17. As a researcher, I want to submit a Search Job describing a model image, a search space and a metric, so that the Fabric runs my sweep across the Room.
18. As a researcher, I want to express the search space with Optuna-style distributions, so that I get TPE sampling without learning a new DSL.
19. As a researcher, I want to pass a plain list of configs instead, so that I can run a simple grid.
20. As a researcher, I want to submit a Map Job describing a model image, an input dataset and a shard strategy, so that the Fabric runs inference, evaluation or preprocessing over shards in parallel.
21. As a researcher, I want to keep only the top-K results of a Search, so that I'm not drowned in artifacts from a 64-trial sweep.
22. As a researcher, I want to state a Task's resource needs (VRAM, GPU, relative size), so that the Scheduler can place it sensibly. *(Added 2026-11-10, T14.)*
23. As a researcher, I want my container to receive its config and inputs via env vars and mounted directories, so that I don't import any Compute4Me library.
24. As a researcher, I want my container to report results by writing files, so that the contract is debuggable and language-agnostic.
25. As a researcher, I want an optional small SDK to read config and report metrics, so that I get ergonomics without being forced into them.
26. As a researcher, I want to run my container locally with the same env vars, so that I can reproduce exactly what a Worker does.

### Scheduling behaviour

27. As the Scheduler, I want to hand a free Worker the best-fit eligible Task rather than the next in line, so that fast Workers get the heaviest Tasks.
28. As the Scheduler, I want to estimate each Task's runtime per Worker from a coarse cost model, so that I can shorten overall makespan on a heterogeneous fleet.
29. As the Scheduler, I want to prefer Workers that already cache a Task's inputs, so that I minimise data transfer.
30. As the Scheduler, I want to refuse to place a Task on a Worker without enough VRAM, so that the model fits.
31. As an operator, I want one Job to run at a time per Room with others queued FIFO, so that v0.1 behaviour is predictable.
32. As a researcher, I want a fast Worker to naturally pull more Tasks than a slow one, so that the fleet self-balances.

### Artifacts

33. As a researcher, I want to push a dataset to the Master from my laptop or from a URL, so that the Fabric can distribute it.
34. As the Fabric, I want artifacts identified by content hash, so that Workers can cache, dedup and verify them.
35. As a Worker, I want to fetch only the shard I'm assigned, so that I don't download an 80 GB dataset to process 1/20th of it.
36. As a Worker, I want to skip downloading an artifact I already have, so that repeated Jobs on the same data are fast.
37. As a researcher, I want to download my Job's results via the CLI, so that I can collect metrics and checkpoints.

### Reliability

38. As an operator, I want a Worker that stops responding to be detected within ~30 s and its Task re-queued, so that one machine dropping doesn't stall the Job.
39. As an operator, I want a failed Task retried up to 3 times, so that transient failures self-heal.
40. As the Scheduler, I want an OOM-failed Task retried on a Worker with more VRAM, so that a too-big trial lands somewhere it fits.
41. As an operator, I want a permanently failed Task surfaced without blocking the rest of the Job, so that one bad trial doesn't sink a sweep.
42. As an operator, I want a Worker that fails repeatedly to be quarantined briefly and then restored, so that a flaky machine doesn't poison the run but isn't lost.
43. As the Fabric, I want returned metrics validated as finite and outputs checked against what was declared, so that buggy Workers' garbage is caught.
44. As an operator, I want the Master to persist its state, so that restarting it resumes the Job instead of losing it.
45. As a researcher, I want to cancel a running Job and still get the results collected so far.

### Observability

46. As an operator, I want a status view of the Room (connected Workers, profiles, live throughput, quarantine events), so that I can see what's happening.
47. As a researcher, I want live progress and logs from running Tasks, so that I can watch a sweep and debug a failing trial.
48. As an operator, I want a queryable history of state changes (joins, assignments, failures), so that I can explain what happened after the fact. *(Added 2026-11-10, ADR-0018.)*

---

## 7. Decisions (ADR index)

All in [adr/](./adr/README.md). Headlines:

- Closed-membership Rooms via signed Invite Tokens ([0002](./adr/0002-closed-membership-rooms.md)); admin tokens for submission ([0014](./adr/0014-admin-tokens-for-submission.md)).
- Master on the data plane; Workers outbound-only ([0003](./adr/0003-master-on-data-plane.md)); flat single Master ([0001](./adr/0001-flat-master-not-hierarchical.md)).
- Our own orchestration, not Ray ([0005](./adr/0005-roll-our-own-orchestration.md)); two primitives, Map and Search ([0009](./adr/0009-map-search-primitives.md)).
- Black-box Container Contract ([0006](./adr/0006-black-box-container-contract.md)); smart-pull scheduling ([0008](./adr/0008-smart-pull-scheduling.md)); Optuna behind a Sampler interface ([0010](./adr/0010-wrap-optuna.md)).
- WebSocket control + HTTP artifacts ([0007](./adr/0007-websocket-http-transport.md)); TLS by fingerprint pinning ([0011](./adr/0011-tls-fingerprint-in-token.md)); content-addressed artifacts ([0012](./adr/0012-content-addressed-artifacts.md)); Master URL separate from the token ([0015](./adr/0015-master-url-separate-from-token.md)).
- Models must fit one GPU ([0004](./adr/0004-big-models-out-of-scope.md)); CLI and observability split ([0013](./adr/0013-cli-design-and-observability.md)).
- Benchmark as its own container ([0016](./adr/0016-benchmark-runs-as-a-container.md)); Python toolchain ([0017](./adr/0017-python-toolchain.md)); logging and events ([0018](./adr/0018-logging-and-events.md)); experiment run records ([0019](./adr/0019-experiment-run-records.md)); the Docker image as the verification surface ([0020](./adr/0020-docker-is-the-verification-surface.md)).

---

## 8. Delivery plan

The work is split into tasks T01–T33 across phases P0–P5. **The task index, dependency graph, Definition of Done and stubs are in [plan.md](./plan.md); the full specification of each task is its card in [tasks/](./tasks/README.md).** This PRD no longer holds per-task detail (moved 2026-11-10; the earlier 2–4-line entries left too much to be settled mid-PR).

| Phase | Delivers | Tracer bullet |
|---|---|---|
| P0 Scaffolding ✅ | Repo, types, state store, wire models | `docker build`; `compute4me --help` |
| P1 Control-plane bootstrap | Tokens, TLS, transport, join, profiling, tooling, logging, benchmark container, runnable CLI, bandwidth | A Worker container joins a Master container in CI |
| P2 Job execution core | Artifacts, shards, samplers, decomposer, cost model, scheduler, runner | A 4-trial Search completes end to end |
| P3 Reliability | Failure handling, quarantine, recovery, cancellation | Kill a Worker and the Master mid-Job; the Job completes |
| P4 Interfaces & observability | Full CLI, Python API + SDK, observability commands, host check | The §13 operator loop from a clean machine |
| P5 Eval & research harness | Run records, `spacesight` images, 3-arm experiment, scale simulation | The makespan + operator-effort table from registered runs |

---

## 9. Eval / research runbook

v0.1 is the substrate for the first research artifact: a measurement of **DL-aware, automatic-capability-discovery, heterogeneity-native scheduling** ([roadmap.md research thread 1](./roadmap.md#research-threads-papers-not-just-features)).

- **Centrepiece, the 3-arm comparison (T26):** the same Search workload on the same heterogeneous fleet under (a) Ray's default scheduler, (b) Ray with manually labelled custom resources, (c) Compute4Me. Report **makespan** and **operator effort** (lines of manual hardware configuration). The operator-effort column is the differentiator: Compute4Me discovers capabilities itself.
- **Scale simulation (T27):** fleets of 10/50/200 Workers with controllable heterogeneity skew and churn, to show the advantage grows with skew and scale.
- **Real workload (T25):** `spacesight` Search and Map Jobs.
- **Baselines:** round-robin, random, greedy pull, Ray default, Ray with manual labels.
- **Records:** every eval run is an auto-named run folder with config, git state, environment, a **fleet snapshot** and logs; reported numbers come only from runs listed in `results/registry.yaml`, and dirty-tree runs can't be registered ([ADR-0019](./adr/0019-experiment-run-records.md), T32).

---

## 10. Testing strategy

A good test exercises **external behaviour, not implementation detail**: given inputs to a module's interface, assert on outputs and observable effects. Conventions (layout, markers, fakes) are in [CONTRIBUTING.md](../CONTRIBUTING.md#tests); where each check runs is in [test-map.md](./architecture/test-map.md).

| Layer | What | Where it runs |
|---|---|---|
| Unit | Pure modules: cost model, scheduler, decomposer, samplers, tokens, failure controller, artifact store, profiler with fake probes | CI, every PR |
| Integration | Real Master and Worker objects over localhost WSS/HTTP, with fake runners (`tests/fakes/`) | CI, every PR |
| Image | Build, `--help`, `version`; compose join smoke (a Master container and a Worker container) | CI, every PR ([ADR-0020](./adr/0020-docker-is-the-verification-surface.md)) |
| Docker / GPU | Real containers, bench image, real-Docker E2E (`requires_docker`, `requires_gpu`) | Locally, before the PR is marked ready |
| Fleet | Real NAT'd contributor, real GPUs, real VPS | By hand, tracked on the "Needs the real fleet" issue |

---

## 11. Non-functional requirements

| ID | Requirement | Checked by |
|---|---|---|
| NFR-01 **Outbound-only Workers** | A Worker needs no inbound port, SSH or firewall change; only outbound TCP to the Master's port. | Compose smoke; fleet check |
| NFR-02 **One-command join** | Joining is one `docker run` with `C4M_MASTER` and `C4M_TOKEN` (plus the documented volume and socket mounts). | README walkthrough, T31 |
| NFR-03 **Lean Worker image** | The Worker image contains no ML framework; ML code runs only in user and bench containers. | Import-hygiene test, image size noted in CHANGELOG |
| NFR-04 **Reproducible builds** | Python 3.13 and every dependency pinned through `uv.lock`; one version per dev tool. | [ADR-0017](./adr/0017-python-toolchain.md), CI |
| NFR-05 **Secrets** | Tokens, signing keys and Job `env` values never appear in logs, events, git or error messages; key files are mode `0600`. | Redaction tests (T29), gitleaks (T28) |
| NFR-06 **Observability** | Every state transition is an event; every process logs to stderr in human or JSON form; nothing fails silently. | T29 tests; review checklist |
| NFR-07 **Determinism** | Samplers, decomposition and scheduling decisions are deterministic under a fixed seed and inputs. | Unit tests (T13, T14, T16); T27 |
| NFR-08 **Failure detection** | A dead Worker is detected within ~30 s (10 s heartbeat, 30 s timeout). | T18 tests |
| NFR-09 **Durability** | Master state survives a restart; a Job resumes. | T20 tests |
| NFR-10 **Verified in the image** | Every task is verified against the built image; CI builds and runs it on every PR. | [ADR-0020](./adr/0020-docker-is-the-verification-surface.md) |
| NFR-11 **Traceable results** | Every reported number traces to a clean run folder listed in the registry. | [ADR-0019](./adr/0019-experiment-run-records.md), T32 |

---

## 12. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| A firewall or proxy mangles WSS or HTTP/2 | Workers can't join | WebSocket over TLS on one port, not gRPC ([ADR-0007](./adr/0007-websocket-http-transport.md)); port decision in T11 |
| User containers can't see their inputs (Docker-outside-of-Docker paths) | Every Task fails or runs on empty input | Decided and tested in T17 before any real Job |
| The bench image is too big for slow contributor links | Slow first join | Pull once per host; join never waits on it ([ADR-0016](./adr/0016-benchmark-runs-as-a-container.md)) |
| The Master's uplink saturates as the fleet grows | Slow artifact distribution | Small fleets in v0.1; content-addressed caching; P2P in v0.5 |
| The cost model is badly wrong (> 2×) | Worse placement | Pull self-corrects; calibration in v0.2; error recorded from T26 data |
| A flaky contributor drops mid-Task | Task lost | 30 s detection, ≤ 3 retries, quarantine; mid-Task checkpointing in v0.3 |
| A buggy Worker returns garbage | Corrupt sweep | `validate_result` (finite metric, declared outputs) |
| A token or signing key leaks (the repo is public) | Unwanted Workers or submissions | TTL, `max_workers`, revocation; redaction; gitleaks; key files `0600` |
| SQLite contention between `serve` and `docker exec … token issue` | "database is locked" | WAL + busy timeout (T31) |
| Master crash mid-Job | Lost run | SQLite persistence and recovery (T20) |
| A model doesn't fit one GPU | Out of scope | Excluded ([ADR-0004](./adr/0004-big-models-out-of-scope.md)) |
| Tooling drift (Python, tool versions, hooks) | "Works locally, fails in CI" detours | [ADR-0017](./adr/0017-python-toolchain.md), T28 |

---

## 13. Acceptance criteria (v0.1 "done")

v0.1 is complete when every criterion holds, each shown on the real fleet unless marked *(CI)*.

| # | Criterion | Delivered by |
|---|---|---|
| 1 | `docker run … serve --room R` brings up a Master; `compute4me token issue` prints a usable token. *(CI: compose smoke)* | T31, T22 |
| 2 | `docker run -e C4M_MASTER=… -e C4M_TOKEN=… … worker` joins from behind a NAT with no inbound ports, SSH or firewall changes; the Master shows the Worker's Capability Profile. | T31, T10, T33 |
| 3 | A `max_workers=4` token admits exactly four Workers and refuses the fifth. | T05, T31 |
| 4 | A Search Job (Optuna and raw list) and a Map Job (whole, index-range, file-list) each run end to end across ≥ 2 heterogeneous Workers and return collected results. | T11–T17, T23 |
| 5 | The Scheduler gives the faster Worker the heavier Tasks and never places a Task on a Worker without enough VRAM (unit tests plus the real fleet). | T15, T16 |
| 6 | A Worker that drops mid-Task is detected within ~30 s and its Task re-queued; a 3×-failing Task is surfaced without blocking the Job; a flaky Worker is quarantined and restored. | T18, T19 |
| 7 | Killing and restarting the Master resumes the running Job from persisted state. | T20 |
| 8 | `compute4me cancel` stops a running Job and still returns the results collected so far. | T21 |
| 9 | The user model image runs unmodified (no `import compute4me`) and reproduces locally with the four `C4M_*` env vars. | T17, T23 |
| 10 | The 3-arm scheduler experiment runs and emits a makespan + operator-effort table from registered runs. | T26 (with T32) |

---

## 14. Out of scope (v0.1)

Deferred (full registry in [roadmap.md](./roadmap.md)):

- **v0.2, scheduler maturity:** multi-Job concurrency and fairness, real-time-throughput rebalancing, dynamic re-sharding, a calibrated cost model.
- **v0.3, ergonomics and robustness:** mid-Task checkpointing, the B2 live-RPC sidecar, streaming partial transfer, external result sinks, cache GC, custom sharders, Master-mediated image distribution, more Samplers, getting-started docs.
- **v0.4, distributed data-parallel training.** **v0.5, WAN.** **v0.6, big-model inference.** **v1.0, big-model training.**
- **Never in this design** (a separate mode if ever): open/public Rooms, Byzantine-robust aggregation, cryptographic privacy, hierarchical aggregation, Master HA.

---

## 15. Open items

Decided later by the named task; options and recommendations are in each card's **Decide first** section. The current list is maintained in [plan.md §Open items](./plan.md#open-items).

---

## 16. Document map

| Doc | Purpose |
|---|---|
| [plan.md](./plan.md) | Phases, task index, dependency graph, Definition of Done, stubs |
| [tasks/](./tasks/README.md) | Full task cards |
| [context.md](./context.md) | Canonical glossary |
| [architecture/](./architecture/README.md) | Durable structure: overview, data, modules, wire, errors, deployment, operations, test map |
| [adr/](./adr/README.md) | Architecture decisions |
| [roadmap.md](./roadmap.md) | What comes after v0.1 |
| [background/challenges-faced.md](./background/challenges-faced.md) | Real problems hit and how they were solved |
| [research/](./research/README.md) | Related work and positioning |
| [style-guide.md](./style-guide.md) | Code and docs conventions |
| [../CONTRIBUTING.md](../CONTRIBUTING.md) | How work is done: branches, PRs, tests, Docker verification |
| [../CLAUDE.md](../CLAUDE.md) | Short guide for AI coding assistants |
