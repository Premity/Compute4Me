# T31: Runnable `serve` / `token issue` / `worker` + compose join smoke

| | |
|---|---|
| Phase | P1 |
| Size | L (5–8 h) |
| Depends on | T08, T29, T30 |
| Unblocks | T10, T11, and Docker verification for every later task |
| Branch | `feat/T31-runnable-cli` |
| Issue | — |
| Status | Not started |

## Why this task exists

After nine tasks, `compute4me serve`, `worker` and `token issue` still raise `NotImplementedError` ([cli.py](../../src/compute4me/cli.py)); they were scheduled for T22 in P4. So the P1 tracer bullet ("a Worker joins; the Master records its profile") exists only inside pytest, and every PR since T01 says "No Docker rebuild needed" because there is nothing in the image to run. This task wires the **minimum** CLI over the components that already exist, and adds a `docker compose` smoke test to CI in which a real Worker container joins a real Master container. From here on, every task can be verified the way users will run it ([ADR-0020](../adr/0020-docker-is-the-verification-surface.md)). T22 keeps the full UX (rendering modes, `--watch`, exit-code polish, the other commands).

## Background you need

- **Components to wire (read them first):**
  - `master/server.py`: `ensure_cert(data_dir) -> MasterCert`, `ControlServer(tokens, cert, store)`, `await server.serve(host, port)`, `await server.close()`.
  - `master/tokens.py`: `TokenService(signing_key, cert_fp, store)`, `issue(room, max_workers, ttl, admin=…)`.
  - `master/state.py`: `StateStore(db_path)`, `save_room(...)`.
  - `worker/daemon.py`: `WorkerDaemon(master_url, token, cert_fp, profile)`, `await run()`; `JoinRejected` is terminal.
  - `worker/profiler.py`: `profile(data_dir=…, cache_dir=…)` (never raises after T30).
  - `log.setup_logging`, `events.EventLog` (T29).
- **Gap: the JWT signing key is never persisted.** `TokenService` takes it as an argument, but nothing creates or stores it. Tokens must survive a restart, so the key lives in the data volume beside the cert: `ensure_signing_key(data_dir)` writes 32 random bytes (hex) to `signing.key`, mode `0600`, and reuses it afterwards (the same pattern as `ensure_cert`).
- **How `token issue` reaches a running Master:** the README's operator flow is `docker exec c4m compute4me token issue …`. That is a **second process in the same container**, so `token issue` is a *local* command: it opens the same `master.db`, cert and signing key in `C4M_DATA_DIR` and signs locally. Two processes on one SQLite file need WAL mode and a busy timeout. (This works for `issue` because the serving process only checks signature and revocation; `revoke` from a second process would not update the server's in-memory set, which is T22's problem and noted in its stub.)
- **The Worker needs `cert_fp` before it can connect**, and it can't verify the token's HS256 signature (only the Master holds the key). It reads `master_cert_fp` from the token's payload **without verifying** (base64url decode of the middle segment). That is safe: if the token was tampered with, the Master rejects the join anyway.
- **Container gotchas:**
  - *PID 1 and SIGTERM:* Python running as PID 1 does not get the default SIGTERM disposition, so `docker stop` waits 10 s and then SIGKILLs. Either install handlers (`loop.add_signal_handler(SIGTERM, …)`) for a clean shutdown (close the server, release slots, close the Worker socket), or run with `docker run --init`. Do the handlers; recommend `--init` in the docs too.
  - *Buffered output:* set `PYTHONUNBUFFERED=1` in the Dockerfile so `docker logs -f` shows lines immediately.
  - *Hostname vs cert:* in compose the Worker dials `wss://master:8443`. Hostname verification is off by design (pinning, ADR-0011), so the self-signed cert's subject doesn't need to match.

## Decide first

1. **Flags for this task (the rest is T22).** Recommendation:
   - `serve --room ROOM [--data-dir DIR] [--bind HOST:PORT] [-v|-q]`
   - `token issue --room ROOM [--max-workers N] [--ttl 30d] [--admin] [--data-dir DIR]`, printing **only** the token on stdout (scriptable), with details on stderr
   - `worker [--master URL] [--token T] [--cache-dir DIR] [--data-dir DIR] [-v|-q]`, falling back to `C4M_MASTER` / `C4M_TOKEN` / `C4M_*_DIR`

   Foreground only; no `-d` (Docker's own `-d` covers it until T22).
2. **Smoke assertion.** Recommendation: the Master runs with JSON logs (non-TTY in CI), and the smoke script waits up to 60 s for a line with `"event": "worker_joined"`. It then checks `master.db` through `docker compose exec master python -c …` for one `workers` row with `status='idle'`. That needs no `status` command (T24).
3. **Where the smoke script lives.** Recommendation: `scripts/smoke/compose_join.py` (Python per the style guide's > 20-line rule), run by `make smoke` and a CI job `ci-compose`.
4. **Fingerprint mismatch.** Today `WorkerDaemon.run` treats `CertPinError` like a network error and retries forever with backoff, but the token's pinned fingerprint never starts matching (found while drawing the daemon state machine, 2026-11-11). Recommendation: make it terminal like `join_reject`: `run` re-raises it, and `worker` exits 3 with a message saying the token was issued by a different Master (or before a cert rotation) and needs re-issuing. Update the state diagram in [modules.md](../architecture/modules.md#worker-daemon--workerdaemonpy).

## Steps

1. `master/server.py` (or a new `master/keys.py`): `ensure_signing_key(data_dir)`.
2. `StateStore`: open with `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout=5000` (file DBs only).
3. `cli.py`: implement `serve`, `token issue` and `worker` with the flags above, each calling `setup_logging` first. `serve` auto-creates the data dir, cert, key and Room and logs the banner lines from [wire-protocol.md §4.10](../architecture/wire-protocol.md#410-first-run-behavior-serve-on-fresh-state). `worker` builds the profile, decodes `cert_fp` from the token and runs the daemon. A `JoinRejected` exits with code 3 and the [error-handling.md](../architecture/error-handling.md) format.
4. SIGTERM/SIGINT handlers in both long-running commands: clean shutdown, exit 0 (130 on SIGINT).
5. Dockerfile: `ENV PYTHONUNBUFFERED=1`.
6. `docker-compose.dev.yml`: `master` (volume, port 8443) and `worker` (`C4M_MASTER=wss://master:8443`, `C4M_TOKEN=${C4M_TOKEN}`, `C4M_BENCHMARK=skip`, socket mount, `init: true`, compose `profiles: [worker]` so it starts only after a token exists).
7. `scripts/smoke/compose_join.py`: `up -d master` → wait for the listen log → `exec master compute4me token issue --room dev` → `up -d worker` with the token → assert as in Decide 2 → always `down -v` → non-zero exit on failure with the last 50 log lines of each service.
8. CI job `ci-compose` (needs `ci-image`), and `make smoke`.
9. Docs: README quick start (now actually runnable for these three commands), deployment.md, operations.md §4 (co-located Master + Worker), wire-protocol §4.1 (mark which flags exist now).

## Outputs

`src/compute4me/cli.py`, signing-key helper, `master/state.py` (pragmas), Dockerfile, `docker-compose.dev.yml`, `scripts/smoke/compose_join.py`, `.github/workflows/ci.yml` (`ci-compose`), Makefile, README, deployment.md, operations.md, wire-protocol.md, CHANGELOG.

## Tests

| File | Markers | Proves |
|---|---|---|
| `tests/unit/test_keys.py` | `task("T31")`, `unit` | the key is created once, reused, and mode 0600 |
| `tests/unit/test_cli_surface.py` (extend) | `task("T31")`, `unit` | `token issue` prints exactly one JWT on stdout whose claims match the flags (Typer `CliRunner`, temp data dir) |
| `tests/integration/test_cli_serve_worker.py` | `task("T31")`, `integration` | `serve` and `worker` as **subprocesses** on an ephemeral port: the Worker joins (event row present); SIGTERM to both exits 0 within 5 s |
| `scripts/smoke/compose_join.py` | CI job `ci-compose` | the same through the real image and Docker networking |

## Verify in Docker

```bash
make smoke      # compose: master up → token issue → worker up → worker_joined seen → down -v
```

Also by hand once, outside compose, following the README's operator flow (`docker run -d --name c4m … serve --room lab`, `docker exec c4m compute4me token issue --room lab`, a Worker `docker run` with `--init`). Paste `docker logs` from both sides in the PR.

## Done when

- [ ] `serve`, `token issue` and `worker` work from the image with the flags above; tokens survive a Master restart.
- [ ] `make smoke` passes locally and `ci-compose` is green.
- [ ] `docker stop` on either container exits cleanly in under 5 s.
- [ ] A bad token makes `worker` exit 3 with a formatted error (no traceback without `--debug`).
- [ ] README and deployment docs describe exactly what now runs.
- [ ] T22's stub is updated to say what's left.

## If this fails

- **Compose networking is flaky in CI (Worker starts before the Master listens):** keep the explicit wait-for-listen step; never rely on `depends_on` alone (it waits for start, not readiness).
- **SQLite "database is locked" between `serve` and `token issue`:** confirm WAL is on (`PRAGMA journal_mode` returns `wal`); raise the busy timeout. If it persists, make `token issue` talk to the serving process (a small authenticated local endpoint), which is T22's planned direction anyway.
- **Signal handling misbehaves under `asyncio.run`:** use `loop.add_signal_handler` inside the running loop, not `signal.signal`.

## References

- [ADR-0020](../adr/0020-docker-is-the-verification-surface.md), [ADR-0013](../adr/0013-cli-design-and-observability.md), [ADR-0015](../adr/0015-master-url-separate-from-token.md), [ADR-0011](../adr/0011-tls-fingerprint-in-token.md)
- [wire-protocol.md §4](../architecture/wire-protocol.md#4-cli), [error-handling.md](../architecture/error-handling.md), [operations.md §4](../architecture/operations.md)
- SQLite WAL: https://www.sqlite.org/wal.html · Docker `--init`: https://docs.docker.com/reference/cli/docker/container/run/#init

## History

- 2026-11-10: Card written (planning rewrite). Pulled forward from T22 by user decision.
