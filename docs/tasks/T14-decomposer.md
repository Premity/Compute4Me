# T14: Job decomposer

| | |
|---|---|
| Phase | P2 |
| Size | M (3–5 h) |
| Depends on | T13 (and T02, T12 for the manifest) |
| Unblocks | T16, T23 |
| Branch | `feat/T14-decomposer` |
| Issue | — |
| Status | Not started |

## Why this task exists

The Scheduler places **Tasks**, but users submit **Jobs**. The decomposer turns a Search Job into config-Tasks (through the Sampler) and a Map Job into shard-Tasks, and stamps each Task with the `requires` the cost model and the feasibility filter run on. Without honest `requires`, the "DL-aware scheduler" has nothing to be aware of.

## Background you need

- **Types:** `SearchJobSpec`, `MapJobSpec`, `ShardStrategy`, `Task{id, job_id, args, input_refs, requires, attempts}`, `TaskRequires{min_vram_mb, gpu_required, est_work_units}` ([data-model.md](../architecture/data-model.md#internal-task-representation)).
- **The gap:** neither job spec has a field for VRAM, GPU need or work. The cost model is `work_units / throughput` (ADR-0008); if every Task has `work_units = 1`, "fast Worker gets the biggest Task" means nothing for Search, and the VRAM filter never filters.
- **Search arrives over time** (ADR-0008 "Pull handles dynamic arrival"): TPE needs results before proposing good configs, so the decomposer must not ask all `n_trials` at submission. It asks as capacity frees up.
- **Map shards** come from T12's manifest: `n_shards` index ranges over the manifest's entries (balanced by **bytes**, not count, so work units are comparable), or the user's file lists.

## Decide first

1. **Where `requires` come from.** (plan.md Open items.)
   - **A. Optional `resources` on both specs (Recommendation):** `resources: {min_vram_mb: int = 0, gpu_required: bool = True, work_units: float = 1.0, work_units_from: str | None = None}`. For Search, `work_units_from="epochs"` multiplies `work_units` by that config value per trial (big trials differ by epochs/batch/model size); for Map, work units scale with shard **bytes**. Additive and optional, so existing specs stay valid.
   - **B. Infer from history:** learn per-config runtimes as trials finish. That is v0.2's calibrated cost model, not v0.1.
   - **C. Constant per Job:** simplest, but makes heterogeneity-aware placement a no-op within a Job.
   Update data-model, wire-protocol §5.2 and context (**Task**).
2. **How many asks are outstanding.** Recommendation: the decomposer is a stateful `JobPlan` with `next_tasks(k) -> list[Task]`; the scheduler asks for `k = idle Workers + 1` when its queue for the Job runs low. Map plans emit all shard-Tasks at once.
3. **Task ids.** Recommendation: `t_<job-short>_<nnnn>` (stable, sortable, readable in logs).

## Steps

1. `resources` model and fields on both specs (types.py); validation.
2. `master/decomposer.py`: `plan(job) -> JobPlan`; `SearchPlan` (wraps a Sampler; `next_tasks(k)`, `on_result(task_id, value)` → `tell`); `MapPlan` (all shard-Tasks, byte-balanced `index-range` and verbatim `file-list`; `whole` → 1 Task).
3. Each Task's `input_refs`: the Job's `inputs` (whole) plus, for Map, the dataset with its shard.
4. Docs: modules.md (JobPlan), data-model.md, wire-protocol §5.2, context.md.

## Outputs

`types.py`, `master/decomposer.py`, docs, CHANGELOG.

## Tests

| File | Markers | Proves |
|---|---|---|
| `tests/unit/test_decomposer.py` | `task("T14")`, `unit` | seeded Search emits the expected configs; `work_units_from` scales per trial; `next_tasks` never exceeds `n_trials`; Map emits exactly `n_shards` Tasks, non-overlapping and exhaustive, byte-balanced within one file's size; `whole` → 1 Task |

## Verify in Docker

No image impact beyond `make image-smoke`.

## Done when

- [ ] `resources` decided and on both specs, documented.
- [ ] Search plans ask lazily; Map plans shard exactly.
- [ ] Every Task carries meaningful `requires`.

## If this fails

- **Byte-balanced index ranges are fiddly with very uneven file sizes:** fall back to count-balanced ranges and put the byte total in `est_work_units`; the cost model still sees the imbalance.

## References

- [ADR-0008](../adr/0008-smart-pull-scheduling.md), [ADR-0009](../adr/0009-map-search-primitives.md), [ADR-0010](../adr/0010-wrap-optuna.md), T12 card (manifest)

## History

- 2026-11-10: Card written (planning rewrite).
