---
status: accepted
date: 2026-11-10
---

# Experiment Run Records and a Results Registry

## Context

v0.1 is also the substrate for a paper: a 3-arm comparison (Ray default, Ray with manual labels, Compute4Me) on a real heterogeneous fleet, plus a simulation at 10/50/200 Workers ([prd.md §9](../prd.md#9-eval--research-runbook), T26, T27). PRD acceptance asks for numbers "reproducible across two runs within noise". Nothing in the design said how a run is recorded, so the default would be hand-named result folders. A sibling project tried that and abandoned it (`v2`, `v3_final`, `v3_final_FIXED`: nobody could say which code and fleet produced which number).

## Decision

1. **Every eval script creates a run folder automatically:** `runs/<YYYY-MM-DD_HHMM>_<name>_<git short hash>[-dirty]/`. Nobody names or numbers anything by hand.
2. Each folder holds:
   - `config.yaml` (resolved);
   - `git.txt` (commit, branch, dirty flag, changed files);
   - `env.txt` (Python, OS, Docker and driver versions, compute4me version);
   - **`fleet.json`** (every Worker's Capability Profile at the start of the run, plus the Room and bench image tag);
   - `log.txt` (everything the script printed, with an end-status line);
   - the results (`results.csv`, `summary.json`, figures).
3. `runs/index.csv` gets one line per run (id, time, name, git, dirty, host, note).
4. `results/registry.yaml` (in git) maps names to official run ids. The paper's tables and figures read **only** from the registry. A test rejects any registered run with a `-dirty` suffix.
5. `runs/` is gitignored; official runs are archived with the release that reports them.

Implemented in T32 (stub in [plan.md](../plan.md#t32-experiment-run-records--results-registry-p5-m)), before T26.

## Why

1. **Traceability:** every number links to the code, config, fleet and log that produced it.
2. **The fleet is part of the experiment.** A makespan means nothing without knowing which GPUs were connected and what each benchmarked at; `fleet.json` makes that explicit.
3. **Dirty runs can't be reproduced**, so they can't be reported.

## Alternatives considered

- **MLflow or W&B for eval runs:** good for training curves, but the eval is a scheduler measurement, not a training run; a folder plus a registry is simpler and works offline.
- **Results only in the PR description:** not machine-readable, and it lacks the fleet snapshot.

## Consequences

- Eval scripts must go through the run-folder helper (a review checklist item).
- Commit before any run you might report.

## History

- 2026-11-10: Accepted (planning rewrite). Pattern taken from the Fovea project's ADR-0002.
