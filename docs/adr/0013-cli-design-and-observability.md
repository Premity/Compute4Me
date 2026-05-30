---
status: accepted
---

# CLI Design and Observability Command Split

## Context

The CLI is the operator's primary surface — used for daemon lifecycle (`serve`, `worker`), token management, and observing a running fabric. Naively, "observing what's happening" is one command. In practice, distributed systems produce at least five distinct kinds of observable output (fleet topology, job progress, trial metrics, system events, container logs), each with different access patterns, refresh rates, and consumers. Conflating them is the classic tech-debt path — every CLI that started with one `status` command grew unmaintainable as users demanded "but I just want to see Y."

We also need to settle the structural shape (flat-verb vs noun-verb hierarchy vs hybrid) and the default mode (foreground vs detached) for the daemon commands, because both decisions cascade through every downstream command's naming and behavior.

## Decision

Three coupled decisions:

1. **Structure:** **flat command list** (git-style), with one nested group (`token`) for the only noun that has multiple verbs. Eight top-level commands fit in one `--help` screen.

2. **Five distinct observability commands**, not one:
   - `status` — fleet topology + Job progress summary (snapshot; `--watch` for live)
   - `progress JOB_ID` — live per-trial metrics from `progress.jsonl` (stream)
   - `logs <master|worker ID|task ID|job ID>` — stdout/stderr of a process or container (stream)
   - `events` — system-level state transitions in logfmt (stream)
   - `fetch JOB_ID` — download final result Artifacts (one-shot)

3. **Foreground-by-default** for `serve` and `worker`; `-d` to detach. The foreground stream is essentially `status --watch` + `events --follow` merged, with a sticky bottom status bar. When `stdout` is not a TTY, the output auto-switches to JSON-lines for log aggregators.

Three rendering modes for terminal glyphs:
- **Default:** Unicode arrows / dots / box-drawing (✓ ✗ ⚠ ➜).
- **`--ascii`:** plain text replacements for limited terminals, screen readers, copy-paste.
- **`--slop`:** emoji-heavy with maximum color, for users who want it.

Full surface in [wire-protocol.md §4](../architecture/wire-protocol.md).

## Why

1. **Flat structure fits the size.** Eight commands across three nouns (master, worker, token) is too small for the gh/kubectl noun-verb hierarchy to pay off. Modern noun-verb conventions assume 30+ commands; we don't have that, and the "type less" win for daily use is real. The single nested group (`token` with 3 verbs) genuinely benefits from grouping; everything else is flat.

2. **The five-command observability split avoids the One Status Command anti-pattern.** Categories differ structurally: fleet topology is a *snapshot*, container logs are a *stream*, system events are a *structured stream*, trial metrics are a *stream of typed records*, final results are *files*. Conflating any two means designing one CLI to serve incompatible use cases. The split mirrors what kubectl, docker, ray, and SLURM converged on independently.

3. **Foreground-default matches Docker convention** and removes the "did I forget to attach?" failure mode. Users expect `docker run X` to show output; they expect `compute4me serve` to do the same. `-d` is the explicit opt-out for systemd, Docker-Compose, and CI contexts.

4. **External ML-observability (W&B, MLflow, TensorBoard) stays out of Compute4Me's CLI.** The user container talks to those services directly via env var pass-through ([wire-protocol.md §1](../architecture/wire-protocol.md)). The orchestrator's job is not to break ML-experiment-observability; integrating it would create overlapping concept hierarchies (Compute4Me's "Job" vs W&B's "Run") that confuse rather than help.

## Alternatives considered

- **Pure noun-verb (`compute4me master serve` / `compute4me job status JOB_ID` / `compute4me job results JOB_ID`):** more discoverable for large CLIs. Rejected because our surface is small enough that the typing overhead exceeds the discoverability benefit. Re-evaluate at v0.6+ if the surface grows.

- **One `status` command, modes via flags (`compute4me status --logs`, `--events`, `--progress`):** keeps `--help` short. Rejected because flag-driven modes lead to incoherent flag interactions ("can I `--logs --events` at the same time?"), and the streaming/snapshot split doesn't map cleanly onto flags.

- **Detached-by-default `serve`/`worker` with `-f` for foreground:** matches systemd's expectation. Rejected because the dominant first-time UX is interactive, and "did I detach the daemon I needed to watch?" is a worse failure mode than "I forgot `-d` for my systemd unit." Systemd users learn `-d` once.

- **Tight W&B integration (auto-register a W&B project per Job, surface live curves in `status`):** tempting but a maintenance trap. W&B's API churns; their concept hierarchy differs from ours; users with non-W&B preferences would be second-class. Loose integration via env pass-through scales to any upstream.

## Consequences

- Every command's `--help` page is short and scannable. `compute4me --help` shows the full surface.
- The `events` and `progress` streams are *new commands* that didn't exist in the original PRD sketch — added with this ADR.
- Adding new commands later is cheap as long as they fit the existing categories (extending `events --type X` or `logs <target>` instead of inventing a new command).
- The `--slop` flag is a load-bearing joke: the explicit name signals "this is opt-in noise" and prevents the default from drifting toward emoji-heavy output, which would be a regression.
- Non-TTY auto-switch to JSON-lines means systemd / CI / pipelines work cleanly without flag plumbing.

## Revisit when

- The command surface grows past ~15 top-level commands (then consider migrating to noun-verb).
- Users repeatedly conflate two observability commands (sign the split is wrong).
- A real demand emerges for tighter W&B/MLflow integration that the loose env-pass model can't satisfy.
