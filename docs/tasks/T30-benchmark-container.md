# T30: Benchmark as a container

| | |
|---|---|
| Phase | P1 |
| Size | L (5–8 h, plus a one-time multi-GB image pull) |
| Depends on | T09, T28 |
| Unblocks | T31 (a Worker container that can join), T15 (fallback when there is no benchmark), T17 (reuses the Docker wrapper) |
| Branch | `feat/T30-benchmark-container` |
| Issue | — |
| Status | Not started |

## Why this task exists

The shipped Worker image **cannot join a Room**. `profile()` calls the ResNet18 benchmark directly ([profiler.py:192](../../src/compute4me/worker/profiler.py#L192)). The benchmark needs torch, the image deliberately has none, so it raises `BenchmarkUnavailable` and `profile()` fails. `scripts/setup-worker.sh` installs torch on the *host*, which the Worker container never sees, and its CUDA detection picks the wrong wheel (see Background). [deployment.md](../architecture/deployment.md) claims the Worker "runs fine" without torch; it doesn't. [ADR-0016](../adr/0016-benchmark-runs-as-a-container.md) settles the fix: the Worker runs the benchmark as **its own pinned container image** through the Docker socket it already has for user Tasks.

## Background you need

- **Existing code:** `worker/profiler.py`: `profile(*, data_dir, cache_dir, gpu_probe, stats_probe, dataset_scan, benchmark=None)`, `run_micro_benchmark(seconds=30)`, `BenchmarkUnavailable`. Tests inject fake probes ([tests/unit/test_profiler.py](../../tests/unit/test_profiler.py)).
- **Why a container:** ADR-0006 already makes the Worker a launcher of containers via the host socket. A bench image gets CUDA-matched torch for free (the image's CUDA runtime plus the host driver), keeps the Worker image small, and runs the same way on every host. Registry access is already a v0.1 assumption (context.md, Container Contract).
- **Docker-outside-of-Docker:** the Worker talks to the **host** daemon through `/var/run/docker.sock`. Any container it starts is a sibling on the host, not a child. GPU flags and volume paths refer to the host. The benchmark needs no volumes, which makes it the simplest first use of this pattern before T17.
- **Which GPU:** a Worker started with `--gpus device=1` must benchmark GPU 1, not GPU 0. Inside the Worker, `nvidia-smi --query-gpu=uuid --format=csv,noheader` lists exactly the GPUs it was given (the NVIDIA Container Toolkit mounts `nvidia-smi` with the default `utility` capability). Pass that UUID to the sibling: `docker run --gpus device=GPU-<uuid> …`. A CPU-only Worker runs the bench without `--gpus`; torch falls back to CPU.
- **Host driver vs image CUDA:** a CUDA 12.x runtime image runs on any driver that supports CUDA 12 ("minor version compatibility"). NVIDIA documents the minimum Linux driver for CUDA 12.x as **≥ 525.60.13** (**Unverified** for the exact bench base you pick; check the CUDA compatibility table when choosing the tag). Older drivers make the bench container fail, which must degrade to `throughput_ref = None`, not a crash.
- **`setup-worker.sh` bugs (for the record, it is deleted here):** the `case` lists `12.*` before `12.1|12.2|12.3`, so cu121 is never picked; a CUDA 13 driver falls through to `*` and gets **CPU** torch, so the GPU is benchmarked on its CPU; and `uv sync --index …` can rewrite `uv.lock`.
- **Measurement design** (keep it the documented yardstick, ADR-0008): fixed ResNet18, fixed batch and input size, a warm-up, then a fixed wall-clock window; report samples/sec of forward+backward. On CUDA, synchronise before reading the clock.

## Decide first

1. **Base image.** Recommendation: the official `pytorch/pytorch:<torch>-cuda12.<x>-cudnn9-runtime` tag that is current when you implement, pinned **by digest**. Record the tag, digest, torch and CUDA versions in ADR-0016's History. Alternative: `nvidia/cuda` runtime plus a pip-installed torch wheel (smaller, but you maintain the install).
2. **Image name and versioning.** Recommendation: `ghcr.io/premity/compute4me-bench:<compute4me version>`. The Worker requests the bench tag matching its own version (`compute4me.__version__`), so results stay comparable within a release. Built by a `bench-image.yml` workflow on `workflow_dispatch` and on tags, not on every PR (multi-GB).
3. **What `throughput_ref` becomes when the bench can't run.** Recommendation: `throughput_ref: float | None` plus `throughput_note: str | None` (e.g. `"bench image pull failed: …"`). T15 uses a coarse GPU-model table when it is `None`. This is an additive schema change (data-model "Versioning" rule).
4. **Skipping in dev/CI.** Recommendation: env `C4M_BENCHMARK=auto|skip` (default `auto`). `skip` gives `throughput_ref=None, throughput_note="skipped (C4M_BENCHMARK=skip)"`. The compose smoke in CI uses `skip`, so CI never pulls the multi-GB image. Add it to the env table in wire-protocol §4.8.

## Steps

1. `bench/` folder: `Dockerfile` (pinned base, non-root user), `bench.py` (argparse: `--seconds`, `--batch`, `--device auto|cuda|cpu`; prints **one** JSON line `{"samples_per_sec", "device", "gpu_name", "torch", "cuda", "batch", "seconds"}`; exit 0 only on success).
2. `worker/docker.py`: a small typed wrapper over the `docker` CLI (`subprocess`, no docker-py dependency): `run(image, args, *, gpus=None, env=None, mounts=(), timeout) -> CompletedRun`, `pull(image)`, `image_present(image)`. T17 extends it; keep it free of benchmark specifics.
3. `worker/profiler.py`: `run_micro_benchmark(seconds=30, *, docker=…, gpu_uuid=None)` runs the bench image through the wrapper and parses the JSON line; `profile()` catches every bench failure, logs a WARNING (T29) and returns `throughput_ref=None` with a note. `detect_gpu()` also returns the GPU UUID.
4. `types.CapabilityProfile`: `throughput_ref: float | None`, `throughput_note: str | None = None`. Update data-model, context and the wire-protocol `join` payload description.
5. Remove the `bench` extra from `pyproject.toml`, delete `scripts/setup-worker.sh`, `uv lock`. Rewrite the deployment.md benchmark section (one image pull per host; how to pre-pull; what happens offline).
6. `.github/workflows/bench-image.yml` (manual + tag) and `make bench-image`.

## Outputs

`bench/Dockerfile`, `bench/bench.py`, `src/compute4me/worker/docker.py`, `worker/profiler.py`, `types.py`, `pyproject.toml`, `uv.lock`, `.github/workflows/bench-image.yml`, Makefile, deployment.md, data-model.md, context.md, wire-protocol.md, ADR-0016 History, CHANGELOG. Deleted: `scripts/setup-worker.sh`.

## Tests

| File | Markers | Proves |
|---|---|---|
| `tests/unit/test_profiler.py` (extend) | `task("T30")`, `unit` | with a fake docker wrapper: a good JSON line → `throughput_ref`; non-zero exit / timeout / garbage output / pull failure → `None` + note, and **`profile()` never raises**; `C4M_BENCHMARK=skip` skips |
| `tests/unit/test_docker_wrapper.py` | `task("T30")`, `unit` | command-line construction: `--gpus device=GPU-…`, env, timeout handling (fake `subprocess.run`) |
| `tests/integration/test_bench_image.py` | `task("T30")`, `requires_docker` | the bench image runs on CPU and prints a positive `samples_per_sec` (short `--seconds 3`) |
| same file | `task("T30")`, `requires_docker`, `requires_gpu` | on a GPU host, `device == "cuda"` and the GPU name matches `nvidia-smi` |

## Verify in Docker

```bash
make bench-image
docker run --rm $BENCH_IMAGE --seconds 5 --device cpu          # one JSON line, samples_per_sec > 0
docker run --rm --gpus all $BENCH_IMAGE --seconds 5            # on a GPU host: device=cuda
# The Worker path: from inside a Worker container with the socket mounted
docker run --rm --gpus all -v /var/run/docker.sock:/var/run/docker.sock \
  --entrypoint python $IMAGE -c "from compute4me.worker.profiler import run_micro_benchmark as b; print(b(5))"
```

Paste the outputs (CPU host and, when available, a GPU host) in the PR. The GPU-host run is also a tick on the "Needs the real fleet" issue.

## Done when

- [ ] The bench image builds and prints one JSON line on CPU (and on GPU where available).
- [ ] `profile()` inside the Worker image returns a profile on a host **without** a GPU and without network access to the registry (`throughput_ref=None`, note set).
- [ ] The Worker benchmarks the GPU it was given (UUID passed through), not GPU 0.
- [ ] `bench` extra and `setup-worker.sh` are gone; deployment.md describes the new path.
- [ ] ADR-0016 History records the base tag, digest, torch and CUDA versions.

## If this fails

- **The pytorch base is too large to pull on slow contributor links (more than ~15 min):** switch to `nvidia/cuda:<12.x>-runtime` plus a `pip install torch` layer at a pinned version; if still too large, ship a CPU-only bench and mark `throughput_note="cpu-only bench"` until v0.2's real-time throughput.
- **`--gpus device=<uuid>` isn't honoured on a host (old toolkit):** fall back to the index from `NVIDIA_VISIBLE_DEVICES` inside the Worker; log which was used.
- **The Docker socket is unavailable (rootless Docker, Podman):** the bench fails → `None`; that host can't run user Tasks either, which T33 (`doctor`) reports.

## References

- [ADR-0016](../adr/0016-benchmark-runs-as-a-container.md), [ADR-0006](../adr/0006-black-box-container-contract.md), [ADR-0008](../adr/0008-smart-pull-scheduling.md)
- NVIDIA Container Toolkit, GPU enumeration and `--gpus device=`: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/docker-specialized.html
- CUDA compatibility (minor version compatibility, minimum drivers): https://docs.nvidia.com/deploy/cuda-compatibility/

## History

- 2026-11-10: Card written (planning rewrite). Approach chosen by the user: bench as a container (ADR-0016).
