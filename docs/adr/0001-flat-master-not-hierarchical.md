---
status: accepted
---

# Flat Master, not Hierarchical Aggregation

## Context

Compute4Me's **Workers** will live in network regimes that differ by orders of magnitude — a lab LAN (sub-ms RTT, Gbps) and friends' home internet links (50–200 ms RTT, tens of Mbps) can join the same **Room**. Hierarchical SGD — sync tightly within each network tier, loosely across tiers — is a well-established pattern (used by NCCL's intra-/inter-node split, by federated edge→fog→cloud, by geo-distributed training) and is the textbook answer to multi-tier networks.

## Decision

Every milestone (until hierarchy is warranted — see *Revisit when*) uses a **single flat Master**. No Sub-Masters, no nested aggregation. The Master directly aggregates from every Worker in the Room, with per-Worker sync frequency varying instead (every step on LAN once training lands in v0.4; local-SGD every K steps on WAN in v0.5).

## Why

1. The three concrete novelty gaps Compute4Me targets (Docker-native onboarding, capability-aware heterogeneous scheduling, cross-paradigm multiplexing) live in the **scheduler and orchestration**, not in the aggregation topology. Hierarchical aggregation is already covered by FL literature and NCCL — building it would consume a large engineering budget for no novelty.
2. Three component types (leaf Worker, Sub-Master, Top-Master) is ~4–5× the engineering surface of one, with new failure modes (Sub-Master dies mid-aggregation while its Workers are mid-step), new RPC contracts, and a much murkier onboarding UX than "run this container with a token."
3. At the scale the project will actually run at first (4–20 Workers), the flat Master's uplink is not the bottleneck. Hierarchy pays off at 50+ Workers across many tiers; we are not there and may never be.

## Leaving the door open

To make hierarchy a later-additive feature instead of a later-rewrite, we hold three architectural rules from day one:

1. **Master ↔ Worker communicates over a network protocol** (not in-process calls), so a Sub-Master can speak both sides.
2. **The aggregation function accepts N gradient streams with per-stream weights**, so its inputs could be pre-averaged updates from Sub-Masters carrying "we represent K Workers" weighting.
3. **A Worker has exactly one Master address it talks to** (configurable). Pointing a leaf at a Sub-Master instead of the Top-Master becomes a config change, not a code change.

If we ever cross the scale or topology threshold where hierarchy pays, adding a Sub-Master role on top of the existing abstractions is roughly a multi-week change, not a rewrite. Until then, every reader who asks "why aren't they hierarchical?" should be pointed here.

## Revisit when

- More than ~50 Workers in a single Room.
- Workers cluster into ≥3 network tiers with order-of-magnitude bandwidth gaps.
- Profiling shows the Master's uplink is the steady-state bottleneck (not the slowest Worker's gradient compute).
