---
status: accepted
---

# Models Larger Than One GPU Are Out of Scope Until the Big-Model Thread

## Context

A natural question is whether Compute4Me supports training or inferring on models that exceed a single **Worker**'s GPU memory — e.g. Llama-3-70B, 100B+ research models. The standard solutions (FSDP, tensor parallelism, pipeline parallelism, SWARM) all require model parallelism, which is a substantially different architectural problem from data parallelism.

## Decision

Every milestone through **v0.5** assumes **the model fits on a single Worker's GPU**. This covers research models up to ~10B params on a 24 GB consumer card — essentially the entire space of models trainable or runnable on consumer hardware. Models that exceed one GPU are out of scope until **v0.6 (inference)** and **v1.0 (training)**.

## Why

1. **Audience fit.** Compute4Me targets researchers with lab GPUs + friends' consumer GPUs. Almost every model in that audience's workflow fits on one card. The audience that needs to train or run 70B+ models has alternatives (cloud H100, university supercomputers).
2. **Architectural mismatch with the single-GPU milestones.** FSDP and tensor parallelism need fast peer-to-peer (NVLink-class), which contradicts our master-brokered, no-worker-to-worker design ([ADR-0003](./0003-master-on-data-plane.md)). Pipeline parallelism is tractable through a Master relay but is a new primitive that doesn't fit the Map/Search abstraction.
3. **Engineering cost is enormous and orthogonal.** Pipeline-parallel training would be a 6–12 month research project on top of the v0.1–v0.5 substrate, and it requires deep integration with model libraries to extract layer subsets — not a quick extension.
4. **Order is correct.** The model-parallel work *uses* the orchestration substrate built across v0.1–v0.5 (capability profile, scheduler, room/token, artifact transport). Build the substrate first; layer big-model support on top later.

## Future thread

The big-model work has its own design tree:

- **v0.6 — big-model inference**: a new **Pipeline Job** primitive (alongside Map and Search). Each Worker hosts a contiguous range of model layers; inference requests stream through the pipeline via Master. Activation bandwidth is tractable (megabytes per request, not gigabytes). Estimated 6–8 weeks on top of the v0.5 substrate.
- **v1.0 — big-model training**: pipeline parallelism with backward pass + gradient flow, master-orchestrated layer assignment based on **Capability Profile**, SWARM-style re-routing when a Worker drops. This is the genuinely novel research contribution — "master-orchestrated pipeline parallelism over a hub topology with heterogeneity-aware layer assignment" — and is largely unclaimed in the literature.

## Revisit when

- A user actually needs to run/train a model larger than the largest GPU in their **Room**.
- The v0.5 substrate is shipped and proven.
- We're ready to commit a major version-cycle to the big-model thread.
