# Error Handling

How errors are presented to users (CLI), raised programmatically (Python), and reasoned about across the fabric (operational events). The goal: every error tells the user **what** went wrong, **why** if knowable, and **what to do** if actionable — without lying, blaming, or burying tracebacks.

This document captures the conventions; the implementation will live in `src/compute4me/errors.py` (once code lands) and is referenced by [wire-protocol.md §4 (CLI)](./wire-protocol.md) and [wire-protocol.md §5 (Python API)](./wire-protocol.md).

## 1. The format

```
error: <what>
  → <why if knowable>
  → hint: <what to do>
```

- **`error:`** prefix is lowercase (Rust / Cargo / Go convention). Uppercase reads as shouty.
- **`→`** for continuation lines. With `--ascii`, the arrow is `->`.
- **`hint:`** is a contract — only present when there's a real next step. Never speculative.
- **Concrete identifiers** (token JTIs, fingerprints, Worker IDs, Task IDs) always appear inline. Never "the token" — always "token `tk_abc`".

## 2. Worked examples

### Token expired
```
error: token expired 3 days ago
  → token jti=tk_abc valid until 2026-05-27T14:00:00Z
  → hint: ask the operator for a new token: `compute4me token issue --room lab`
```

### Cert fingerprint mismatch (security-critical)
```
error: Master cert fingerprint does not match token
  → expected a1b2…f3, got x9y8…22 from wss://vps.example:8443
  → hint: the Master may have been replaced or you may be talking to an impostor.
          ask the operator for a fresh token; do not bypass this check.
```

### Submission spec invalid (with did-you-mean)
```
error: metric 'val_aucc' not found in trial output metrics
  → trial t_001 wrote {'val_auc': 0.84, 'train_loss': 0.07}
  → hint: did you mean 'val_auc'?
```

### Job failed with multiple causes (compressed)
```
error: Job j_4z failed: 47 of 64 trials permanently failed
  → most-common failure: CUDA OOM (41 trials)
  → hint: see `compute4me logs job j_4z --failed-only` for per-trial details
```

### Network unreachable
```
error: could not connect to wss://vps.example:8443
  → connection refused (is the Master running?)
  → hint: check `ssh vps.example "docker ps | grep compute4me"`
```

### Auth — not admin
```
error: token jti=tk_abc is not authorized to submit Jobs
  → token has admin=False; only admin tokens can submit
  → hint: ask the operator for an admin token: `compute4me token issue --room lab --admin`
```

## 3. Style rules

| Rule | Why |
|---|---|
| Lowercase `error:` | Convention. Uppercase reads as shouty. |
| One-line summary first | User should be able to act on the first line alone in ~80% of cases. |
| No "I", no "sorry", no "!" | Tool voice, not chatbot voice. |
| Never lie about cause | "error: Task failed (cause unknown)" is fine. "(probably out of memory)" is not. |
| `hint:` is a contract | If you write one, it must be a real next step. Don't write "hint: try again." |
| Concrete identifiers always | "token `tk_abc`" not "the token". Lets the user grep logs. |
| Quote user input back when plausibly a typo | `'val_aucc'`, with did-you-mean if Levenshtein-near. |
| stderr for errors, stdout for results | So `compute4me fetch JOB_ID 2>/dev/null > metrics.json` works. |
| Tracebacks hidden by default | Use `--debug` (or `C4M_DEBUG=1`) to reveal. Most operator errors are config/network, not bugs. |
| User-container tracebacks go to `compute4me logs task <ID>` | Not into Compute4Me's stderr — that's where the operator looks for fabric errors. |
| Match the rendering mode | `--ascii`: `->` not `→`. `--slop`: 💥 prefixes welcome. |

## 4. Many-failures compression

A Job with 47 failed trials should not scroll 47 error lines off the screen. Compress:

```
error: Job j_4z failed: 47 of 64 trials permanently failed
  → most-common failure: CUDA OOM (41 trials)
  → other failures: non-finite metric (3), heartbeat timeout (2), exit code 1 (1)
  → hint: see `compute4me logs job j_4z --failed-only` for per-trial details
```

Then drill down with `logs`. The flag `--no-compress` (or `--full`) prints the full list for piping to a file.

## 5. Exit codes

| Code | Meaning |
|---|---|
| **0** | Success |
| **1** | Generic failure (default for unclassified errors) |
| **2** | Misuse / bad flags / bad args (argparse-style) |
| **3** | Auth error (token invalid / expired / revoked / not admin) |
| **4** | Connection / network failure |
| **5** | Job ended in a failed state (specific to `fetch` / `wait` / interactive blocking) |
| **130** | SIGINT (Ctrl-C); standard convention |

Distinct codes for auth (3) and network (4) because scripts retry these very differently — an auth fail triggers a token refresh; a network fail triggers backoff. Other distinct codes can be added later (6+) if a recurrent recovery pattern emerges; do not over-allocate up front.

Exit codes are documented in `compute4me help` so scripts can be written against them.

## 6. Python exception ↔ CLI mapping

The Python exception hierarchy and CLI errors share one source of truth — the exception class carries the user-facing message via `__str__`, and the CLI layer formats it with the WHY / HINT lines.

| Python exception | CLI exit | Common message form |
|---|---|---|
| `ConnectionError` | 4 | "error: could not connect to {url}" |
| `AuthError` | 3 | "error: token expired ..." / "error: cert fingerprint mismatch ..." / "error: token is not authorized to ..." |
| `SubmissionError` | 2 | "error: {spec problem with concrete value}" |
| `JobFailedError` | 5 | "error: Job {id} failed: N of M trials permanently failed" |
| `TaskFailedError` | 5 | "error: Task {id} failed: {classified cause}" (raised inside iterators) |
| `CancelledError` | 130 | "error: Job {id} cancelled" |
| `Compute4MeError` (other) | 1 | "error: {message}" |

Each exception carries inspection-friendly attributes:

```python
try:
    job.wait()
except JobFailedError as e:
    e.completed       # int: trials that succeeded
    e.total           # int: total trials submitted
    e.failed_tasks    # list[TaskFailure(task_id, worker_id, cause, error)]
```

## 7. What is *not* an error

Operational events that are part of normal recovery are **not errors** — they go through [`events`](./wire-protocol.md#42-observability--the-five-command-split), not stderr:

- Worker disconnect with re-queue (transient network)
- Task retry that succeeds on attempt 2
- OOM-promotion to a higher-VRAM Worker
- Quarantine + auto-restore
- Worker re-joining after a brief disconnect

The line: **stderr is for things that ended badly.** Events are for things that happened. A Task that OOMs once and succeeds on retry is a *successful* Task; the operator hears about the OOM via the event stream, not as an error.

## 8. Debug mode

`--debug` (or `C4M_DEBUG=1`) enables:

- Full Python tracebacks on uncaught errors
- Per-WS-message wire dumps (incoming + outgoing JSON)
- Per-HTTP-request logging (artifact transfers)
- Internal state-machine transitions (Worker / Task lifecycles)

In normal mode, none of these appear. Operators who hit something weird run with `--debug` and either fix it or send the output as a bug report.

## 9. Where to place new errors

When adding code that can raise, ask:

1. **Is it a true error?** (Something ended badly.) → raise/print per this doc.
2. **Is it an operational event?** (Something happened during normal recovery.) → emit via `events`.
3. **Is it ambiguous?** (Worker disconnected — is that an error or an event?) → event, until ≥3 consecutive failures, then error. The threshold of "enough recovery attempts to call it failure" lives in the failure controller, not the caller.

When in doubt: event > error. Operators tolerate noisy event logs; they distrust tools that cry wolf with errors.
