# Compute4Me Study Notes — Section 6: Federated, Edge/Fog, and Privacy-Aware Paradigms

> **Context:** Section 6 of the report looked at **federated learning (FL)**, **edge/fog computing**, and **private & secure distributed deep learning**. These paradigms are adjacent to Compute4Me: they also involve training across multiple devices, but with a stronger emphasis on **data locality and privacy** than on raw throughput. This doc explains what these systems do, how they work, and what you can reuse or extend.

---

## 6.1 Federated Learning Systems (FLSs)

### 6.1.1 What Federated Learning Actually Is

Federated learning (FL) flips the usual training paradigm:

- **Centralized training:** bring data from many clients into one data center; train a model centrally.
- **Federated training:** keep data **on the clients** (phones, hospitals, banks), send the **model** to them, let each client compute local updates, then aggregate those updates on a server.

The classical **FedAvg** algorithm:
1. Server sends current model \(w_t\) to a subset of clients.
2. Each client trains locally on its own data for a few epochs → updates \(w_t \to w_t^k\).
3. Clients send updates (or model weights) back to server.
4. Server aggregates: \(w_{t+1} = \sum_k p_k w_t^k\), where \(p_k\) reflects client data size.

This allows training a global model without raw data ever leaving clients.

### 6.1.2 Federated Learning Systems (FLSs): Survey

Main survey we rely on:

- *"A Survey on Federated Learning Systems: Vision, Hype and Reality for Data Privacy and Protection"* (Li et al., 2023, TKDE).[web:22][web:127][web:130][web:136]
  - arXiv version: https://arxiv.org/abs/1907.09693
  - TKDE DOI: https://doi.org/10.1109/TKDE.2021.3124599

This survey defines **Federated Learning Systems (FLSs)** and categorizes them along six axes:[web:22][web:127]

1. **Data distribution**: IID vs non-IID, balanced vs unbalanced.
2. **ML model**: linear, shallow, deep networks, personalized models.
3. **Privacy mechanism**: DP, secure aggregation, HE, etc.
4. **Communication architecture**: star (client-server), hierarchical, peer-to-peer.
5. **Scale of federation**: a few powerful silos (banks/hospitals) vs millions of devices (phones).
6. **Motivation**: regulatory/privacy constraints, resource constraints, or both.

They also discuss FLS components:
- Client selection.
- Communication protocols.
- Aggregation server.
- Security & privacy modules.

### 6.1.3 Existing FL Frameworks

There are several open-source frameworks:

- **TensorFlow Federated (TFF)**: https://www.tensorflow.org/federated
- **PySyft** (OpenMined): https://github.com/OpenMined/PySyft
- **Flower (FLWR)**: https://flower.dev / https://github.com/adap/flower

**TensorFlow Federated:**
- Provides a declarative interface for defining federated computations and simulating FL on a single machine.
- Good for research and prototyping.

**PySyft:**
- Focuses on privacy-preserving ML with FL + differential privacy + secure multi-party computation.

**Flower:**
- A flexible **FL orchestration framework**.
- You write your model code in PyTorch/TensorFlow; Flower handles the client/server orchestration.

### 6.1.4 Difficulty to Use vs Reimplement

- **Using an FLS as-is:**
  - For exoplanet-style workloads, you could use Flower to simulate FL (e.g., different observatories as clients).
  - Code changes: moderate; you need to write client and server logic.

- **Reimplementing an FLS:**
  - Hard if you want all bells & whistles (client selection, robust aggregation, DP, secure aggregation, etc.).
  - Medium if you build a minimal FedAvg system: one server, multiple clients, simple SGD updates.

### 6.1.5 Relevance to Compute4Me

Compute4Me is **not primarily privacy-driven**; it’s more about harnessing spare compute. But FL gives you:

- A **template for data-local training**: if volunteers cannot share raw data (e.g., proprietary telescope data), FL-style training lets them participate safely.
- A library of **privacy and security mechanisms** you can plug into your orchestration.

Potential hybrid:
- Some Compute4Me jobs are **federated** (data never leaves nodes; only gradients/updates do).
- Others are **centralized** (data lives on master or a few data nodes).

---

## 6.2 Edge, Fog, and IoT-Oriented Deep Learning

### 6.2.1 Computing Paradigms: Cloud, Edge, Fog, IoT

The survey:

- *"Deep learning models for cloud, edge, fog, and IoT computing paradigms: Survey, recent advances, and future directions"* (Shahnawaz et al., 2023).[web:21][web:137]
  - ScienceDirect: https://www.sciencedirect.com/science/article/abs/pii/S1574013723000357

explains these paradigms:

- **Cloud computing:** Central data centers; high compute, but higher latency and bandwidth cost.
- **Edge computing:** Compute deployed near data sources (e.g., base stations, routers) to reduce latency.
- **Fog computing:** A multi-layer hierarchy: cloud ↔ fog nodes ↔ edge devices.
- **IoT:** Many small devices (sensors, embedded boards) at the very edge.

The key motivation: IoT and real-time apps produce huge data volumes and have strict latency requirements; shipping everything to the cloud is too slow and expensive.[web:21][web:137]

### 6.2.2 DL at the Edge/Fog

The survey highlights:[web:21][web:137]

- **Deploying DL models at the edge** for real-time inference (e.g., video analytics on a local gateway).
- **Collaborative training** across edge/fog nodes to adapt models locally.
- Challenges:
  - Limited compute (small GPUs or CPUs).
  - Energy constraints.
  - Unreliable connectivity.

There’s overlapping work on **lightweight DL models for IoT** (TinyML, MobileNet, SqueezeNet, quantization, pruning).[web:131]

### 6.2.3 Difficulty to Use vs Reimplement

- Using this paradigm:
  - If you wanted to run exoplanet inference close to telescopes, you’d deploy compact models on edge devices and use fog nodes to aggregate.
  - Requires engineering of model compression and deployment, not new DL algorithms.

- Reimplementing a fog/edge orchestration layer:
  - Medium: you’d use MQTT, gRPC, or similar to connect edge → fog → cloud.

### 6.2.4 Relevance to Compute4Me

Compute4Me is conceptually a **fog-like system**:

- Master node ≈ cloud / central control.
- Volunteer nodes ≈ edge/fog nodes.

Differences:

- Edge/Fog literature often assumes **long-lived, managed nodes** (e.g., base stations), not ad-hoc volunteers.
- But their strategies for **placing models closer to data** and managing resource-constrained devices are directly relevant.

Possible synergy:
- Some Compute4Me nodes could be **persistent edge nodes** (e.g., in observatories), others opportunistic volunteers.
- For latency-sensitive jobs (e.g., real-time transient detection), you’d schedule primarily on edge/fog nodes.

---

## 6.3 Private and Secure Distributed Deep Learning

### 6.3.1 Survey: Private and Secure Distributed DL

We use:

- *"Private and Secure Distributed Deep Learning: A Survey"* (Allaart et al., ACM Computing Surveys, 2025).[web:25][web:135][web:138]
  - Publisher link: https://dl.acm.org/doi/10.1145/3703452

This survey splits distributed learning into two broad paradigms:[web:25][web:135]

1. **Centralized distributed training:** Data potentially flows to a central cluster (standard distributed DL), but there may still be multiple data owners.
2. **Decentralized/federated training:** Data stays where it originates; only updates or encrypted data move.

It then catalogs **protective measures**:

- **Secure aggregation:** Server aggregates client updates without being able to see individual updates.
- **Differential privacy (DP):** Noise added to gradients or parameters to limit privacy leakage.
- **Homomorphic encryption (HE):** Computations on encrypted data.
- **Secure multi-party computation (MPC):** Protocols that compute a function over inputs while keeping them private.

And highlights open issues:[web:25][web:129]

- Efficiency: many cryptographic protocols are expensive.
- Scalability: scaling to millions of clients.
- Combining privacy and robustness: defending against malicious clients *and* preserving privacy.

### 6.3.2 Survey: Privacy-Preserving Deep Learning (PPDL)

Another relevant survey:

- *"A comprehensive survey and taxonomy on privacy-preserving deep learning"* (2024).[web:129]
  - ScienceDirect: https://www.sciencedirect.com/science/article/abs/pii/S0925231224001164

Focuses on:

- Threats to privacy in DL (membership inference, model inversion, etc.).
- Techniques: DP-SGD, HE, MPC, split learning, etc.
- Evaluation criteria for PPDL solutions.

### 6.3.3 Difficulty to Use vs Reimplement

- **Using DP / secure aggregation:**
  - Many FL frameworks (e.g., TFF, PySyft, Flower) already have examples.
  - Implementing basic DP-SGD is fairly straightforward (clipping + Gaussian noise).

- **Using HE / MPC:**
  - Harder, heavy crypto, and often 10–100× slower.

- **Reimplementing full privacy stack:**
  - High complexity; you’d likely rely on existing libraries (OpenMined, HE libraries like Microsoft SEAL, etc.).

### 6.3.4 Relevance to Compute4Me

Compute4Me’s main driver is compute pooling, but:

- Some contributors may care about **privacy of their local data** (e.g., proprietary astronomical observations, company logs).
- If you want to attract such contributors, supporting **FL-style data locality + DP/secure aggregation** becomes a selling point.

Practical path:
- Start with **no raw data movement** from volunteers (only gradients/updates).
- Add **basic DP** on client-side updates for privacy-sensitive jobs.
- Consider **secure aggregation** to prevent master from seeing individual client updates.

---

## 6.4 How These Paradigms Intersect with Compute4Me

### 6.4.1 Two Kinds of Compute4Me Jobs

From these paradigms, you can distinguish **two classes of jobs** Compute4Me might support:

1. **Compute-focused jobs (current emphasis)**
   - Data is centrally hosted (e.g., on the master or a few data nodes).
   - Volunteers provide compute only; data is streamed to them as needed.
   - Privacy is less critical; performance and heterogeneity handling dominate.

2. **Privacy-sensitive jobs**
   - Data must **never leave the owner’s node**.
   - Compute4Me orchestrates federated-style training:
     - Master sends model/config.
     - Nodes locally train and send encrypted or noisy updates.
     - Master aggregates.

Having both modes makes Compute4Me more generally useful.

### 6.4.2 Where Novelty Can Be Added

1. **Federated Deep Learning on a Volunteer Fabric**
   - Existing FL systems assume relatively stable clients (e.g., phones) and strong control of the server.
   - Combine FL with **volunteer-style, heterogeneous, ephemeral nodes**:
     - Some nodes are edge devices with local sensitive data.
     - Others are pure compute volunteers.
   - Scheduler must decide:
     - Which nodes are data owners vs compute-only.
     - How to place models to minimize privacy risk and maximize performance.

2. **Edge/Fog-Aware Scheduling in Compute4Me**
   - Data-heavy jobs: schedule close to the data (edge/fog nodes), use nearby volunteers.
   - Latency-sensitive inference: prefer fog/edge nodes.
   - Background training/HPO: use idle remote volunteers.

3. **Lightweight Privacy for Volunteer DL**
   - Add DP-SGD or basic DP on volunteer nodes for sensitive jobs.
   - Use secure aggregation when multiple volunteers share a dataset type (e.g., multiple telescopes).

4. **Unified DSL for Data-Local vs Data-Centralized Jobs**
   - Provide a job specification where a user can say:

     - `data_location: "central"` (Compute4Me pulls data to workers), or
     - `data_location: "local"` (workers keep data and only send updates).

   - The runtime chooses between **standard distributed DL** and **federated-style training** automatically.

### 6.4.3 Difficulty for Compute4Me to Add These Features

- **Mode 1 (compute-focused, centralized data):**
  - You already have most ingredients: DDP/Horovod/Ray Train inside containers + your scheduler.

- **Mode 2 (FL-style, privacy-aware):**
  - Using an existing FL framework inside Compute4Me nodes (e.g., Flower): medium.
  - Adding DP on top: medium.
  - Implementing secure aggregation: medium–high, but libraries exist.

The big win is that **you don’t need to invent federated learning**, just integrate it into your orchestration so that privacy-sensitive jobs can opt into it.

---

## 6.5 Summary

Section 6 broadens the picture from “use everyone’s GPUs for training” to “use everyone’s GPUs **and** data in a privacy-preserving way when needed.”

- **Federated learning systems** focus on keeping data local and aggregating updates, with a rich ecosystem of frameworks (TFF, PySyft, Flower) and a detailed system-level survey.[web:22][web:127][web:130]
- **Edge/fog/IoT DL** focuses on where to put computation (edge vs fog vs cloud) to minimize latency and bandwidth, which maps naturally onto Compute4Me’s master–worker architecture in heterogeneous networks.[web:21][web:137]
- **Private and secure distributed DL** explores DP, secure aggregation, HE, and MPC as tools to mitigate privacy and security risks in distributed training.[web:25][web:135][web:129]

Compute4Me can leverage these paradigms to support **two job modes** — performance-focused and privacy-focused — and to offer an advanced scheduler that is aware of both **where the data is** and **how sensitive it is**, not just where GPUs are.

---

*This completes the deep dive through Section 6. The next logical step in the overall series would be synthesizing Sections 2–6 into a concrete Compute4Me architecture and then defining an initial minimal prototype.*

