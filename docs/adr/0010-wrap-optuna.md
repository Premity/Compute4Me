---
status: accepted
---

# Wrap Optuna for Search Spaces, Not a Homegrown DSL

## Context

Search Jobs need a way to express hyperparameter search spaces and a sampling strategy. Options: invent a native DSL (`LogUniform`, `Choice`, …), wrap Optuna, or wrap Ray Tune (rejected — pulls in Ray, see [ADR-0005](./0005-roll-our-own-orchestration.md)).

## Decision

Define a small **Sampler** interface (`ask() -> config`, `tell(config, result)`) and ship **Optuna** as the v0.1 implementation, with a **raw config-list** fallback for users who don't want Optuna. The Sampler runs on the Master; Compute4Me dispatches each emitted config as a Task to a Worker.

## Why

1. **Optuna is the de-facto HPO DSL in the PyTorch world.** Researchers already know it — no new search-space language to learn.
2. **Advanced samplers for free.** TPE, multivariate TPE, multi-objective NSGA-II — we won't outdo these; wrapping inherits them.
3. **Clean integration.** Optuna already separates "ask for a config" from "execute it." Compute4Me slots in as the remote-execution half (`ask()` → Task; `tell()` ← result).
4. **No lock-in.** The pluggable interface costs ~30 extra LoC and lets users pass a plain config list or, later, a different sampler. A homegrown DSL would reinvent Optuna and lose the advanced samplers.

## Consequences

- Running N trials in parallel weakens a sequential sampler's quality slightly (configs are drawn before all prior results return). Handled via Optuna's `ask`-before-all-`tell` async support; acceptable, and matches how Ray Tune handles the same.

## Revisit when

- v0.3 adds additional Sampler implementations (Hyperopt, scikit-optimize, DEAP) behind the same interface, only when someone needs one.
