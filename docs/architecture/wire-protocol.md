# Wire & API Contracts

Every interface that crosses a process boundary or a host boundary. Five layers:

1. **Container Contract** — Master/Worker ↔ user's model image.
2. **Control channel** — Worker ↔ Master, WebSocket, JSON messages.
3. **Artifact channel** — Worker ↔ Master, HTTP, binary.
4. **CLI** — operator's command surface.
5. **Python submission API** — researcher's submission surface.

## 1. Container Contract (Master/Worker ↔ user image)

See [ADR-0006](../adr/0006-black-box-container-contract.md). The user's model container speaks **env-vars-in, files-out** — no `import compute4me` required.

| Variable | Meaning |
|---|---|
| `C4M_CONFIG` | Path to a JSON file of this Task's args (the sampled config / shard descriptor). |
| `C4M_INPUT_DIR` | Read-only mount of this Task's input Artifacts (and the assigned shard for Map). |
| `C4M_OUTPUT_DIR` | Writable dir; the container writes `metrics.json` (+ result Artifacts) here. |
| `C4M_TASK_ID` | Opaque Task identifier (for the container's own logging). |

### Success / failure semantics

- **Success:** process exit code `0` **and** `C4M_OUTPUT_DIR/metrics.json` present (Search) / declared output present (Map).
- **Failure:** non-zero exit code, OR missing required output, OR result-validation failure (non-finite metric / schema mismatch).

### Job-supplied environment variables (`env={...}`)

The submitter may attach additional environment variables to the Job spec via the `env: dict[str, str]` field on [`SearchJobSpec`/`MapJobSpec`](./data-model.md#53-job-submission-schemas). The Master forwards them; the Worker's runner sets them on the user container alongside the `C4M_*` variables. Typical use:

```python
job = c.submit_search(
    image="...",
    env={
        "WANDB_API_KEY": os.environ["WANDB_API_KEY"],   # W&B authentication
        "MLFLOW_TRACKING_URI": "https://mlflow.lab.local",
        "HF_HOME": "/tmp/hf_cache",
    },
    ...
)
```

This is the **only integration point** between Compute4Me and external observability / model-registry tooling (W&B, MLflow, Comet, TensorBoard, HuggingFace, etc.). Compute4Me does not parse, proxy, or interpret these variables — it just passes them through. The user container talks to the upstream service directly over outbound HTTPS.

**Security note:** These values traverse Master ↔ Worker inside the TLS-encrypted control channel; the Master holds them in `tasks.args_json` (SQLite). The closed-membership trust model assumes both Master and Worker hosts are trusted with the secret. Don't put secrets in `env` if any Worker host is outside your trust boundary.

**Reserved prefix:** any variable starting with `C4M_` is **reserved** for Compute4Me's own use. Job specs SHOULD NOT supply `C4M_*` values; the runner ignores them with a warning.

### Live metrics (optional)

The container may append JSON lines to `C4M_OUTPUT_DIR/progress.jsonl`. The Worker runner tails this and forwards to the Master as `task_progress` messages. Format is open — any JSON object per line; the operator's `status` view surfaces them verbatim.

### Optional SDK (`c4m`)

Pure sugar over the file contract:

```python
import c4m

cfg = c4m.config()              # reads C4M_CONFIG
in_dir = c4m.input_dir()        # reads C4M_INPUT_DIR
out_dir = c4m.output_dir()      # reads C4M_OUTPUT_DIR

# ... training ...

c4m.progress(epoch=3, loss=0.42)            # appends to progress.jsonl
c4m.report({"val_auc": 0.91, "train_loss": 0.07})   # writes metrics.json
```

The SDK is a Python package installable via `pip install compute4me` — *only* if the user wants it. Containers that prefer `os.environ` + raw file I/O work identically.

### Local reproduction

Running the same image with the same four env vars locally reproduces exactly what a Worker does:

```bash
docker run \
  -e C4M_CONFIG=/in/config.json \
  -e C4M_INPUT_DIR=/in \
  -e C4M_OUTPUT_DIR=/out \
  -e C4M_TASK_ID=local-debug \
  -v ./inputs:/in -v ./outputs:/out \
  ghcr.io/hamda/spacesight-train:latest
```

This is the debugging path: if a Task fails in the fabric, reproduce it locally with the same env vars and the same input volume to isolate the cause.

## 2. Control channel (Worker → Master, WebSocket)

See [ADR-0007](../adr/0007-websocket-http-transport.md). JSON messages over one persistent WSS connection per Worker. TLS via self-signed cert; fingerprint pinned from the Invite Token ([ADR-0011](../adr/0011-tls-fingerprint-in-token.md)).

### Worker → Master

| `type` | Payload | When |
|---|---|---|
| `join` | `{token, profile: CapabilityProfile}` | On connect. |
| `heartbeat` | `{worker_id, task_id?, throughput_sample?}` | Every 10s. |
| `task_progress` | `{task_id, fields: {...}}` | When a line appears in `progress.jsonl`. |
| `task_result` | `{task_id, status: 'succeeded'|'failed', metrics?, output_refs?, error?}` | On Task completion. |
| `profile_update` | `{worker_id, profile}` | Periodic refresh (~10 min). |

### Master → Worker

| `type` | Payload | When |
|---|---|---|
| `join_ack` | `{worker_id}` | Token verified, capacity available. |
| `join_reject` | `{reason}` | Bad/expired/revoked token, `max_workers` exceeded, fingerprint mismatch. |
| `task_assign` | `{task_id, code_ref, args, input_refs, requires}` | Scheduler matches Worker to a Task. |
| `task_cancel` | `{task_id}` | User cancellation; runner sends SIGTERM(30s) then SIGKILL. |
| `bandwidth_probe` | `{}` | Master measures throughput/RTT for the profile. |

### Connection lifecycle

```
Worker                                  Master
─────                                   ──────
1. open WSS (verify fingerprint)
2. send `join`
                                        verify token; admit if capacity
3. receive `join_ack` (or `join_reject`)
4. heartbeat every 10s
5. receive `task_assign` (when free)
6. fetch inputs (HTTP)
7. run container; tail progress.jsonl
8. send `task_progress` per line
9. send `task_result` on exit
10. back to step 4 (idle)
```

### Transport choice rationale

- **WebSocket over WSS (port 443-style)** survives firewalls and HTTP proxies that mangle HTTP/2 (which would break gRPC). The whole point of the outbound-only architecture is firewall survival.
- **JSON over CBOR/protobuf** — the control channel volume is tiny (KB/s per Worker); the readability win for debugging is worth the parsing cost. Migrate later if profiling shows otherwise.
- **One persistent connection per Worker** — avoids reconnect overhead; pairs naturally with heartbeats.

## 3. Artifact channel (Worker ↔ Master, HTTP)

See [ADR-0012](../adr/0012-content-addressed-artifacts.md). Separate from the control channel because artifact transfer is bulk binary, can take minutes, and benefits from HTTP's range/resume semantics.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/artifacts/{hash}` | Pull a full Artifact. Supports `Range`. |
| `GET` | `/artifacts/{hash}/shard?kind=index-range&start=&end=` | Pull a Map shard slice (per ShardStrategy). |
| `POST` | `/artifacts` | Ingest (operator CLI upload; multipart body OR `{url}` for external pull). |
| `POST` | `/tasks/{task_id}/outputs` | Worker uploads result Artifacts; Master content-addresses them. |

### Caching

Workers cache fetched artifacts locally by hash. `ensure_cached(hash)` skips re-fetch if the file exists and its hash matches. Cache contents are reported back in the `datasets_cached` field of the Capability Profile, enabling the Scheduler's locality preference.

### Integrity

Every fetch verifies the sha256 hash on disk. Mismatch → discard + re-fetch + log. No trust in the bytes on the wire.

## 4. CLI

Single binary `compute4me`, ships in the Docker image, also installable via `pip install compute4me`. Used by both the operator (ops surface) and — for any per-Job lifecycle work — the researcher.

Design choices recorded in [ADR-0013](../adr/0013-cli-design-and-observability.md). Error-message style in [error-handling.md](./error-handling.md).

### 4.1 Command surface

**Structure:** flat command list with one nested group (`token`) for the only noun with multiple verbs. Eight top-level commands; everyone is scannable in one `--help` screen.

```
# Mode commands (long-running; "be a Master" / "be a Worker")
compute4me serve     --room ROOM [--data-dir DIR] [--bind HOST:PORT] [-d]
compute4me worker    --token TOKEN [--name NAME] [--cache-dir DIR]
                     [--max-vram-mb N] [-d]

# Token management (grouped — 3 verbs on the `token` noun)
compute4me token issue   --room ROOM [--max-workers N] [--ttl DURATION] [--admin]
compute4me token revoke  JTI
compute4me token list    [--room ROOM] [--show-revoked]

# Observability — five distinct kinds of output, five commands
compute4me status     [--room ROOM] [--watch [--interval Ns]] [--json]
compute4me progress   JOB_ID [--task TASK_ID] [--json]
compute4me logs       <master | worker WORKER_ID | task TASK_ID | job JOB_ID>
                      [-f] [--tail N] [--since DURATION]
compute4me events     [--since DURATION] [-f] [--type TYPES] [--json]
compute4me fetch      JOB_ID [--out DIR] [--top K]

# Job lifecycle
compute4me jobs       [--room ROOM] [--status STATUSES] [--all]
compute4me cancel     JOB_ID [--yes]

# Utility
compute4me version
compute4me help [COMMAND]
```

### 4.2 Observability — the five-command split

Distinct categories of output get distinct commands. Conflating them is the tech-debt path; the split below comes from kubectl / docker / ray convergence.

| Command | What it shows | Default mode |
|---|---|---|
| **`status`** | Fleet topology (Workers + Capability Profiles) + Job progress summary | Snapshot once; `--watch` for live refresh |
| **`progress JOB_ID`** | Live per-trial metrics from `progress.jsonl` (epoch / loss / val_auc / wandb_url) | Stream until interrupted; color-by-worker |
| **`logs <target>`** | Stream of stdout/stderr from Master, a Worker, or a Task's user container | Stream; `--tail N` for snapshot |
| **`events`** | System-level transitions (joined, assigned, completed, failed, quarantined) | Stream; logfmt format |
| **`fetch JOB_ID`** | Download final result Artifacts to disk | One-shot |

External ML-observability (W&B, MLflow, TensorBoard) is **not a Compute4Me command** — the user container talks to those services directly. Compute4Me only passes their API keys through via [`env={...}`](#job-supplied-environment-variables-env) on the Job spec, and surfaces `wandb_url` (if present in `progress.jsonl`) inline in `progress` output.

### 4.3 Foreground-by-default for `serve` and `worker`

Both `serve` and `worker` are foreground by default — they print a startup banner, then stream live events with a sticky bottom status bar (rich-style). Use `-d` to detach as a daemon.

**`compute4me serve`** foreground output (sketch):
```
 Compute4Me Master 0.1.0
 ✓ State loaded from /data/master.db
 ✓ Self-signed cert generated; fingerprint a1b2…f3
 ✓ Listening on wss://0.0.0.0:8443
 ✓ Room 'lab' resumed: 0 workers connected, 0 queued jobs
 ─── log ───────────────────────────────────  Ctrl-C to stop ───
 14:23:15  ↪ worker ali joined  ·  RTX 3070, 8 GB
 14:23:42  ↪ job j_4z submitted  ·  search / 64 trials
 14:23:42  ➜ task t_001 assigned  ·  ali  ·  est 18.4s
 14:24:01  ✓ task t_001 done  ·  ali  ·  val_auc=0.84  ·  19.1s
 ─────────────────────────────────────  3 workers · 12/64 ───
```

The streaming section is essentially `status --watch` + `events --follow` merged. With `-d`, the process detaches and the same content is available via `compute4me status --watch` + `compute4me events -f` from another shell.

**Non-TTY auto-switch:** when `stdout` is not a terminal (systemd, `docker run -d` without `-t`), output switches to JSON-lines automatically — one event per line, suitable for `journalctl` / log aggregators.

### 4.4 Rendering modes

Three opt-in glyph + color modes for terminal output:

| Mode | Flag | What it does |
|---|---|---|
| Default | (none) | Unicode arrows / dots / box-drawing characters (✓ ✗ ⚠ ➜ ↪ ▶ ↓). Color when TTY. |
| ASCII | `--ascii` | Plain text replacements (`[OK]` / `[FAIL]` / `[WARN]` / `->` / `<-` / `>` / `v`). Color still applies unless `NO_COLOR`. For limited terminals, screen readers, copy-paste into bug reports. |
| Slop | `--slop` | Emoji-heavy with maximum color (✅ ❌ ⚠️ 📋 ⚙️ 🚀 🎉 💥). For when you want it. |

`--json` overrides all three (no glyphs in JSON output).

`NO_COLOR=1` env var disables color in any mode (standard convention).

### 4.5 Progress bars and accessibility

Progress bars are always paired with explicit numerals — the bar is supplementary visual aid, not load-bearing:

```
│ j_4z  search  running   42/64 trials (66%)  ████░░░░  5m      ~3m  │
```

A reader who can't parse the bar still gets full progress info from `42/64 trials (66%)`. Useful for screen readers and for terminals where the bar renders as garbage.

### 4.6 Watch refresh rate

`--watch` default refreshes once per second. Override with `--interval Ns` (e.g., `--interval 5s` for less flicker, `--interval 500ms` for finer-grained — though 1s is the sweet spot).

### 4.7 Confirmation prompts

- **`cancel JOB_ID`** prompts `Cancel job j_4z (47/64 trials done)? [y/N]` before acting. `--yes` skips. Reason: cancel kills running containers and discards partial Task results — disruptive enough to warrant a confirmation.
- **`token revoke JTI`** does *not* prompt — easy to undo (just issue another) and frequently scripted.
- **`serve`** does *not* prompt on first run; auto-creates state silently (see §4.10).

### 4.8 Environment variable precedence

`--flag` > `C4M_*` env > built-in default. No global config file in v0.1.

Standard env vars:

| Variable | Used by | Default |
|---|---|---|
| `C4M_ROOM` | Client commands (`status`, `fetch`, etc.) | — |
| `C4M_MASTER` | Client commands (e.g., `wss://vps:8443`) | — |
| `C4M_TOKEN` | Client commands | — |
| `C4M_CERT_FP` | Client commands (usually carried inside the token) | — |
| `C4M_DATA_DIR` | `serve` | `/data` |
| `C4M_CACHE_DIR` | `worker` | `/var/cache/c4m` |
| `C4M_DEBUG` | All commands (`1` enables `--debug`) | `0` |
| `NO_COLOR` | All commands (standard env var) | unset |

### 4.9 Verbosity levels

| Level | Flag | Output |
|---|---|---|
| Quiet | `-q` / `--quiet` | Errors only; suppress banner and event stream. Commands that return data still print their result on stdout. |
| Normal | (default) | Banner + key events (joins, leaves, jobs, tasks, errors). |
| Verbose | `-v` | Above + protocol-level events (heartbeats, profile updates, queue moves). |
| Debug | `-vv` / `--debug` | Above + per-message wire dumps + tracebacks on error. |

`-q` and `-v/-vv` are mutually exclusive; the last one wins. `C4M_DEBUG=1` env sets `--debug` globally (useful in CI).

### 4.10 First-run behavior (`serve` on fresh state)

`serve` auto-creates the SQLite DB, the Room (if `--room` given and not present), and the self-signed cert. No explicit `init` step. The startup banner reports what was created vs. what was resumed:

```
 ✓ State directory /data initialized (empty)
 ✓ Self-signed cert generated; fingerprint a1b2…f3
 ✓ Room 'lab' created
```

Subsequent runs:
```
 ✓ State loaded from /data/master.db (3 rooms, 4 tokens, 2 jobs)
 ✓ Self-signed cert loaded; fingerprint a1b2…f3
 ✓ Room 'lab' resumed: 0 workers connected, 0 queued jobs
```

Idempotent. Re-running `serve` on existing state never destroys data.

### 4.11 Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Generic failure |
| 2 | Misuse / bad flags / bad args |
| 3 | Auth error (token invalid / expired / revoked / not admin) |
| 4 | Connection / network failure |
| 5 | Job ended in a failed state (specific to `fetch` / `wait`) |
| 130 | SIGINT (Ctrl-C); standard convention |

Distinct codes for auth (3) and network (4) because scripts retry these very differently. See [error-handling.md](./error-handling.md) for the full error model.

### 4.12 What's *not* user-configurable in v0.1

Hard-coded sensible defaults are better defaults than fifty knobs no one understands. v0.1 fixes the following — they're tunable in v0.3+ if real use exposes a need:

- Heartbeat interval (10s), heartbeat timeout (30s)
- Task retry attempts (3), OOM-promotion threshold (≥2× VRAM)
- Quarantine trigger (≥3 fails in 10min), quarantine duration (5min)
- Job cancel grace (SIGTERM, 30s, SIGKILL)
- Profile refresh interval (~10min)
- Watch refresh rate default (1s — overridable per invocation via `--interval`)
- Worker cache size (unbounded in v0.1; LRU eviction in [v0.3](../roadmap.md#v03--fabric-ergonomics--robustness))

## 5. Python submission API (researcher — primary submit surface)

The researcher's surface. Sync-first; async opt-in. One `Client` per Master.

### 5.1 Connection

Three equivalent construction paths:

```python
from compute4me import Client

# Recommended: token carries master URL + cert fingerprint + auth in one credential
c = Client.from_token("eyJ...")

# Explicit construction
c = Client(master="wss://vps:8443", cert_fp="a1b2…f3", token="eyJ...")

# From environment (C4M_MASTER, C4M_CERT_FP, C4M_TOKEN, C4M_ROOM)
c = Client.from_env()
```

**Authentication:** submission requires an **admin token** (`compute4me token issue --admin`). The `admin: bool` claim on [`TokenClaims`](./data-model.md#54-invite-token-claims-signed) gates submission, cancellation, and job listing. Worker-only tokens (the default) cannot submit. One token system, two capability bits — recorded in [ADR-0014](../adr/0014-admin-tokens-for-submission.md).

### 5.2 Job submission

Two methods, one per primitive — not one polymorphic `submit(spec)`:

```python
from compute4me import loguniform, uniform, categorical, ShardStrategy
import os

# Search Job
job = c.submit_search(
    image="ghcr.io/hamda/spacesight-train:latest",
    metric="val_auc", direction="maximize",
    n_trials=64, top_k=5, sampler="optuna",
    search_space={
        "lr": loguniform(1e-5, 1e-2),
        "dropout": uniform(0, 0.5),
        "optimizer": categorical(["adam", "sgd"]),
    },
    inputs=["kepler-q1-q17/v3"],                # input Artifacts (mounted into every trial)
    env={"WANDB_API_KEY": os.environ["WANDB_API_KEY"]},   # passed to every trial container
)

# Map Job
job = c.submit_map(
    image="ghcr.io/hamda/spacesight-infer:latest",
    dataset="kepler-unlabeled/v1",
    shard=ShardStrategy(kind="file-list", n_shards=20),
    inputs=["model-checkpoint/best"],
    env={"HF_HOME": "/tmp/hf_cache"},
)
```

**Search-space DSL:** the `loguniform` / `uniform` / `categorical` (and similar) helpers re-export Optuna distributions under Compute4Me's namespace. The user does not `pip install optuna` separately; if the Sampler interface gains a non-Optuna backend later (Hyperopt, scikit-optimize — per [ADR-0010](../adr/0010-wrap-optuna.md)), the API stays stable.

**`env={...}`** see [§1 Job-supplied environment variables](#job-supplied-environment-variables-env). The standard W&B / MLflow / TensorBoard integration path.

### 5.3 JobHandle

`submit_search` / `submit_map` return a `JobHandle`. All per-Job operations live on the handle:

```python
job.id                          # str, e.g. "j_4z8c"
job.status()                    # JobStatus(state='running', tasks={pending: 4, running: 4, done: 56, failed: 0})
job.wait(timeout=None)          # block until terminal state; returns final status
job.results()                   # in-memory: list[TrialResult] (Search) or list[MapOutput] (Map)
job.fetch(out="./runs/abc")     # download artifacts to disk
job.cancel()                    # graceful: SIGTERM(30s)→SIGKILL on running Task containers; preserves done results
for trial in job.progress():    # iterator yielding live trial metrics as they arrive
    print(trial.task_id, trial.metrics)
```

`Client`-level methods exist for recovery — when you only have an ID (e.g., resumed from a script):

```python
c.get_job("j_4z8c")             # → JobHandle
c.list_jobs(status="running")   # → list[JobHandle]
c.fleet()                       # → FleetSnapshot (Workers + capability profiles + EMA throughput)
```

### 5.4 Two ways to get results — `results()` vs `fetch()`

Distinct use cases, distinct methods:

- **`job.results()`** returns in-memory objects. For Search: top-K `TrialResult(config, metrics, artifact_refs)`. For Map: `MapOutput(shard_descriptor, output_refs, metrics)`. Use this in notebooks to inspect metrics without touching disk.
- **`job.fetch(out=DIR)`** downloads result Artifacts (checkpoints, output files) to a local directory. Use this when the next step is a separate tool that reads files.

Both are valid; neither subsumes the other. `results()` is a network round-trip; `fetch()` is a file transfer.

### 5.5 Context manager — auto-cancel on unhandled exception

```python
with c.submit_search(...) as job:
    job.wait()
    best = job.results()[0]
    print(f"best val_auc: {best.metrics['val_auc']}")
# If Ctrl-C or unhandled exception, job.cancel() runs on exit.
```

Crucial for notebook UX: a Ctrl-C'd cell leaves no orphan Job running on the Master. Opt out by simply not using `with` — the handle still works after the block ends.

### 5.6 Exception hierarchy

```python
from compute4me.errors import (
    Compute4MeError,        # base — catch this for "anything fabric-related"
    ConnectionError,         # network / cert fp mismatch / endpoint down
    AuthError,               # token invalid / expired / revoked / not admin
    SubmissionError,         # bad spec (typo in metric name, malformed search space)
    JobFailedError,          # Job terminal-failed; has .failed_tasks for inspection
    TaskFailedError,         # individual Task failed (raised in iterators)
    CancelledError,          # Job was cancelled
)
```

Specific subclasses for the failure modes scripts care about (so `except AuthError` can trigger a token refresh, `except ConnectionError` can trigger backoff retry). Maps 1-to-1 to CLI exit codes — see [error-handling.md](./error-handling.md).

Each exception carries useful attributes:

```python
try:
    job.wait()
except JobFailedError as e:
    print(f"{e.completed} of {e.total} trials succeeded; {len(e.failed_tasks)} failed")
    for t in e.failed_tasks:
        print(f"  task {t.task_id} on {t.worker_id}: {t.error}")
```

### 5.7 Async opt-in

Sync is primary because notebook-driven research is overwhelmingly sync. For power users overlapping many submissions:

```python
from compute4me.async_ import AsyncClient

ac = AsyncClient.from_token("eyJ...")
job = await ac.submit_search(...)
await job.wait()
```

Two separate import paths so the sync API stays clean (no `async def` everywhere). Same interface shape; same exception hierarchy.

### 5.8 Boundary: what the Python API does *not* cover

Ops are CLI-only:

| Operation | Available in CLI | Available in Python |
|---|---|---|
| Issue / revoke / list tokens | ✅ | ❌ |
| `serve` / `worker` mode commands | ✅ | ❌ (process management, not Python territory) |
| Submit Job | (deferred to v0.3 — `compute4me submit job.yaml`) | ✅ |
| Wait / fetch / cancel / inspect Jobs | ✅ | ✅ |
| Live status / progress / events | ✅ | ✅ |
| Stream raw logs from Tasks | ✅ | (deferred to v0.2 unless needed for eval) |

The line: **anything multi-Job ops or daemon-startup goes through CLI; per-Job submission and observation goes through Python.**

## Versioning of the wire protocol

- **Additive messages only.** A Master that knows new message types may receive them from a Worker that doesn't send them (no-op) or send them to a Worker that doesn't understand them (Worker ignores unknown types — Pydantic discriminated union should tolerate this with `extra='ignore'`).
- **Required fields in `join`** are stable across all v0.x. New optional fields can be added to `CapabilityProfile`; readers ignore unknowns.
- **Breaking wire changes are gated by major version bumps** — i.e., not until 1.0 unless an explicit migration is provided.

## Security boundary summary

- **The token is the only secret on the Worker side.** Anyone with the token can join the Room (up to `max_workers`). Treat as you would an SSH key.
- **Master cert fingerprint pinning** prevents token-replay against an impostor Master.
- **TLS protects the channel**; no plaintext fallback. WSS only.
- **No mutual TLS** — the token authenticates the Worker; the cert fingerprint authenticates the Master. Sufficient for closed-membership.
- **Out of scope:** Byzantine-robust aggregation, secure aggregation, differential privacy — see [ADR-0002](../adr/0002-closed-membership-rooms.md).
