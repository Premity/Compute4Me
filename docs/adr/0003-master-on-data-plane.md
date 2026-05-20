---
status: accepted
---

# Master on the Data Plane; Workers Connect Outbound Only

## Context

Compute4Me's **Workers** live behind firewalls and NATs that often forbid inbound connections and worker-to-worker traffic — both in segmented lab LANs (observed: lab machines on one LAN cannot reach each other directly) and on all residential WAN links. The dominant distributed-DL data plane, ring all-reduce (NCCL/Gloo, as used by PyTorch DDP, Horovod, Ray), assumes every Worker has a fast direct link to every other Worker.

## Decision

**Workers only ever make outbound connections to the Master.** There are no worker-to-worker connections, and no NAT traversal until v0.5. The Master is therefore on the **data plane**, not just the control plane: through v0.3 it relays Artifacts and collects results; from v0.4 it aggregates gradients (parameter-server-shaped). The only network requirement is that the Master is reachable from every Worker (one lab machine on a routable interface, or a small VPS).

## Why

1. **It's the only thing that reliably works** given the network constraints. "Can your machine reach `master:8888` outbound?" is answerable yes on essentially every network; "can all your machines accept inbound and reach each other?" is not.
2. **All-reduce loses its advantage on a hub anyway.** Ring all-reduce parallelizes communication across N independent peer links. Route every byte through a single Master uplink and that parallelism collapses — relayed all-reduce becomes *strictly worse* than a parameter server on the same hub. So the constraint doesn't cost us the "better" algorithm; on a hub, PS-shaped aggregation **is** the better algorithm.
3. **The Master-aggregator architecture carries through all versions.** v0.1–v0.3 (no gradients) → v0.4 (every-step PS aggregation on LAN) → v0.5 (local-SGD, infrequent sync on WAN). What changes is sync *frequency*, not topology.
4. **It keeps onboarding a one-liner.** No firewall config on the contributor's side is the whole point of "join with one `docker run`."

## Consequences

- The Master's uplink is the steady-state bottleneck at scale. Acceptable at the project's target scale (4–20 Workers); see [ADR-0001](./0001-flat-master-not-hierarchical.md) for the revisit threshold and the hierarchy escape hatch.
- Readers from the Ray/Hivemind world will ask "why are gradients going through the master?" — this is the answer.
- Direct worker-to-worker links and P2P artifact distribution remain possible *future optimizations* (v0.5 for WAN where the Master uplink saturates), added behind the same `GradientChannel`/transport abstraction.

## Revisit when

- Profiling shows the Master uplink (not the slowest Worker's compute) is the steady-state bottleneck.
- A deployment has reliable worker-to-worker connectivity that would make direct all-reduce worthwhile.
