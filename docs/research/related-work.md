# Related Work

A condensed survey of the distributed deep-learning landscape Compute4Me sits in. Frames the project as a **Docker-native, master-orchestrated DL fabric for heterogeneous, firewall-constrained machines**, at the intersection of cluster training, volunteer compute, elastic scheduling, and container-based deployment.

## 1. Classical distributed DL — largely solved

Two architectures underpin most production distributed training:

- **Parameter Server (PS)**: server nodes hold global weights; workers pull, compute gradients on local shards, push updates. Scales well in data centers but the PS tier can bottleneck.
- **All-reduce** (e.g., ring all-reduce in NCCL / Horovod): workers exchange gradients directly in a collective pattern. More bandwidth-efficient, no central bottleneck.

Mature implementations: **Horovod** (Uber), **PyTorch DDP**, **TensorFlow's distribution strategies**, **GeePS** (GPU-specialized PS). These solve synchronous data-parallel training on homogeneous or mildly heterogeneous data-center clusters with stable connectivity. What stays hard: extremely large models under network constraints, and *highly* heterogeneous nodes with intermittent availability.

## 2. Ray and general-purpose AI compute engines — closest to Compute4Me, but assumes a managed cluster

**Ray** (Moritz et al., OSDI 2018) is a general-purpose distributed framework that unifies task-parallel and actor-based execution. It includes a distributed scheduler, a fault-tolerant object store, and high task throughput (1.8M tasks/sec in published benchmarks). **Ray Train** layers DL-specific abstractions (PyTorch/TF training loops, sharding, checkpoints) on top.

Ray is the system Compute4Me overlaps with most. Key limitations for the Compute4Me setting:

- **Onboarding assumes an admin-provisioned cluster.** `ray start --address=…` requires SSH access, firewall config, and explicit node addition. No volunteer-self-join story.
- **Scheduler is resource-based, not DL-aware.** `num_gpus` is opaque — an RTX 3070 and a GTX 1060 look the same to Ray. Critical context (VRAM, bandwidth, historical reliability, cached datasets) is invisible.
- **Trust model assumes one admin domain.** No mechanism for semi-trusted volunteers; gradient poisoning is unaddressed.

## 3. Elastic and heterogeneous training — active research

**EasyScale** (2022) is an elastic training system that maintains accuracy consistency when scaling distributed data-parallel training across heterogeneous GPUs — by decoupling training logic from resource allocation and adjusting per-worker parameters (batch size, gradient scaling) to preserve convergence semantics. Demonstrated +60% GPU utilization in a production cluster.

The **2024 ICML survey** "Resource Allocation and Workload Scheduling for Large-Scale Distributed Deep Learning" reviews 5 years of scheduling research across job-level, pipeline-level, and network-flow-level granularities. Persistent open problems: heterogeneity in hardware/workloads, fault tolerance, optimization complexity at data-center scale.

Both lines focus on *data-center* heterogeneity. They don't address opportunistic, consumer-hardware, intermittent fleets — the Compute4Me regime.

## 4. Decentralized and volunteer-based DL — adjacent, but masterless

Volunteer computing has a long history (BOINC, Folding@home) — proven that pooled compute can exceed supercomputers in aggregate FLOPs, but for loosely-coupled simulations rather than tightly-synchronized neural networks.

**Hivemind** (the Learning@home project) is a PyTorch library for decentralized DL across internet-connected volunteers. It uses peer-to-peer protocols for parameter averaging and supports decentralized Mixture-of-Experts to train models larger than any single participant's memory. **SWARM Parallelism** (2023, built on Hivemind) extends this to pipeline-parallel training of large models on unreliable heterogeneous devices, with random re-wiring of the pipeline when nodes fail.

**Secure Distributed Training at Scale** (ICLR 2022) proposes Byzantine-tolerant decentralized training protocols that resist gradient poisoning and Sybil attacks while remaining communication-efficient.

These systems target a regime very similar to Compute4Me's, but they make two structural choices Compute4Me rejects:

- **Fully decentralized, no master** — sacrifices central orchestration UX (Compute4Me wants a master for capability accounting, job decomposition, ergonomics).
- **Require framework rewrites** — Hivemind/SWARM need the model expressed as Decentralized MoE; standard models like InceptionResNet don't compose.

## 5. Federated, edge, and fog-based learning — overlapping but data-privacy-first

Federated Learning (FL) trains across clients while keeping data local. Recent surveys (e.g., "A Survey on Federated Learning Systems") categorize FL systems by data distribution, privacy mechanism, communication architecture, and federation scale. Distinct from Compute4Me in motivation: FL is about *data sovereignty*; Compute4Me is about *compute pooling*. Edge/fog computing literature pushes ML to the network edge for latency/bandwidth reasons, again with different optimization targets.

**Private and Secure Distributed DL** (2024 survey) reviews secure aggregation, differential privacy, and homomorphic encryption in distributed settings. Algorithmically rich but engineering implementations for general-purpose ad-hoc clusters are scarce.

## 6. Serverless and cloud-native ML — different cost model

Databricks, AWS Lambda, and similar offer distributed ML on managed/serverless infrastructure. They show how far cloud-native abstractions can hide cluster management, but they assume managed services and a billing relationship — not user-contributed nodes in a non-cloud setting.

## 7. Containerization — treated as deployment, not scheduling

Container-based packaging of DL workloads (Docker for reproducible environments; Kubernetes for orchestration) is mature. What's underexplored: **container-aware scheduling semantics for DL** — capability discovery from inside a container, model-agnostic Master↔container contracts, fine-grained per-container resource accounting tied to DL workload structure. Most research treats containers as deployment units; Compute4Me elevates the container to the unit of *execution* with a typed contract.

## 8. Gaps Compute4Me targets

From the synthesis above, six concrete gaps emerge that align directly with the project's scope. The first three are addressed in v0.1; the remaining three live in the [ROADMAP](../roadmap.md) for v0.2+.

1. **Heterogeneity- and capability-aware orchestration for volunteer-style fabrics** — Most scheduling work assumes data-center clusters. Volunteer-based systems (Hivemind) avoid central scheduling. Compute4Me proposes a master-driven orchestrator that automatically profiles each Dockerized node (GPU, VRAM, throughput, cached datasets, bandwidth) and uses this for placement.
2. **Container-centric, model-agnostic execution interface** — Existing frameworks require modifying training-loop code. Compute4Me's [Container Contract](../architecture/wire-protocol.md) treats containers as black boxes with env-vars-in/files-out — standard models compose unchanged.
3. **Empirical characterization of opportunistic DL fabrics** — Little measurement exists comparing volunteer-style DL fabrics to managed clusters. Compute4Me v0.1's [eval](../prd.md#13-eval--research-runbook) provides a 3-arm comparison (Ray default / Ray + manual labels / Compute4Me) on a real heterogeneous fleet plus a simulation arm at 10/50/200 Workers.
4. *(v0.4+)* **Hybrid master–decentralized architectures for training** — Compute4Me's [ADR-0001](../adr/0001-flat-master-not-hierarchical.md) holds the door open for sub-masters and capability-weighted aggregation when distributed training arrives.
5. *(v1.0)* **Master-orchestrated pipeline parallelism for big models** — The cross-over between Hivemind/SWARM (no master) and Megatron (master on InfiniBand). Currently open.
6. *(deferred)* **Integration of privacy and security into containerized volunteer fabrics** — Byzantine-robust aggregation, secure aggregation, differential privacy as containerized-fabric features. Out of scope for v0.1 ([ADR-0002](../adr/0002-closed-membership-rooms.md)) but a natural extension once closed-membership trust is exhausted.

## Key references

- Moritz et al., **Ray: A Distributed Framework for Emerging AI Applications**, OSDI 2018.
- Sergeev & Del Balso, **Horovod: fast and easy distributed deep learning in TensorFlow**, 2018.
- Li et al., **EasyScale: Accuracy-consistent Elastic Training for Deep Learning**, 2022.
- Ryabinin et al., **SWARM Parallelism: Training Large Models Can Be Surprisingly Communication-Efficient**, ICML 2023.
- Diskin et al., **Secure Distributed Training at Scale**, ICLR 2022.
- Liu et al., **Resource Allocation and Workload Scheduling for Large-Scale Distributed Deep Learning**, 2024.

The full literature-review drafts (8 long-form section files) are preserved in the git history before this consolidation.
