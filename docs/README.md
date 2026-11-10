# Compute4Me docs

All project documentation lives here. The repo root holds only the files GitHub recognises (`README.md`, `LICENSE`, `CONTRIBUTING.md`, `CHANGELOG.md`, `SECURITY.md`) plus `CLAUDE.md` for coding assistants.

## Where to start

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
| [archive/](./archive/) | Frozen past-version PRDs and plans | Append-only |

## Conventions

- **Lowercase file names** under `docs/` (`prd.md`, not `PRD.md`).
- **Relative links** throughout (`[overview](./architecture/overview.md)`); anchors must match a real heading (checked from T28).
- **Mermaid** for every diagram, rendered locally before committing ([style-guide.md §Diagrams](./style-guide.md#diagrams)).
- **One owner per fact.** When two docs need the same content, one owns it and the other links. When they disagree, the PRD wins, and the other is fixed in the same PR.
- **Who updates what, when:** the "Documentation travels with code" table in [../CONTRIBUTING.md](../CONTRIBUTING.md#documentation-travels-with-code).
