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
| **[test-map.md](./test-map.md)** | Which checks run where (hooks, CI jobs, local, Docker host, real fleet) and the commands that run them. |

## Diagrams

Every diagram, by kind. *As built* diagrams show the code today; *Planned* ones show a card's recommendation and change when the card is settled.

| Kind | Diagram | Where | Status |
|---|---|---|---|
| Context | Actors and external systems | [overview.md](./overview.md#system-context) | Concept |
| Component | Master and Worker components, sibling containers | [overview.md](./overview.md#components) | Target |
| Deployment | Hosts, containers, ports, volumes, socket, GPU | [deployment.md](./deployment.md#topology) | Target |
| Package | Package map and import rules | [modules.md](./modules.md#package-map) | As built (T09) |
| Class | Control-plane classes | [modules.md](./modules.md#classes-as-built) | As built (T09) |
| Class (interfaces) | Sampler, JobPlan, Scheduler, cost model, ArtifactStore, EventLog | [modules.md](./modules.md#interfaces-planned-for-p2) | Planned (T11–T17, T29) |
| Class | Pydantic model map | [data-model.md](./data-model.md#model-map) | As built (T02–T09) |
| Class | Wire message unions | [wire-protocol.md](./wire-protocol.md#message-models) | As built (T04) |
| ER | SQLite schema | [data-model.md](./data-model.md#master-state-store-sqlite) | As built (T03) |
| Interface | Container Contract (env in, files out) | [wire-protocol.md](./wire-protocol.md#1-container-contract-masterworker--user-image) | Spec (ADR-0006) |
| Interface | CLI command tree | [wire-protocol.md](./wire-protocol.md#41-command-surface) | Spec, status per command |
| Sequence | Join | [overview.md](./overview.md#join) | Target |
| Sequence | Submit, schedule, run, collect | [overview.md](./overview.md#submit-schedule-run-collect) | Target |
| Sequence | A Worker dies mid-Task | [overview.md](./overview.md#a-worker-dies-mid-task) | Planned (T18) |
| Sequence | The Master restarts | [overview.md](./overview.md#the-master-restarts) | Planned (T20) |
| Sequence | Control-channel lifecycle | [wire-protocol.md](./wire-protocol.md#connection-lifecycle) | Target |
| Sequence | Task execution on a Worker | [modules.md](./modules.md#task-execution-on-a-worker) | Planned (T12, T17) |
| Sequence | Fetching a shard | [wire-protocol.md](./wire-protocol.md#fetching-a-shard) | Planned (T11, T12) |
| State | Worker, Task, Job lifecycles | [overview.md](./overview.md#lifecycle-states) | Target |
| State | Worker daemon connection | [modules.md](./modules.md#worker-daemon--workerdaemonpy) | As built (T08) |
| Activity | Scheduler decision | [modules.md](./modules.md#scheduler--masterschedulerpy) | Planned (T15, T16) |
| Activity | Failure handling | [modules.md](./modules.md#failure-controller--masterfailurepy) | Planned (T18, T19) |
| Dependency | Task graph | [../plan.md](../plan.md#task-dependency-graph) | Plan |

## How these docs relate to PRD and ADRs

- **PRD** says *what to build and when* (scope, acceptance criteria, per-version task lists).
- **Architecture docs** say *how it's structured* (the durable bits — data, modules, wire). The PRD links into these rather than duplicating them.
- **ADRs** say *why a specific structural choice was made* and what alternatives were rejected.

When v0.2 begins, the PRD is rewritten for the new scope; these architecture docs are amended additively (new modules / new schemas / new wire messages added as features grow). The diff in any single version is small relative to the durable structure.

## Conventions

- Terminology follows [../context.md](../context.md). Terms like **Fabric**, **Master**, **Worker**, **Room**, **Capability Profile** are canonical.
- Code signatures shown in Python (the implementation language) but are intentionally *interface-shaped* — implementations can change without invalidating these docs as long as the interface holds.
- Diagrams are **Mermaid** blocks inside the Markdown (diffable, rendered by GitHub); render them locally before committing ([style-guide.md](../style-guide.md#diagrams)). A PR that changes what a diagram shows updates the diagram and, for an *As built* one, its task label.
