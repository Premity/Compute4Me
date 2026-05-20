---
status: accepted
---

# Black-Box Container Contract, Not an SDK

## Context

The Master must tell a user's container what to do and collect what it produced. The Ray-style approach is an SDK: the user imports the framework and wraps their code in a decorator. But a core Compute4Me goal (the survey's Gap 3) is a *model-agnostic* execution interface — the user shouldn't have to modify their model code to run on the fabric.

## Decision

The container speaks **env-vars-in, files-out** (the "B1" contract), with **no `compute4me` import required** in model code. The Master launches the container with `C4M_CONFIG` (path to a Task-args JSON), `C4M_INPUT_DIR` (mounted input Artifacts), `C4M_OUTPUT_DIR` (where the container writes `metrics.json` and result Artifacts), and `C4M_TASK_ID`. Process exit code signals success/failure; an optional `progress.jsonl` is tailed for live metrics. An optional **SDK** (`c4m.config()`, `c4m.report(...)`) is pure sugar over this contract, never required.

## Why

1. **It delivers the model-agnostic promise.** Users bring a standard Dockerized script, add a ~10-line entrypoint shim (or use our base image), and it runs — no framework leaking into model code.
2. **It's debuggable in isolation.** A user can run their container locally with the same env vars and reproduce exactly what a Worker does — invaluable across heterogeneous machines.
3. **It's language-agnostic by accident.** JAX, TensorFlow, or non-Python containers work identically, because the contract is files + env vars, not a Python API.
4. **One contract, both primitives.** Map Tasks get a shard in `C4M_INPUT_DIR`; Search Tasks get hyperparameters in `C4M_CONFIG`. The Worker never knows which primitive produced its Task.

The SDK-decorator alternative couples user model code to Compute4Me — exactly the friction the project exists to remove. The cost of B1 (file-based, not rich-typed, data passing) is a non-issue for DL workloads (small config dicts, file outputs).

## Revisit when

- v0.3 adds the **B2 sidecar** (live-RPC agent for streaming metrics + mid-Task checkpoint coordination). It layers *on top of* this contract without changing it — power-users opt in, the black-box default stands.
