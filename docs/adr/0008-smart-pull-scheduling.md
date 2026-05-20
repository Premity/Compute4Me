---
status: accepted
---

# Smart-Pull Scheduling

## Context

The Master must assign Tasks to Workers that differ by orders of magnitude in speed and capacity. For v0.1's embarrassingly-parallel Map+Search, there's no inter-Task coordination, so this is a pure assignment problem — but *not* the easy one: a Task's runtime depends on *which* Worker runs it (a heavy HPO trial is 3 min on an RTX 3070, 18 min on a GTX 1060). This is scheduling on **unrelated parallel machines** (R‖Cmax), NP-hard in general.

## Decision

**Smart-pull.** The Master holds a priority queue of pending Tasks. When a Worker becomes free, it is handed the *best-fit* eligible Task: filter by feasibility (enough VRAM, GPU if required), prefer Tasks whose inputs the Worker has cached, and give a fast Worker the biggest pending Task / a slow Worker a smaller one. A coarse (within ~2×) DL-aware **Cost Model** (`work_units / throughput_ref`) drives the "best-fit." v0.1 runs **one Job at a time per Room**; Jobs queue FIFO.

## Why

1. **Pull is robust where push is brittle.** Push-all-upfront strands a big Task on a slow Worker when a runtime estimate is wrong, with no recovery. Pull auto-load-balances (a Worker that finishes early just pulls again) and tolerates coarse estimates.
2. **Pull handles dynamic arrival.** Optuna generates trials based on prior results, so Tasks arrive over time. A pull queue absorbs this naturally; a static push plan doesn't.
3. **The "smart" (best-fit) part is the contribution.** Plain pull would put the biggest Task on whichever Worker happens to be free first. Best-fit selection injects heterogeneity-awareness — the differentiation from Ray's "any node with a free GPU" ([ADR-0005](./0005-roll-our-own-orchestration.md)).
4. **Coarse is enough.** Even 2×-accurate runtime estimates beat round-robin; precision isn't worth the v0.1 engineering.

## Revisit when

- v0.2 adds a calibrated cost model, real-time-throughput rebalancing, dynamic re-sharding, and multi-Job concurrency with cross-Job fairness — all building on this queue, not replacing it.
