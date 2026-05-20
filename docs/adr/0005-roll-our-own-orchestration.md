---
status: accepted
---

# Roll Our Own Orchestration, Not Ray

## Context

The Job/Task abstraction (a Job decomposing into independent Tasks, a distributed object/artifact store, work assignment) is suspiciously Ray-shaped. The obvious move is to wrap Ray and inherit its scheduler, object store, actor model, and fault tolerance.

## Decision

Build the Master + Worker orchestration ourselves — a job queue, capability-aware assignment, and content-addressed artifact transport over WebSocket/HTTP. **No Ray dependency**, in the Master or the Worker container.

## Why

1. **Ray's onboarding is the opposite of ours.** `ray start --address` assumes admin-provisioned, SSH-configured nodes. Compute4Me's premise is token-gated `docker run` by people the operator doesn't administer ([ADR-0002](./0002-closed-membership-rooms.md)). We'd spend our time escaping Ray's defaults.
2. **Ray's scheduler is the part we'd replace anyway.** Ray matches generic resources (`num_gpus≥1`); our contribution is heterogeneity-aware, runtime-predicting placement ([ADR-0008](./0008-smart-pull-scheduling.md)). Wrapping Ray means replacing its most famous component.
3. **Ray's free lunch isn't needed for v0.1.** Sophisticated distributed scheduling + fault tolerance matter for complex dependency graphs; v0.1's Map+Search are embarrassingly parallel. A FIFO queue + capability matcher covers 90%. The v0.1 orchestration is ~300–500 LoC.
4. **It keeps onboarding honest.** Bundling Ray bloats the Worker container and pulls a heavy transitive dependency tree into something contributors run with one command.

## Revisit when

- v0.4 distributed training — Ray's `collective` primitives are *one* option to evaluate for the data plane. Even then, the orchestration layer stays ours; only the gradient-sync backend is in question.
