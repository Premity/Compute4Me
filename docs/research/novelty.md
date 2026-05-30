# Novelty — what Ray doesn't solve, where Compute4Me lives

Ray is the closest existing system to Compute4Me's design space. This document examines, gap by gap, what Ray's assumptions exclude and what Compute4Me adds on top. Each gap maps to either a v0.1 contribution or a future-version research thread (see [../roadmap.md](../roadmap.md)).

## Ray's world, in one sentence

Ray is excellent for **a cluster you control, with nodes you trust, on hardware you provisioned, connected on a fast LAN or cloud network**. The moment you step outside that — heterogeneous consumer hardware, internet links, semi-trusted contributors, ad-hoc joining — Ray's assumptions start to crack.

## Gap 1 — Open-world, volunteer-style node joining *(v0.1)*

**Ray:** Nodes join via `ray start --address=…`, requiring SSH, firewall config, and explicit admin action per node.

**Adjacent work:** Hivemind handles internet-volunteer joining via BitTorrent-style DHT — but is fully decentralized (no master) and requires the model to be expressed as Decentralized Mixture-of-Experts. "Distributed Deep Learning Using Volunteer Computing-Like Paradigm" (Atre et al., 2021) designed VC-ASGD for preemptible, unreliable workers, but used preemptible cloud instances as a proxy — not real volunteer hardware joining via container.

**The gap:** No master-centric, Docker-native volunteer-joining system exists for general DL. Ray is too ops-heavy; Hivemind is masterless and framework-restrictive.

**Compute4Me's contribution:** A Docker image any Ubuntu user runs with `docker run compute4me worker --token <T>` — outbound-only, no inbound ports, no SSH, no firewall changes. The Master verifies the token, profiles the host, admits it under the token's `max_workers` cap. See [ADR-0002](../adr/0002-closed-membership-rooms.md) and [ADR-0003](../adr/0003-master-on-data-plane.md).

## Gap 2 — Capability-aware, DL-specific heterogeneous scheduling *(v0.1)*

**Ray:** The scheduler is generic resource-matching. Declare `num_cpus`, `num_gpus`, `memory`; Ray finds a node that has enough. But **all GPUs look the same to Ray** — an RTX 3070 with 8 GB VRAM and a GTX 1060 with 6 GB VRAM both count as "1 GPU." PCIe bandwidth, internet uplink, historical reliability, cached datasets — invisible.

**Adjacent work:** "Topology-aware GPU scheduling with deep reinforcement learning" (2025) reports 47% throughput improvement by adding topology to the scheduler's state. "GPU Cluster Scheduling for Network-Sensitive Deep Learning" (2024) uses proximity-based consolidation to reduce communication bottlenecks. Netflix's heterogeneous Ray cluster built custom layers atop Ray for similar reasons.

**The gap:** A scheduler that goes beyond "does it have a GPU?" to "what kind of GPU, how much VRAM, how fast is the network, what's the historical throughput?" — and uses that to make **DL-aware placement** decisions: bigger shards to faster cards, VRAM-feasibility as a hard constraint, locality preference for cached data.

**Compute4Me's contribution:** A [Capability Profile](../architecture/data-model.md#capability-profile) advertised by each Worker (GPU model, VRAM, micro-benchmark throughput, cached datasets, bandwidth/RTT to Master) feeds a [smart-pull scheduler](../adr/0008-smart-pull-scheduling.md) that does best-fit-eligible placement, not first-fit. This is the v0.1 paper contribution.

## Gap 3 — SWARM-style elastic pipelines, but with a master *(v1.0 — marquee research)*

**SWARM Parallelism** (Ryabinin et al., ICML 2023) trains large models on poorly-connected, heterogeneous, unreliable devices. It splits the model into pipeline stages and **randomly re-wires** the pipeline when nodes fail or leave. Built on Hivemind, fully decentralized. A 2025 follow-up (Pluralis Research) added asynchronous updates with NAG-based gradient correction for up to 45.9% wall-clock improvement on elastic swarms.

**The gap:** SWARM is masterless and Hivemind-dependent. No system combines:
- A **logical master** for task decomposition, job submission UX, capability accounting.
- **SWARM-like elastic pipeline routing** for model-parallel execution across heterogeneous nodes.

**Compute4Me's future contribution (v1.0):** Hybrid where the master decomposes and assigns jobs, but pipeline execution uses SWARM-style elastic routing among Workers. Combines master-driven UX with masterless fault tolerance. See [ROADMAP v1.0](../roadmap.md).

## Gap 4 — Security and trust for semi-trusted volunteers *(deferred)*

**Ray:** Assumes all nodes are trusted (one admin domain). No mechanism against gradient poisoning or fabricated results.

**Adjacent work:** "Towards Volunteer Deep Learning: Security Challenges and Solutions" (2025) surveys exactly this problem. "Secure Distributed Training at Scale" (ICLR 2022) proposes Byzantine-tolerant protocols. ACM's 2019 survey of volunteer computing discusses trust architectures.

**The gap:** No system combines Byzantine-robust aggregation with a practical, container-based, volunteer DL fabric. Existing secure-training papers are algorithmic; no Docker-native implementation works over commodity internet.

**Compute4Me's position:** v0.1 uses **closed-membership** ([ADR-0002](../adr/0002-closed-membership-rooms.md)) — trust established out-of-band via Invite Token issuance. No Byzantine defenses, only bug-level checks (finite metrics, valid output schemas). Open/public Rooms with Byzantine-robust aggregation are a separate research thread, not on the v0.x ladder.

## Gap 5 — Cross-paradigm multiplexing on the same fabric *(v0.1)*

**Ray:** Ray Train (training), Ray Tune (HPO), Ray Serve (inference) run on the same Ray cluster but are separate libraries with separate APIs. No unified "DL job" abstraction picks the right parallelism strategy based on job type and current node availability.

**The gap:** A single job submission could be a training run (data-parallel), an HPO search (trial-parallel), or large inference (pipeline-parallel). No open-source system gives a single, simple interface that picks the right strategy.

**Compute4Me's contribution:** Two job primitives in v0.1 — **Map** (sharded batch) and **Search** (HPO/ablation) — under one submission API ([ADR-0009](../adr/0009-map-search-primitives.md)). A third primitive, **Pipeline**, lands in v0.6 for big-model inference. The Master picks decomposition and placement; the user describes *what*, not *how*.

## Summary table

| Dimension | Ray | Compute4Me |
|---|---|---|
| Node joining | Admin-provisioned, SSH, firewall config | Docker-based volunteer self-registration (v0.1) |
| Scheduling | Generic resource matching (GPU count) | DL-aware: VRAM, bandwidth, throughput, locality (v0.1) |
| Elasticity | Limited in heterogeneous settings | SWARM-style elastic pipelines (v1.0 target) |
| Security | Trusted nodes only | Closed-membership v0.1; Byzantine-robust deferred |
| Job interface | Separate Train/Tune/Serve APIs | Unified Map/Search v0.1; Pipeline v0.6 |
| Hardware target | Managed clusters / cloud VMs | Commodity consumer GPUs over the internet |

## What Compute4Me is *not* claiming to invent

The novelty is **not** in any single technique. Hivemind has volunteer joining. Capability-aware scheduling exists in fragments. The Container Contract pattern is well-known from CI systems. SWARM has the elastic-pipeline idea.

The novelty is in **the specific composition for a real, used, deployable system**: a master-driven orchestrator that makes ad-hoc heterogeneous Dockerized hardware usable for standard DL workloads with one command, evaluated empirically against Ray on the same fleet. The v0.1 paper contribution lives in that composition + the empirical comparison, not in any one component.
