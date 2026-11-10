---
status: accepted
date: 2026-11-10
---

# Logging, Events and Log Shipping

## Context

[ADR-0013](./0013-cli-design-and-observability.md) promises five observability commands, a foreground display for `serve`/`worker`, and JSON-lines output when stdout is not a TTY. [error-handling.md §7](../architecture/error-handling.md#7-what-is-not-an-error) separates *errors* (things that ended badly) from *events* (things that happened). Nothing underneath existed: as of T09 there was no `logging` call anywhere in `src/`, no events table in the data model (so `events --since 1h` had nothing to read), and no wire message that could carry a user container's output to the Master (so `logs task <id> -f` had no source). A cert-pin failure inside the Worker's reconnect loop was retried silently.

## Decision

**1. Logging.** stdlib `logging`, one logger per module (`logging.getLogger(__name__)`). Library code never configures handlers; only CLI entry points call `compute4me.log.setup_logging(verbosity, json_output=None)`. Output goes to **stderr** (stdout stays for command results, per error-handling.md). On a TTY it uses a human format; otherwise one JSON object per line (`ts`, `level`, `logger`, `msg`, plus structured fields such as `worker_id`, `job_id`, `task_id`). Levels follow [wire-protocol.md §4.9](../architecture/wire-protocol.md#49-verbosity-levels).

**2. Redaction.** A filter on every handler replaces JWTs (anything matching the `eyJ….….…` shape) with `eyJ…<jti>`, and code never logs signing keys or Job `env={...}` values. The repository is public, and bug reports paste logs.

**3. Events.** State transitions of fabric objects (`worker_joined`, `task_assigned`, `task_failed`, …) are typed `Event` records with a closed `type` set. The Master persists them in an `events` table and also logs them at INFO. Heartbeats and other periodic traffic are DEBUG logs, never events. Workers do not keep their own event store; the Master's view is the record.

**4. Log shipping** (implemented in T17, read by T24). A Task's container stdout/stderr is streamed Worker → Master as `task_log` messages, batched (≤ 1 s) and rate-capped per Task, with a marker when lines are dropped. On completion the full log is uploaded as a Task output Artifact. The Master keeps a bounded in-memory tail per running Task for `logs -f` and serves finished logs from the Artifact.

Implemented in [T29](../tasks/T29-logging-events.md) (1–3) and [T17](../tasks/T17-runner-and-e2e.md) (4).

## Why

1. **The stdlib is enough.** JSON formatting and filtering are ~100 lines; a structured-logging dependency would add a second API for every contributor to learn.
2. **Events need to be queryable later**, so they need storage; logs only need to be readable now. Keeping them separate stops the events table from filling with heartbeats.
3. **Shipping logs over the existing control channel** keeps the outbound-only network model ([ADR-0003](./0003-master-on-data-plane.md)); the rate cap protects the channel's heartbeats from a container that prints in a tight loop.

## Alternatives considered

- **structlog or loguru:** nicer APIs, but another dependency, and stdlib `logging` is what library users and pytest's `caplog` expect.
- **Events derived from logs** (parse log lines for `events`): no table, but a typo in a log message breaks a query, and filtering by type needs a schema anyway.
- **Logs only as Artifacts at Task end:** simple, but `logs -f` on a running Task (ADR-0013) becomes impossible.

## Consequences

- Every new state transition adds an event type (a small Literal change) and a log line.
- The `events` table grows without bound in v0.1; [operations.md §6](../architecture/operations.md) covers pruning by hand.
- `task_log` adds Master memory per running Task (bounded tail) and some control-channel traffic (capped).

## History

- 2026-11-10: Accepted (planning rewrite).
