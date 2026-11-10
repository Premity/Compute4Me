# T15: Cost model

| | |
|---|---|
| Phase | P2 |
| Size | M (3–5 h) |
| Depends on | T02, T30 (and T14 for `resources`, T10 for bandwidth) |
| Unblocks | T16 |
| Branch | `feat/T15-cost-model` |
| Issue | — |
| Status | Not started |

## Why this task exists

Smart-pull's "best fit" needs an estimate of how long a Task would take on a given Worker, and whether it can run there at all. [ADR-0008](../adr/0008-smart-pull-scheduling.md) asks for coarse (within ~2×) estimates: enough to beat round-robin. This task writes those two pure functions, including what to do when a Worker has no benchmark figure (T30 made `throughput_ref` optional).

## Background you need

- **Interface** ([modules.md](../architecture/modules.md#cost-model--mastercost_modelpy)): `estimate(task, worker) -> seconds`, `feasible(task, worker) -> bool`. Pure, no I/O.
- **Inputs:** `TaskRequires{min_vram_mb, gpu_required, est_work_units}` (T14); `CapabilityProfile{gpu.model, gpu.vram_total_mb, gpu.vram_free_mb, throughput_ref: float | None, bandwidth_to_master_mbps, datasets_cached}` (T09, T10, T30).
- **Units:** `throughput_ref` is ResNet18 samples/sec, a *relative* speed. `est_work_units` is in the user's units. So `estimate` is meaningful for **ranking** Workers and Tasks, not as wall-clock seconds, until v0.2 calibrates it. Say so in the docstring.
- **No benchmark:** the T30 decision is a fallback instead of excluding the Worker. Don't invent per-GPU throughput numbers: use measured data only.

## Decide first

1. **Rate when `throughput_ref is None`.** Recommendation: the median `throughput_ref` of other Workers **with the same `gpu.model`** in the Room; otherwise the Room median; otherwise 1.0. Log the source. (A static GPU table would need numbers we haven't measured; it can come later from our own bench runs.)
2. **VRAM for feasibility.** Recommendation: `vram_free_mb` from the latest refresh (T10), not total: a contributor's desktop may hold VRAM. OOM promotion (T18) catches the rest.
3. **Transfer term.** Recommendation: include `uncached_input_bytes × 8 / (bandwidth_mbps × 10⁶)` when bandwidth > 0 (PRD story 14). Input sizes come from the manifest/artifacts table, passed in by the caller so the function stays pure.

## Steps

1. `master/cost_model.py`: `rate(worker, room_peers) -> (value, source)`, `estimate(task, worker, *, peers, input_bytes_uncached=0) -> float`, `feasible(task, worker) -> bool` (`gpu_required` vs `gpu.model == "cpu"`, `min_vram_mb` vs free VRAM).
2. Docstrings state the unit caveat.
3. Docs: modules.md signatures, context.md (**Cost Model** fallback).

## Outputs

`master/cost_model.py`, docs, CHANGELOG.

## Tests

| File | Markers | Proves |
|---|---|---|
| `tests/unit/test_cost_model.py` | `task("T15")`, `unit` | two Workers differing only in `throughput_ref` → estimates in inverse proportion; `None` rate uses the same-GPU median, then the Room median; VRAM-short or GPU-less → infeasible; transfer term added only for uncached bytes |

## Verify in Docker

No image impact beyond `make image-smoke`.

## Done when

- [ ] Pure `estimate`/`feasible` with the fallback and transfer term, tested.
- [ ] Unit caveat documented.

## If this fails

- **The real fleet's ranking is wrong by more than 2×** (seen in T25/T26): that's v0.2's calibration thread; record the measured error in challenges-faced and the roadmap, don't tune v0.1 by hand.

## References

- [ADR-0008](../adr/0008-smart-pull-scheduling.md), [ADR-0016](../adr/0016-benchmark-runs-as-a-container.md), [roadmap v0.2](../roadmap.md#v02--scheduler-maturity--concurrency)

## History

- 2026-11-10: Card written (planning rewrite).
