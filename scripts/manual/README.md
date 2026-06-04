# Manual verification drivers

Throwaway-but-kept scripts that exercise a task's network/runtime surface by hand, for the
manual phase of a PR (and for re-poking a surface later). Each stands up real components on
an ephemeral localhost port — no Docker, no external network.

Run from the repo root:

```bash
uv run python scripts/manual/<script>.py
```

| Script | Task | Exercises |
|---|---|---|
| `t07_ws.py` | T07 | `ControlServer` over TLS: a client joins, a `bandwidth_probe` is pushed, the slot is released on close. |
| `t08_join.py` | T08 | The full tracer bullet — `WorkerDaemon` joins `ControlServer`: cert pinning, `join_ack`/`worker_id`, Worker persisted, heartbeat, bad-token reject. |

These are **not** part of the package or image (only `src/compute4me` ships). They complement
the automated `tests/integration/` suite, which is the durable CI proof; the drivers are for
eyeballing the behavior live.
