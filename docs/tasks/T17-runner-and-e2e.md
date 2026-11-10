# T17: Container runner + dispatch + E2E

| | |
|---|---|
| Phase | P2 (closes it) |
| Size | L+ (a full day or more) |
| Depends on | T08, T12, T16, T30 |
| Unblocks | T18–T21, T23, T24, T25 |
| Branch | `feat/T17-runner-and-e2e` |
| Issue | — |
| Status | Not started |

## Why this task exists

This is where a Job first actually runs. The Worker receives `task_assign`, makes sure its inputs are cached, `docker run`s the user's image under the Container Contract ([ADR-0006](../adr/0006-black-box-container-contract.md)), streams progress, uploads outputs, and reports `task_result`. The P2 tracer bullet, a tiny Search Job end to end, is this task's acceptance test, both on fake Workers in CI and on real Worker containers locally.

## Background you need

- **Contract** ([wire-protocol.md §1](../architecture/wire-protocol.md#1-container-contract-masterworker--user-image)): `C4M_CONFIG` (path to the args JSON), `C4M_INPUT_DIR` (read-only), `C4M_OUTPUT_DIR` (writable; `metrics.json`, optional `progress.jsonl`), `C4M_TASK_ID`; exit 0 + required outputs = success; Job `env={...}` forwarded, `C4M_*` keys stripped with a warning.
- **Docker-outside-of-Docker (the big gotcha).** The Worker container drives the **host's** Docker daemon through the socket. `docker run -v /var/cache/c4m/shards/t1:/in` resolves `/var/cache/c4m/...` **on the host**, not inside the Worker container. With the documented named volume (`-v c4m-cache:/var/cache/c4m`), that host path doesn't exist, and the user container silently gets an empty, freshly created directory.
- **Reuse T30's `worker/docker.py`** (CLI wrapper, GPU UUID passthrough). The user container gets the same `--gpus device=<uuid>` as the bench.
- **OOM classification** (feeds T18): a container killed by the cgroup memory limit shows `State.OOMKilled=true` in `docker inspect` (exit 137); a **CUDA** OOM is an ordinary non-zero exit with "CUDA out of memory" in stderr. Both set `TaskError.oom=True`.
- **Logs** ([ADR-0018](../adr/0018-logging-and-events.md) §Log shipping): the user container's stdout/stderr must reach `compute4me logs task <id>` (T24). Today no wire message carries logs.
- **Fakes:** `tests/fakes/` (T28) gets `FakeRunner` (no Docker; writes `metrics.json` from a function of the config) and an in-process fake Worker built from the real `WorkerDaemon` with the fake runner injected, so the E2E runs on GitHub-hosted CI.

## Decide first

1. **How user containers see inputs and outputs.** (plan.md Open items.)
   - **A. Bind-mount the cache at the same path on host and Worker (Recommendation):** the Worker runs with `-v /var/cache/c4m:/var/cache/c4m` (host dir, identical path), so any subpath is valid for the host daemon; user containers get exact `:ro` input and per-Task output mounts. Works on every Docker version. Cost: deployment docs switch from a named volume to a host directory, one per Worker (`/var/cache/c4m-gpu0`, …).
   - **B. `--volumes-from <worker container>`:** no path translation, but it exposes the whole cache and data volumes to the user container, read-write.
   - **C. Named-volume subpath mounts** (`--mount type=volume,src=c4m-cache,volume-subpath=…`): clean, but needs a recent Docker Engine (**Unverified** minimum version; check the release notes) on every contributor host.
   Record it in a History line on ADR-0006 and in deployment.md.
2. **Log shipping.** Recommendation (ADR-0018): stream stdout/stderr lines as `task_log{task_id, stream, lines[]}` messages, batched every ≤ 1 s and capped (e.g. 64 KiB/s per Task, excess dropped with a marker); at the end, upload the full log as a Task output Artifact (`logs.txt`). The Master keeps the tail in memory for `-f` and the Artifact for history.
3. **Sample images.** Recommendation: two. `examples/toy_quadratic/` (python-slim; metric = −(lr−0.01)², sleeps `epochs × 0.2 s`) for fast real-Docker E2E; `examples/resnet18_hpo/` (torch, tiny CIFAR subset, CPU-capable) as the realistic sample the PRD names.

## Steps

1. `worker/runner.py`: `run(task, *, inputs: Path, outputs: Path, gpu_uuid, env, on_progress, on_log) -> TaskResult`: write the config JSON, build the docker command (mount policy from Decide 1), start, tail `progress.jsonl` and stdout/stderr, wait, classify the exit (OOM detection), read `metrics.json`, return the result.
2. Daemon: handle `task_assign` (status busy, `ensure_cached`, run, upload outputs to `POST /tasks/{id}/outputs`, send `task_progress` / `task_log` / `task_result`, status idle). One Task at a time per Worker.
3. Master: `POST /tasks/{id}/outputs` (only the assigned Worker's token); on `task_result`, persist the result, `SearchPlan.on_result` → `tell`, then the next pull (T16); Job completes when every Task is terminal; Search keeps `top_k`.
4. Messages: `task_log` (new), wire-protocol §2.
5. `examples/toy_quadratic/` and `examples/resnet18_hpo/` with READMEs and `make example-images`.
6. Tests below; `tests/integration/test_e2e_search.py` is the CI tracer bullet.
7. Docs: wire-protocol §1–3, deployment.md (mount decision), modules.md, context.md, ADR-0006 History.

## Outputs

`worker/runner.py`, `worker/docker.py` (extended), `worker/daemon.py`, `master/server.py`/`app.py`, `proto/messages.py`, `tests/fakes/*`, `examples/*`, docs, CHANGELOG.

## Tests

| File | Markers | Proves |
|---|---|---|
| `tests/unit/test_runner.py` | `task("T17")`, `unit` | docker command construction (env, `C4M_*` stripped with a warning, mounts, GPU); exit and OOM classification from fake `inspect` output; missing `metrics.json` → failure |
| `tests/integration/test_e2e_search.py` | `task("T17")`, `integration` | Master + 2 fake Workers + a 4-trial Search: all trials complete, results validated and retrievable, Job `completed`, events in order |
| `tests/integration/test_e2e_docker.py` | `task("T17")`, `requires_docker` | the same with real Worker containers running `toy_quadratic`; `env` values reach the container; a `C4M_*` override is stripped |

## Verify in Docker

```bash
make example-images && make smoke
uv run python scripts/manual/t17_search.py      # submits a 4-trial toy Search to the compose Master
```

Expect four `task_succeeded` events and `metrics.json` for each trial in the Master's store. Paste the event log. (Submission goes through a test helper until T23's `Client` exists.)

## Done when

- [ ] Runner implements the contract, including env forwarding, `C4M_*` stripping and OOM classification.
- [ ] Mount strategy decided, implemented and documented; a user container sees its inputs read-only and writes outputs.
- [ ] Log shipping per the decision.
- [ ] Fake E2E passes in CI; real-Docker E2E passes locally.
- [ ] Sample images build and run locally with the four `C4M_*` variables (PRD criterion 9).

## If this fails

- **Same-path bind mounts are refused on a host (e.g. Docker Desktop file-sharing limits on macOS/WSL):** document the host requirement in deployment.md; for that host, fall back to option B with `:ro` on the cache volume and a separate output volume.
- **Tailing `progress.jsonl` misses lines across container restarts:** poll by file offset every 0.5 s rather than inotify (works on every filesystem).
- **The E2E is flaky in CI:** every wait has an explicit timeout and the failure prints the event log; never add sleeps.

## References

- [ADR-0006](../adr/0006-black-box-container-contract.md), [ADR-0016](../adr/0016-benchmark-runs-as-a-container.md), [ADR-0018](../adr/0018-logging-and-events.md), [wire-protocol.md](../architecture/wire-protocol.md), [deployment.md](../architecture/deployment.md)
- Docker bind mounts: https://docs.docker.com/engine/storage/bind-mounts/ · `docker inspect` State.OOMKilled: https://docs.docker.com/reference/cli/docker/inspect/

## History

- 2026-11-10: Card written (planning rewrite).
