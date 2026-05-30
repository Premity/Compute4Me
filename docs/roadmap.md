# Compute4Me Roadmap & Deferred-Features Registry

Everything deliberately pushed out of v0.1 during design, so nothing is lost. Each entry: **what**, **why deferred**, **why it matters**. v0.1 scope and rationale live in [context.md](./context.md) and [adr/](./adr/).

## The version ladder

| Milestone | Theme | Risk |
|---|---|---|
| **v0.1** | Map + Search primitives, small models, LAN. *Daily-useful tool + the scheduler paper.* | — |
| **v0.2** | Scheduler maturity & concurrency | Med |
| **v0.3** | Fabric ergonomics & robustness | Low |
| **v0.4** | Distributed data-parallel training (the data-plane paradigm) | High |
| **v0.5** | WAN: less-frequent sync, P2P, NAT traversal | Med |
| **v0.6** | Big-model inference (Pipeline Job) | Med |
| **v1.0** | Big-model training (master-orchestrated pipeline parallelism — marquee research) | High |

Sequencing logic: front-load the lower-risk, immediately-useful work (v0.2 completes the scheduler paper; v0.3 makes it a real daily tool), give the heavy data-plane build its own focused milestone (v0.4) rather than burying it in a polish release, then the dependency-ordered tail. Hard constraints respected: **WAN (v0.5) depends on training (v0.4)**; **big-model training (v1.0) depends on big-model inference (v0.6)** per [ADR-0004](./adr/0004-big-models-out-of-scope.md).

---

## v0.2 — Scheduler maturity & concurrency

*Theme: make the scheduler genuinely smart and multi-tenant. This milestone completes the strongest form of the v0.1 scheduler paper.*

- **Multi-Job concurrency + cross-Job fairness/preemption** — more than one Job running per Room at once. *v0.1 runs one Job at a time, FIFO, to keep a single Task queue.* Needed once you submit several HPO sweeps at once.
- **Real-time-throughput-based mid-Job re-balancing** — act on the live samples/sec EMA, not just the join-time micro-benchmark. *v0.1 collects this signal but only for monitoring.* Catches thermal throttling / contention drift.
- **Dynamic re-sharding** — reassign data shards mid-Job when a Worker's measured throughput diverges from estimate. *Deferred with re-balancing.* Recovers from bad initial cost-model estimates.
- **Calibrated cost model** — per-architecture profiling, regression on config features, replacing the coarse flops-÷-throughput estimate. *v0.1 is deliberately coarse (~2× is enough to beat round-robin).* Sharper placement; strengthens the novelty story.

---

## v0.3 — Fabric ergonomics & robustness

*Theme: make the embarrassingly-parallel fabric pleasant and reliable for daily use. Mostly independent, parallelizable, low-risk items.*

- **Mid-Task checkpointing** — a dying Worker doesn't lose in-progress compute; Task resumes from a checkpoint. *v0.1 restarts the Task from scratch on failure.* Big win for long HPO/inference Tasks.
- **B2 sidecar / live-RPC container interface** — a Compute4Me agent alongside the user's container exposing local RPC for streaming metrics and mid-Task checkpoint coordination, richer than tailing `progress.jsonl`. *v0.1 uses the black-box env-vars-in/files-out contract (B1).* The powerful complement to B1 — live observability and coordination without breaking the model-agnostic promise. **(Flagged by user as a must-not-lose idea.)**
- **Streaming partial artifact transfer** — Worker starts a Task before the full dataset arrives. *v0.1 is whole-file.* Faster Task start on big datasets.
- **External result sinks** — Workers write results directly to S3 / user fs over reverse tunnel, not just POST-to-Master. *v0.1 is Master-centric to match the firewall model.* Avoids funneling all results through the Master.
- **Disk-cache GC / LRU eviction** on Workers. *v0.1 ships a max-cache-size config only.* Prevents long-lived Workers from filling their disks.
- **Custom sharders** beyond whole / index-range / file-list. *v0.1 covers the common cases.* Arbitrary user-defined sharding logic.
- **Master-mediated container image distribution** — private-registry auth, air-gapped Workers. *v0.1 assumes a public/accessible registry (Docker Hub/GHCR).* Lets Workers run private images without registry credentials.
- **Pluggable Sampler implementations** beyond Optuna (Hyperopt, scikit-optimize, DEAP). *v0.1 ships the Sampler interface with only the Optuna impl.* Cheap to add once someone needs a different sampler.
- **Getting-started tutorial + how-to docs.** A proper `docs/getting-started.md` walking through a first end-to-end run, plus per-topic how-tos (HPO sweep, batch inference, debugging a failing trial). *v0.1 has only the README quick-start by persona.* Premature before v0.1 ships — would document features that don't exist yet.

---

## v0.4 — Distributed data-parallel training (the big paradigm)

*Theme: add gradient-synchronized training as a new primitive on the Master-as-data-plane substrate. The single biggest, riskiest chunk — its own focused milestone.*

- **Distributed data-parallel training** via parameter-server-shaped aggregation on the Master. *Deferred because v0.1–v0.3's Map+Search are embarrassingly parallel and need no gradient sync.* The whole reason we designed the master-on-data-plane model ([ADR-0003](./adr/0003-master-on-data-plane.md)).
- **Gradient compression** (quantization, sparsification) before shipping to Master. *Deferred with the data plane.* Cuts Master uplink pressure — the steady-state bottleneck.
- **Capability-weighted aggregation** — down-weight slow/unreliable Workers' gradient contributions. *Deferred with the data plane.* Heterogeneity-native convergence; a research angle of its own.
- **Async aggregation option for stragglers** — Master proceeds without waiting for the slowest Worker, with staleness handling. *Deferred with the data plane.* Keeps fast Workers from idling on a slow one.
- **Gradient-norm sanity checks** — bug-level defense (drop NaN/exploding gradients) for closed-membership rooms. *Deferred because pre-v0.4 has no gradients.* The non-Byzantine defense promised in [ADR-0002](./adr/0002-closed-membership-rooms.md).

---

## v0.5 — WAN

*Theme: extend training to high-latency, low-bandwidth, churny internet links. Depends on v0.4.*

- **Local SGD / DiLoCo** — Workers do K local optimizer steps, sync model weights every K. *Deferred until WAN is the target.* The WAN-appropriate sync regime (frequent every-step sync is unusable at 100ms RTT). Same master-aggregator architecture, dialed-down frequency.
- **Async SGD with bounded staleness** — Workers send updates when ready; Master applies with staleness-aware LR scaling. *Deferred with WAN.* Alternative to local SGD for churny WAN fleets.
- **Direct worker-to-worker links / gossip aggregation** — peers average directly when connectivity allows, falling back to Master relay. *Pre-v0.5 is Master-relay only.* Relieves Master uplink when it saturates; behind the same transport abstraction ([ADR-0003](./adr/0003-master-on-data-plane.md)).
- **P2P artifact distribution** (BitTorrent-style swarm) between Workers. *Pre-v0.5 routes all transfer through Master.* Removes Master as the artifact-bandwidth bottleneck on large WAN fleets.

---

## v0.6 — Big-model inference

- **Pipeline Job primitive** — a third primitive alongside Map and Search. Each Worker hosts a contiguous range of model layers; inference requests stream through the pipeline via the Master. *Deferred because it's a new primitive and execution model.* See [ADR-0004](./adr/0004-big-models-out-of-scope.md). Activation bandwidth is tractable (~MB/request). Builds the layer-partition substrate v1.0 training reuses.

---

## v1.0 — Big-model training (marquee research)

- **Master-orchestrated pipeline parallelism over a hub topology** with heterogeneity-aware layer assignment and SWARM-style re-routing on Worker drop. *The genuinely novel, largely-unclaimed contribution* — Hivemind/SWARM do the parallelism without a master; Megatron does it with a master but on InfiniBand. The cross-over is open. See [ADR-0004](./adr/0004-big-models-out-of-scope.md).

---

## Someday / unscheduled (no version committed)

- **Hierarchical / multi-tier aggregation** — Sub-Masters per network tier. *Held as later-additive via the three rules in [ADR-0001](./adr/0001-flat-master-not-hierarchical.md).* Revisit at 50+ Workers across ≥3 network tiers.
- **Open / public Rooms** — anyone joins without an Invite Token; requires Byzantine-robust aggregation (median-of-means, Krum, trimmed mean) + reputation. *Out of scope per [ADR-0002](./adr/0002-closed-membership-rooms.md); a separate mode, not a change to the token-gated default.*
- **Cryptographic privacy** — secure aggregation, differential privacy, homomorphic encryption for untrusted-data settings. *Out of scope; the federated/private-DL research direction from the survey.*
- **Per-token resource quotas** beyond `max_workers` (e.g., per-token GPU-hour budgets), **token revocation lists**, **reputation scoring**. *v0.1 does `max_workers` + TTL + in-memory revocation.* The natural trust-model upgrade path.
- **Cloud-broker transport mode** — an optional substrate where Master and Workers communicate through a shared cloud broker (S3-style blob store + a message queue / pub-sub) instead of a direct connection: the Master writes Task assignments and Artifacts to the broker; Workers poll it. *Sidesteps the "Master must be reachable from every Worker" requirement entirely — no VPS, no public IP, no NAT traversal, both sides outbound-only to a public cloud endpoint.* Deferred because it's a serious change touching [ADR-0003](./adr/0003-master-on-data-plane.md) (Master on data plane), [ADR-0007](./adr/0007-websocket-http-transport.md) (WS transport), and [ADR-0012](./adr/0012-content-addressed-artifacts.md) (Artifact origin), and adds a cloud dependency + egress/storage cost. Likely a v0.x optional transport mode behind the existing transport abstraction, not the default. Wants its own ADR + design pass when revisited.
- **Master HA / multi-process** — replace single-process + SQLite with a replicated control plane. *Far off; SQLite is fine at target scale.*
- **Exactly-once Task execution** — v0.1 tolerates double-runs because all Tasks are idempotent. Only matters if non-idempotent Tasks are ever introduced.

---

## Research threads (papers, not just features)

1. **Scheduler paper** (lands on v0.1, strengthened by v0.2) — DL-aware, heterogeneity-native, automatic-capability-discovery scheduling for containerized volunteer DL fabrics. Eval: smart-pull vs round-robin vs Ray-style vs random on a real fleet + simulation at scale. Centerpiece: the 3-arm Ray comparison (default / manually-labeled / Compute4Me) with an operator-effort column.
2. **Empirical characterization of volunteer-style DL fabrics** (doc Gap 5) — throughput, time-to-accuracy, robustness to churn across real geographically-distributed Workers vs managed clusters. Naturally lands around v0.5 (WAN) when real distributed deployment exists.
3. **Pipeline-parallelism-over-hub paper** (v1.0) — the big-model training contribution.
