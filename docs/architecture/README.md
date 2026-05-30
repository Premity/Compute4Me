# Architecture

Durable architectural reference for Compute4Me. These documents describe the system's structure, data, modules, and protocols **across versions** — they are not tied to a specific milestone. Per-milestone scope and acceptance criteria live in [../prd.md](../prd.md); milestone-by-milestone evolution lives in [../roadmap.md](../roadmap.md); single architectural decisions and their rationale live in [../adr/](../adr/).

## What's here

| File | What it covers |
|---|---|
| **[overview.md](./overview.md)** | The system in one diagram + the role of each component. Start here. |
| **[data-model.md](./data-model.md)** | Master state store (SQLite schema) + Pydantic schemas for Capability Profile, Job specs, Token claims. |
| **[modules.md](./modules.md)** | Interface signatures for every module (Token service, Scheduler, Cost Model, Job Decomposer, Artifact Store, Failure Controller, Container Runner, etc.). |
| **[wire-protocol.md](./wire-protocol.md)** | Container Contract (Master ↔ user image), WebSocket control channel (Worker ↔ Master), HTTP artifact channel, CLI surface, Python submission API. |
| **[error-handling.md](./error-handling.md)** | Error message format, exit codes, Python exception hierarchy, what counts as an "error" vs an "event." |
| **[deployment.md](./deployment.md)** | Practical reference: volume mounts, GPU flags, Docker socket grant on Workers, multi-GPU hosts, where the CLI lives. |
| **[operations.md](./operations.md)** | Running and maintaining a deployment: backup/restore, upgrades, moving the Master, cert rotation, pausing/decommissioning Workers, multi-Room, co-location, storage growth, emergencies. |

## How these docs relate to PRD and ADRs

- **PRD** says *what to build and when* (scope, acceptance criteria, per-version task lists).
- **Architecture docs** say *how it's structured* (the durable bits — data, modules, wire). The PRD links into these rather than duplicating them.
- **ADRs** say *why a specific structural choice was made* and what alternatives were rejected.

When v0.2 begins, the PRD is rewritten for the new scope; these architecture docs are amended additively (new modules / new schemas / new wire messages added as features grow). The diff in any single version is small relative to the durable structure.

## Conventions

- Terminology follows [../context.md](../context.md). Terms like **Fabric**, **Master**, **Worker**, **Room**, **Capability Profile** are canonical.
- Code signatures shown in Python (the implementation language) but are intentionally *interface-shaped* — implementations can change without invalidating these docs as long as the interface holds.
- ASCII diagrams over rendered images (diffable in git, copy-pasteable, no external dependencies).
