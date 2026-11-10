# T16: Smart-pull scheduler

| | |
|---|---|
| Phase | P2 |
| Size | L (5–8 h) |
| Depends on | T14, T15 |
| Unblocks | T17, T18, T20, T27 |
| Branch | `feat/T16-scheduler` |
| Issue | — |
| Status | Not started |

## Why this task exists

This is the project's research contribution. When a Worker becomes free, the Master hands it the **best-fit eligible** Task: feasible on that Worker, preferring cached inputs, fast Workers taking the biggest Tasks ([ADR-0008](../adr/0008-smart-pull-scheduling.md)). T26 and T27 measure exactly this logic against Ray and round-robin, so it must be precise, deterministic and pure.

## Background you need

- **Interface** ([modules.md](../architecture/modules.md#scheduler--masterschedulerpy)): `enqueue(tasks)`, `next_task_for(worker_id) -> Task | None`, `on_task_done`, `on_task_failed`. "Pure given the pending queue + Capability Profiles" means no network and no clock: inputs in, decision out.
- **The problem class:** scheduling on *unrelated parallel machines* (R‖Cmax), NP-hard. Pull-based greedy rules are the practical choice; the classic offline intuition is LPT ("longest processing time first to the machine that finishes it earliest").
- **"Fast Worker gets the biggest Task" is ambiguous** in a pull system. When a slow Worker frees up first, should it take the biggest Task (FIFO-like) or leave it for a fast Worker that frees up soon? That choice is the algorithm, so it must be written down.
- **One Job at a time per Room, FIFO** (v0.1). Search Tasks arrive lazily from `JobPlan.next_tasks(k)` (T14).
- **Determinism:** T27 replays the scheduler on synthetic fleets with a seed, so every tie must break deterministically (e.g. by Task id).

## Decide first

1. **The best-fit rule.**
   - **A. Rank matching (Recommendation):** among feasible Tasks (after the locality preference), rank the free Worker's rate among the Room's connected, non-quarantined Workers as a quantile *q* (fastest = 1.0), and give it the Task at quantile *q* of the pending Tasks sorted by `est_work_units`. Fast → biggest, slow → smallest, and nobody waits. Simple to explain in the paper; O(n log n).
   - **B. Earliest-completion check:** give the biggest Task to the free Worker only if no faster Worker would *finish* it sooner, accounting for when that Worker frees up (needs predicted free times). Closer to LPT, but needs estimates of running Tasks' remaining time.
   - **C. Plain greedy:** the biggest feasible Task to whoever pulls. The baseline, not the contribution.
   Recommendation A for v0.1. Implement C too, as the internal `round_robin`/`greedy` baselines T27 needs. Record the rule in ADR-0008 History.
2. **Locality strength.** Recommendation: lexicographic: a Task whose inputs the Worker has cached beats any uncached Task, then rank matching inside each group. Simple, explainable, testable.

## Steps

1. `master/scheduler.py`: `Scheduler(policy="smart")` holding per-Room FIFO Jobs and a pending set; `next_task_for(worker, fleet) -> Task | None`; `enqueue`, `on_task_done`, `on_task_failed` (re-enqueue with `attempts + 1`; T18 adds the policy).
2. Policies as small pure functions (`smart`, `greedy`, `round_robin`, `random(seed)`) sharing one signature, for T27.
3. Wire it into the Master: on `join_ack` or `task_result`, an idle Worker pulls; push `task_assign` (T17 handles the Worker side). Emit `task_assigned` with the estimate and the policy reason.
4. Docs: modules.md, ADR-0008 History (the exact rule), context.md (**Scheduler**).

## Outputs

`master/scheduler.py`, Master wiring in `master/server.py`, docs, CHANGELOG.

## Tests

| File | Markers | Proves |
|---|---|---|
| `tests/unit/test_scheduler.py` | `task("T16")`, `unit` | fastest Worker gets the biggest pending Task; slowest gets the smallest; a VRAM-infeasible Task is never assigned; a Worker with cached inputs gets that Task over a bigger uncached one; the queue empties exactly once (each Task assigned once); FIFO across Jobs; identical inputs → identical decisions |
| `tests/unit/test_scheduler_sim.py` | `task("T16")`, `unit`, `slow` if > 5 s | on a seeded synthetic fleet with 4× speed skew, `smart` makespan < `greedy` < `round_robin` (a cheap preview of T27) |

## Verify in Docker

No new image surface until T17 dispatches; run `make image-smoke`.

## Done when

- [ ] The rule is decided, implemented, documented in ADR-0008, and tested on every property above.
- [ ] Baseline policies exist behind the same interface.
- [ ] `task_assigned` events carry estimate and reason.

## If this fails

- **Rank matching starves big Tasks when only slow Workers are connected:** when every connected Worker is "slow", *q* is computed among connected Workers only, so the fastest connected Worker still gets the biggest Task; add a test for it.
- **The synthetic preview doesn't beat greedy:** check that `est_work_units` actually varies in the generated Tasks before touching the rule (with constant work, nothing can beat greedy).

## References

- [ADR-0008](../adr/0008-smart-pull-scheduling.md), [ADR-0005](../adr/0005-roll-our-own-orchestration.md), [research/novelty.md](../research/novelty.md) (Gap 2)
- Graham, "Bounds on multiprocessing timing anomalies" (1969), the LPT rule

## History

- 2026-11-10: Card written (planning rewrite).
