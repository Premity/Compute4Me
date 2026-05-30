# Compute4Me Docs

This folder holds **all project documentation**. The repo root is kept sparse (`README.md`, `LICENSE`, `CONTRIBUTING.md`, `CHANGELOG.md`, `SECURITY.md`) so everything else lives here, organized by intent.

## Where to start

- **Just want to understand the project?** → [../README.md](../README.md), then [architecture/overview.md](./architecture/overview.md).
- **Going to contribute code?** → [../CONTRIBUTING.md](../CONTRIBUTING.md), then [prd.md](./prd.md) (current milestone).
- **Designing or extending a module?** → [architecture/](./architecture/) for structure, [adr/](./adr/) for rationale.
- **Curious about the research framing?** → [research/](./research/).

## What's where

| Path | Purpose |
|---|---|
| **[prd.md](./prd.md)** | Product Requirements Document for the **current milestone** (v0.1). Scope, user stories, T-tasks, acceptance criteria, eval plan. **Rewritten per minor version**; past versions archived to [archive/](./archive/). |
| **[context.md](./context.md)** | The canonical glossary. Definitions of **Fabric**, **Master**, **Worker**, **Room**, **Invite Token**, **Capability Profile**, **Job**, **Task**, **Artifact**, **Scheduler**, **Container Contract**, etc. |
| **[roadmap.md](./roadmap.md)** | Forward-looking registry: what's deferred to v0.2, v0.3, …, v1.0 and why. |
| **[architecture/](./architecture/)** | Durable architectural reference (system overview, data model, modules, wire protocol). Spans all versions; amended additively as features land. |
| **[adr/](./adr/)** | Architectural Decision Records — one decision per file, with context, alternatives, consequences. |
| **[research/](./research/)** | Literature-review / positioning material that informed the design. |
| **[archive/](./archive/)** | Frozen snapshots of past-version PRDs. |
| **[style-guide.md](./style-guide.md)** | Code + documentation style conventions. *Placeholder until after T01–T03 land.* |

## Documentation lifecycle

- **PRD** is *living* — it always describes the version currently in development. When v0.1.0 ships, it's archived to `archive/prd-v0.1.md` and a new `prd.md` is written for v0.2.
- **Architecture docs** are *durable* — they evolve additively as features land. The diff per version is small relative to the total surface.
- **ADRs** are *append-only* — once accepted, they're never edited (except status changes: `accepted` → `superseded by ADR-NNNN` if the decision is reversed in a future ADR).
- **CONTEXT.md** is *living* — terms are added when they enter the code; existing definitions only change with care (renaming a term cascades through code + docs).
- **ROADMAP.md** is *living* — entries are added when scope shifts; completed milestones are summarized and linked to the archived PRD.

For who-updates-what-when, see [../CONTRIBUTING.md](../CONTRIBUTING.md) — the docs-in-PR convention says doc changes travel with the code that motivates them.

## Conventions

- **Lowercase filenames** under `docs/` (`prd.md`, not `PRD.md`). Uppercase reserved for the GitHub-recognized root files (`README.md`, `LICENSE`, etc.).
- **Relative markdown links** throughout (`[overview](./architecture/overview.md)`), not absolute paths or rendered HTML.
- **ASCII diagrams** over rendered images — diffable, copy-pasteable, no external dependencies.
- **Cross-references over duplication.** When two docs need the same content, one owns it and the other links.
