# Architecture Decision Records

Each file records one architectural decision: the context, the decision, the alternatives considered, and the consequences.

## When to write one

Write an ADR when a decision is:

1. **Hard to reverse:** changing your mind later costs real work.
2. **Surprising without context:** a future reader would look at the code and ask "why on earth is it like this?"
3. **A real trade-off:** there were genuine alternatives and one was picked for specific reasons.

If any of the three is missing, the decision doesn't need an ADR. A task card's **Decide first** answers usually belong in the card's History line, unless they meet all three.

## How they're used

- **When making a decision** that meets the criteria, write the ADR *before* or *alongside* the code, in the same PR.
- **When reading unfamiliar code,** check the ADRs before assuming the implementation is wrong.
- **When a later task fills in a detail an ADR left open** (e.g. T16 choosing the exact best-fit rule for ADR-0008), add it to that ADR with a History line.

## Changing an ADR

An accepted ADR states the **current** truth.

- **Small changes** (fixing a fact, adding a detail a task settled, correcting a name or a count) are **edited in place**, with a dated line under **History** saying what changed and in which task or PR.
- **Reversing or replacing** a decision needs a **new** ADR that supersedes the old one. Set the old one's status to `superseded by ADR-NNNN` and add a History line; don't otherwise rewrite it.

This replaces the earlier "append-only, never edit" rule (changed 2026-11-10), which ADR-0002's amendment had already broken in practice.

## Format

File name `NNNN-kebab-case-title.md`, four-digit sequence. Take the next free number from the index below.

```markdown
---
status: accepted | proposed | superseded by ADR-NNNN
date: YYYY-MM-DD          # when first accepted
---

# Title in Title Case

## Context
## Decision
## Why
## Alternatives considered
## Consequences            (when non-obvious)
## Revisit when            (optional)
## History
- YYYY-MM-DD: Accepted.
```

Most ADRs are 30–80 lines. Link other ADRs as `[ADR-NNNN](./NNNN-slug.md)`.

## Index

| # | Title | Status | Date |
|---|---|---|---|
| [0001](./0001-flat-master-not-hierarchical.md) | Flat Master, not hierarchical aggregation | accepted | 2026-05-20 |
| [0002](./0002-closed-membership-rooms.md) | Closed-membership Rooms via signed Invite Tokens | accepted (amended by 0014) | 2026-05-20 |
| [0003](./0003-master-on-data-plane.md) | Master on the data plane; Workers connect outbound only | accepted | 2026-05-20 |
| [0004](./0004-big-models-out-of-scope.md) | Models that don't fit one GPU are out of scope for v0.1–v0.5 | accepted | 2026-05-20 |
| [0005](./0005-roll-our-own-orchestration.md) | Roll our own orchestration, not Ray | accepted | 2026-05-20 |
| [0006](./0006-black-box-container-contract.md) | Black-box Container Contract (env-vars-in / files-out) | accepted | 2026-05-20 |
| [0007](./0007-websocket-http-transport.md) | WebSocket control channel + HTTP artifacts (not gRPC) | accepted | 2026-05-20 |
| [0008](./0008-smart-pull-scheduling.md) | Smart-pull scheduling | accepted | 2026-05-20 |
| [0009](./0009-map-search-primitives.md) | Two primitives, Map and Search, not a job-type enum | accepted | 2026-05-20 |
| [0010](./0010-wrap-optuna.md) | Wrap Optuna behind a pluggable Sampler interface | accepted | 2026-05-20 |
| [0011](./0011-tls-fingerprint-in-token.md) | TLS via self-signed cert fingerprint pinned in the Invite Token | accepted | 2026-05-20 |
| [0012](./0012-content-addressed-artifacts.md) | Content-addressed Artifacts with the Master as origin | accepted | 2026-05-20 |
| [0013](./0013-cli-design-and-observability.md) | CLI design and observability command split | accepted | 2026-05-30 |
| [0014](./0014-admin-tokens-for-submission.md) | Admin tokens for Job submission (amends 0002) | accepted | 2026-05-30 |
| [0015](./0015-master-url-separate-from-token.md) | Master URL passed separately from the token | accepted | 2026-05-30 |
| [0016](./0016-benchmark-runs-as-a-container.md) | The throughput benchmark runs as its own container | accepted | 2026-11-10 |
| [0017](./0017-python-toolchain.md) | Python toolchain: one pinned Python, one lockfile, one version per tool | accepted | 2026-11-10 |
| [0018](./0018-logging-and-events.md) | Logging, events and log shipping | accepted | 2026-11-10 |
| [0019](./0019-experiment-run-records.md) | Experiment run records and a results registry | accepted | 2026-11-10 |
| [0020](./0020-docker-is-the-verification-surface.md) | The Docker image is the verification surface | accepted | 2026-11-10 |
