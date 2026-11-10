# T13: Sampler interface + Optuna + raw list

| | |
|---|---|
| Phase | P2 |
| Size | M (3–5 h) |
| Depends on | T02 |
| Unblocks | T14 |
| Branch | `feat/T13-samplers` |
| Issue | — |
| Status | Not started |

## Why this task exists

Search Jobs need configurations to try. [ADR-0010](../adr/0010-wrap-optuna.md) wraps Optuna behind a small `Sampler` interface (plus a raw list for plain grids), so researchers keep the HPO language they already know and the Master can feed configs to Workers as they free up.

## Background you need

- **Interface sketch** ([modules.md](../architecture/modules.md#sampler-interface--mastersamplers)): `ask() -> dict`, `tell(config, value)`. Optuna's ask-and-tell API needs the **trial object** (or number) back in `tell`, so the real interface must carry an id.
- **Optuna ask/tell:** `study = optuna.create_study(direction=…, sampler=TPESampler(seed=…))`; `trial = study.ask(fixed_distributions)` returns params immediately; `study.tell(trial, value)` or `study.tell(trial, state=TrialState.FAIL)`. With a fixed seed and the same tells in the same order, the asks are deterministic.
- **Parallel asks:** smart-pull asks for several configs before earlier ones finish. Plain TPE then proposes near-duplicates; `TPESampler(constant_liar=True)` exists for this case (Optuna ≥ 2.8, **experimental** flag; check the warning in the locked version).
- **Search space on the wire:** the client re-exports `loguniform`, `uniform` and `categorical` ([wire-protocol.md §5.2](../architecture/wire-protocol.md#52-job-submission)). They must serialise into `SearchJobSpec.search_space` (JSON). Optuna provides `optuna.distributions.distribution_to_json` / `json_to_distribution`.
- **Restart (T20):** an in-memory study is lost when the Master restarts. Either rebuild it by replaying stored results (`study.add_trial(create_trial(params, distributions, value))`) or use Optuna's RDB storage on a second SQLite file.

## Decide first

1. **Interface.** Recommendation: `ask() -> Proposal(trial_id: int, config: dict)`, `tell(trial_id, value: float | None)` (None = failed), `exhausted() -> bool` (raw list ends; Optuna when `n_trials` reached). Update modules.md.
2. **Search-space wire format.** Recommendation: `{"lr": {"dist": "loguniform", "low": 1e-5, "high": 1e-2}, …}`, our own small schema validated by Pydantic and converted to Optuna distributions on the Master. That keeps Optuna's JSON format out of the public contract. `sampler="raw"` takes `list[dict]`.
3. **Restart strategy.** Recommendation: replay from the `results` table (one DB, no Optuna storage file). T20 implements it; this task exposes `OptunaSampler.restore(completed: list[(config, value)])`.

## Steps

1. `master/samplers/base.py`: `Proposal`, `Sampler` protocol.
2. `master/samplers/optuna_sampler.py`: `OptunaSampler(space, direction, seed, n_trials, constant_liar=True)` with `restore`.
3. `RawListSampler(configs)`.
4. Space schema in `types.py`; validation errors give precise messages (feeds `SubmissionError` in T23).
5. Docs: modules.md, data-model.md (space schema), ADR-0010 History if anything differs.

## Outputs

`master/samplers/*.py`, `types.py`, docs, CHANGELOG.

## Tests

| File | Markers | Proves |
|---|---|---|
| `tests/unit/test_samplers.py` | `task("T13")`, `unit` | same seed + same tells → identical asks; `tell` changes later asks (TPE after its startup trials); failed tells accepted; raw list yields exactly the configs in order, then is exhausted; `restore` reproduces the post-tell state |
| same | `task("T13")`, `unit` | an invalid space (low > high, unknown dist) raises with a precise message |

## Verify in Docker

No image impact beyond `make image-smoke` (pure Master logic).

## Done when

- [ ] Sampler protocol with Optuna and raw implementations, deterministic under a seed.
- [ ] Space schema defined, validated and documented.
- [ ] `restore` exists for T20.

## If this fails

- **`constant_liar` warnings or odd behaviour in the locked Optuna:** turn it off and cap the asks outstanding at the number of idle Workers; note it in ADR-0010 History.

## References

- [ADR-0010](../adr/0010-wrap-optuna.md); Optuna ask-and-tell: https://optuna.readthedocs.io/en/stable/tutorial/20_recipes/009_ask_and_tell.html; `TPESampler` (`constant_liar`): https://optuna.readthedocs.io/en/stable/reference/samplers/generated/optuna.samplers.TPESampler.html

## History

- 2026-11-10: Card written (planning rewrite).
