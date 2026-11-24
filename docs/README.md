# Compute4Me docs

All project documentation lives here. The repo root holds only the files GitHub recognises (`README.md`, `LICENSE`, `CONTRIBUTING.md`, `CHANGELOG.md`, `SECURITY.md`) plus `CLAUDE.md` for coding assistants.

## Where to start

New to the project: follow the **[reading order in the README](../README.md#reading-order)**. This page is the full index.

| You want to… | Read |
|---|---|
| Understand the project | [../README.md](../README.md), then [architecture/overview.md](./architecture/overview.md) |
| Pick up the next piece of work | [plan.md](./plan.md), then the task's card in [tasks/](./tasks/README.md) |
| Know what v0.1 must do | [prd.md](./prd.md) |
| Design or extend a module | [architecture/](./architecture/README.md) for structure, [adr/](./adr/README.md) for rationale |
| Understand the research framing | [research/](./research/README.md) |

## What's where

| Path | Purpose | Lifecycle |
|---|---|---|
| [prd.md](./prd.md) | **What** the current milestone (v0.1) builds and when it's done: scope, user stories, NFRs, risks, acceptance criteria, eval runbook | Living for the milestone; archived to `archive/prd-vX.Y.md` when it ships |
| [plan.md](./plan.md) | **Order:** phases, task index, dependency graph, open items, Definition of Done, stubs | Living; updated whenever a task's order, scope or dependencies change; archived with the PRD |
| [tasks/](./tasks/README.md) | **How:** one card per task (background, decisions to settle, steps, tests, Docker verification, fallbacks) | Written before the task's phase; Status and History updated in the task's PR |
| [context.md](./context.md) | Canonical glossary | Living; a renamed term changes code and docs in the same PR |
| [roadmap.md](./roadmap.md) | What's deferred to v0.2 … v1.0 and why | Living; every "deferred" mention elsewhere must appear here |
| [architecture/](./architecture/README.md) | Durable structure: overview, data model, modules, wire protocol, errors, deployment, operations, test map | Amended as features land; describes what exists, with planned items marked by task |
| [adr/](./adr/README.md) | One architectural decision per file | Small changes edited in place with a History line; reversals superseded by a new ADR |
| [background/challenges-faced.md](./background/challenges-faced.md) | Real problems hit and how they were solved | Appended in the PR that solves each one |
| [research/](./research/README.md) | Related work and positioning that informed the design | Updated when the positioning changes |
| [style-guide.md](./style-guide.md) | Code, logging and docs conventions | Living |
| `archive/` | Frozen past-version PRDs and plans (empty until v0.1 ships) | Append-only |

## Outside `docs/`

| Path | Purpose |
|---|---|
| [../README.md](../README.md) | Pitch, status, reading order, intended quick start |
| [../CONTRIBUTING.md](../CONTRIBUTING.md) | Setup, task workflow, branches, PRs, CI, issues |
| [../CLAUDE.md](../CLAUDE.md) | Rules for AI coding agents |
| [../SECURITY.md](../SECURITY.md) | Threat model, the Docker socket grant, reporting |
| [../CHANGELOG.md](../CHANGELOG.md) | What changed, per release (`[Unreleased]` per PR) |
| [../tests/INDEX.md](../tests/INDEX.md) | Task → test file → markers |
| [../scripts/manual/README.md](../scripts/manual/README.md) | Manual drivers that run merged pieces on localhost |
| [../examples/](../examples/resnet18_hpo/README.md) | Sample user images honouring the Container Contract (T17) |
| [../.github/](../.github/PULL_REQUEST_TEMPLATE.md) | PR template and issue forms |

## Every file under `docs/`

- **Top level:** [prd.md](./prd.md), [plan.md](./plan.md), [context.md](./context.md), [roadmap.md](./roadmap.md), [style-guide.md](./style-guide.md)
- **[architecture/](./architecture/README.md):** [overview](./architecture/overview.md), [data-model](./architecture/data-model.md), [modules](./architecture/modules.md), [wire-protocol](./architecture/wire-protocol.md), [error-handling](./architecture/error-handling.md), [deployment](./architecture/deployment.md), [operations](./architecture/operations.md), [test-map](./architecture/test-map.md)
- **[adr/](./adr/README.md):** ADR-0001 … ADR-0021, indexed in its README
- **[tasks/](./tasks/README.md):** the card template, the [session prompt](./tasks/session-prompt.md) and one card per task (listed in the tasks README)
- **[background/](./background/challenges-faced.md):** [challenges-faced](./background/challenges-faced.md)
- **[research/](./research/README.md):** [novelty](./research/novelty.md), [related-work](./research/related-work.md)

## Conventions

- **Lowercase file names** under `docs/` (`prd.md`, not `PRD.md`).
- **Relative links** throughout (`[overview](./architecture/overview.md)`); anchors must match a real heading (checked from T28).
- **Mermaid** for every diagram, rendered locally before committing ([style-guide.md §Diagrams](./style-guide.md#diagrams)).
- **One owner per fact.** When two docs need the same content, one owns it and the other links. When they disagree, the PRD wins, and the other is fixed in the same PR.
- **Who updates what, when:** the "Documentation travels with code" table in [../CONTRIBUTING.md](../CONTRIBUTING.md#documentation-travels-with-code).
