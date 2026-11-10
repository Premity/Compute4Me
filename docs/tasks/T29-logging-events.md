# T29: Logging and event foundation

| | |
|---|---|
| Phase | P1 |
| Size | L (5–8 h) |
| Depends on | T28 |
| Unblocks | T31 (foreground output of `serve`/`worker`), T18, T24, T32 |
| Branch | `feat/T29-logging-events` |
| Issue | — |
| Status | Not started |

## Why this task exists

There is not one `logging` call in `src/`. A Master and Workers talking over TLS across NATs will fail in ways only a log explains. Today, a cert-pin mismatch inside `WorkerDaemon.run()` is retried with backoff and **no message at all** ([daemon.py:187](../../src/compute4me/worker/daemon.py#L187)), and a malformed frame is dropped silently ([server.py:220](../../src/compute4me/master/server.py#L220)). Meanwhile [ADR-0013](../adr/0013-cli-design-and-observability.md) promises an `events` stream, `logs`, JSON-lines when stdout isn't a TTY, and a live foreground display, and T24 assumes they exist. This task builds the floor all of that stands on, before T31 makes `serve` and `worker` real processes whose output people read.

## Background you need

- **The decision record is [ADR-0018](../adr/0018-logging-and-events.md).** Summary: stdlib `logging` everywhere (one logger per module, `logging.getLogger(__name__)`); one setup function called only by CLI entry points; a human formatter on a TTY and a JSON-lines formatter otherwise; a redaction filter; and a separate, typed **Event** record for state transitions, persisted in an `events` table and also logged.
- **Logs vs events** ([error-handling.md §7](../architecture/error-handling.md#7-what-is-not-an-error)): *events* are things that happened to fabric objects (`worker_joined`, `task_assigned`, `task_failed`) and are queryable later (`events --since 1h --type …`). *Logs* are a process's diagnostic narrative (`retrying connect in 4s: [SSL] …`). An event is always also logged; most log lines are not events.
- **Levels** ([wire-protocol.md §4.9](../architecture/wire-protocol.md#49-verbosity-levels)): `-q` → WARNING, default → INFO, `-v` → DEBUG for `compute4me.*`, `-vv`/`--debug`/`C4M_DEBUG=1` → DEBUG plus per-message wire dumps (logger `compute4me.wire`).
- **Secrets:** an Invite Token is a JWT and always starts `eyJ`. The redaction filter must replace any `eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*` with `eyJ…<jti or "redacted">`, and never log `signing_key` or `env={...}` values. The repo is public and bug reports paste logs.
- **Library etiquette:** `compute4me` modules never call `basicConfig` or add handlers; only `setup_logging()` does, and only the CLI calls it. Tests use pytest's `caplog`.
- **SQLite:** the state store applies its schema idempotently on construction ([state.py](../../src/compute4me/master/state.py)); add the `events` table there.
- `rich` is already a dependency (ADR-0013) but **don't** build the live display here. Plain handlers only; T24 adds `rich.live`.

## Decide first

1. **Module name.** Recommendation: `compute4me/log.py` (`setup_logging`, `RedactingFilter`, `JsonFormatter`) and `compute4me/events.py` (`Event`, `EventType`, `EventLog`). Avoid `compute4me/logging.py`, which shadows the stdlib module inside the package.
2. **Event type set for v0.1.** Recommendation: a `Literal` of `worker_joined`, `worker_rejected`, `worker_left`, `worker_down`, `worker_quarantined`, `worker_restored`, `job_submitted`, `job_started`, `job_completed`, `job_cancelled`, `task_assigned`, `task_succeeded`, `task_retry`, `task_failed`, `profile_updated`. This task only emits the first four; later tasks emit theirs.
3. **Where the Worker's events go.** Recommendation: a Worker logs locally (stderr) but does **not** keep its own events table. Master-observed transitions are the record. Worker-side detail reaches the Master later through `task_result.error` and log shipping (ADR-0018 §Log shipping, T17).

## Steps

1. `compute4me/log.py`: `setup_logging(verbosity: int, json_output: bool | None = None)` (None = auto: JSON when `not sys.stderr.isatty()`); `JsonFormatter` (keys: `ts` ISO-8601 UTC, `level`, `logger`, `msg`, plus any `extra=` fields); a human formatter (`HH:MM:SS  LEVEL  logger: msg`); `RedactingFilter` attached to the handler.
2. `compute4me/events.py`: `Event(BaseModel)` with `id`, `ts`, `type: EventType`, `room_id`, `worker_id`, `job_id`, `task_id` (optional) and `fields: JsonObject`; `EventLog(store, logger)` with `emit(type, **ids_and_fields) -> Event` that persists and logs at INFO with the ids as `extra`.
3. State store: `events` table (`id`, `ts`, `type`, `room_id`, `worker_id`, `job_id`, `task_id`, `fields_json`, index on `(ts)` and `(type, ts)`); `save_event`, `load_events(since=None, types=None, limit=None)`.
4. Instrument the existing code:
   - `ControlServer`: `worker_joined` (with `worker_id`, `gpu.model`, `throughput_ref`), `worker_rejected` (reason; no token text), `worker_left`; DEBUG for every parsed frame; WARNING for a dropped malformed frame (type + first 200 chars, redacted).
   - `WorkerDaemon`: INFO on connect/join/ack; WARNING with the exception text and next delay on each reconnect; **ERROR for `CertPinError`** naming expected vs got fingerprint (it is security-relevant, see [error-handling.md §2](../architecture/error-handling.md#cert-fingerprint-mismatch-security-critical)).
   - `TokenService`: INFO on issue (jti, room, max_workers, admin, expiry) and revoke.
5. Docs: data-model (`events` table), modules.md (`log`, `events`), style-guide §Logging, context.md (**Event** term), ADR-0018 History if anything changed.

## Outputs

`src/compute4me/log.py`, `src/compute4me/events.py`, `master/state.py` (events table), instrumented `master/server.py`, `master/tokens.py`, `worker/daemon.py`, docs above, CHANGELOG.

## Tests

| File | Markers | Proves |
|---|---|---|
| `tests/unit/test_log.py` | `task("T29")`, `unit` | JSON formatter emits one valid JSON object per line with the extras; auto mode picks JSON for a non-TTY stream; verbosity → level mapping |
| `tests/unit/test_log.py::…redact…` | same | a JWT in a message or an `extra` field never reaches the output; the jti is kept |
| `tests/unit/test_events.py` | `task("T29")`, `unit` | emit persists and logs; `load_events(since, types)` filters; schema is idempotent on reopen |
| `tests/integration/test_daemon_join.py` (extend) | `task("T29")`, `integration` | a join produces a `worker_joined` row; a bad token produces `worker_rejected` with no token text in `caplog` |

## Verify in Docker

No new entry point yet (T31 wires `serve`/`worker`). Run `make image-smoke`, and check that the image still has no torch: `docker run --rm --entrypoint python $IMAGE -c "import compute4me.log, compute4me.events"`.

## Done when

- [ ] `setup_logging` and the formatters exist and are tested; library modules never configure handlers.
- [ ] Redaction is proven by a test.
- [ ] `events` table, `EventLog.emit`, `load_events` exist and are tested.
- [ ] Server, daemon and token service are instrumented; the cert-pin failure path logs an ERROR with both fingerprints.
- [ ] style-guide has a Logging section; data-model, modules and context are updated.

## If this fails

- **Writing events on every heartbeat bloats SQLite:** heartbeats are logs (DEBUG), never events; only state *transitions* are events.
- **`caplog` misses records because a handler isn't propagating:** don't set `propagate = False` on `compute4me` loggers; attach handlers to the root logger in `setup_logging` only.

## References

- [ADR-0018](../adr/0018-logging-and-events.md), [ADR-0013](../adr/0013-cli-design-and-observability.md), [error-handling.md](../architecture/error-handling.md), [wire-protocol.md §4.3, §4.9](../architecture/wire-protocol.md#4-cli)
- Python logging HOWTO, "Configuring logging for a library": https://docs.python.org/3/howto/logging.html#configuring-logging-for-a-library

## History

- 2026-11-10: Card written (planning rewrite).
