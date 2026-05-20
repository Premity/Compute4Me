---
status: accepted
---

# Two Primitives (Map + Search), Not a Job-Type Laundry List

## Context

Users want HPO, batch inference, preprocessing, evaluation, and ensemble work. The naive design is a growing enum of job types (`"hpo" | "inference" | "preprocess" | "eval" | "ensemble" | ...`), each with bespoke handling.

## Decision

Two composable primitives:

- **Map** — run `code_ref` on N shards of input `D`, write results to `O`. Covers inference, eval, preprocessing, feature extraction.
- **Search** — run `code_ref` with N configurations from a search space, collect a metric. Covers HPO, ablations, ensemble training.

Everything else composes (ensemble inference = Map over a model list; workflows = Search chained into Map). The **Worker** is agnostic to which primitive produced its Task — primitives only differ in how the **Master** decomposes a Job.

## Why

1. **Avoids an arbitrary, ever-growing enum.** Each new "job type" otherwise means new scheduler/decomposition code. Two primitives + composition cover the space.
2. **Cleaner contribution.** "A composable orchestration substrate" is a stronger and more honest claim than "we support N workload types" — and it doesn't claim to have invented HPO or inference.
3. **Forces a generic abstraction.** Supporting two primitives from day one prevents baking HPO-specific assumptions into the Task model — which is what makes the model-agnostic container contract ([ADR-0006](./0006-black-box-container-contract.md)) possible.

## Revisit when

- v0.6 adds **Pipeline** as a third primitive for big-model inference — a request traverses multiple Workers, which neither Map nor Search expresses. See [ADR-0004](./0004-big-models-out-of-scope.md).
