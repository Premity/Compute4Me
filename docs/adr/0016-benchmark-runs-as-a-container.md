---
status: accepted
date: 2026-11-10
---

# The Throughput Benchmark Runs as Its Own Container

## Context

The Scheduler keys off `throughput_ref`, the samples/sec of a fixed ResNet18 forward/backward micro-benchmark ([ADR-0008](./0008-smart-pull-scheduling.md), [context.md](../context.md)). The benchmark needs PyTorch. T09 kept torch out of the Worker image, because real training runs in the *user's* container with its own ML stack ([ADR-0006](./0006-black-box-container-contract.md)) and torch with CUDA is several GB. It made torch an optional `bench` extra installed on the **host** by `scripts/setup-worker.sh`.

That cannot work in the documented deployment, where the Worker *is* a container. Torch installed on the host is invisible inside it; `profile()` calls the benchmark directly, so it raised `BenchmarkUnavailable` and the shipped Worker image could not join a Room at all. The setup script also picked wrong CUDA wheels (CPU torch on CUDA 13 hosts). Found on 2026-11-10 while auditing the repo ([challenges-faced.md](../background/challenges-faced.md)).

## Decision

1. The benchmark ships as a **separate image**, `ghcr.io/premity/compute4me-bench:<compute4me version>`, built from a pinned PyTorch CUDA runtime base. Its entrypoint runs the fixed benchmark and prints one JSON line.
2. The Worker runs it as a **sibling container through the host Docker socket** it already has for user Tasks, passing through exactly the GPU the Worker was given (`--gpus device=<uuid>`). CPU-only Workers run it without `--gpus`.
3. **A benchmark failure never prevents joining.** `throughput_ref` becomes `float | None` with a `throughput_note` explaining why it is missing. The cost model falls back to measured peers ([T15](../tasks/T15-cost-model.md)).
4. `C4M_BENCHMARK=skip` skips it (CI, development).
5. The `bench` extra and `scripts/setup-worker.sh` are removed.

Implemented in [T30](../tasks/T30-benchmark-container.md).

## Why

1. **It reuses a mechanism we need anyway.** Launching containers through the socket with GPU passthrough is exactly what T17 does for user Tasks; the benchmark is its simplest first customer (no volumes).
2. **CUDA matching comes free.** The image carries its CUDA runtime; the host only needs a compatible driver, the same requirement user images already have.
3. **The Worker image stays small and torch-free**, which keeps the import-hygiene rule simple ([ADR-0017](./0017-python-toolchain.md)).
4. **Same yardstick everywhere.** One pinned image means one torch and cuDNN version across the fleet, so `throughput_ref` values compare like with like within a release.

## Alternatives considered

- **A fat GPU Worker image** (torch + CUDA baked in, ~3–5 GB): simple, but every Worker pulls it even though it uses torch for 30 s, and one CUDA version is pinned for every host.
- **Benchmark optional only** (no torch anywhere; estimate from a GPU-model table and observed Task durations): no image to maintain, but it drops the measured-capability claim the scheduler paper rests on, and a static table would need numbers we haven't measured.
- **Host-installed torch** (the T09 approach): invisible to the containerised Worker; see Context.

## Consequences

- Each Worker host pulls a multi-GB image once (and again when the version changes). Pre-pulling is documented in [deployment.md](../architecture/deployment.md).
- `CapabilityProfile.throughput_ref` is optional; every consumer must handle `None` (cost model, `status`).
- The Worker depends on the registry being reachable at join time for the benchmark only; offline Workers still join with `throughput_ref=None`.

## Revisit when

- v0.2's real-time throughput (from running Tasks) makes the join-time benchmark redundant.
- Contributors' links make the pull impractical (then consider a CPU-only or smaller bench image).

## History

- 2026-11-10: Accepted (planning rewrite).
