# Test map

Which checks run where, and what triggers them. Test conventions (layout, markers, fakes) are in [CONTRIBUTING.md §Tests](../../CONTRIBUTING.md#tests); the T-task → test-file index is [tests/INDEX.md](../../tests/INDEX.md). The task that adds each planned check is named in the **Since** column.

✅ = runs automatically there · ▶ = run by hand there · — = never

## Test layers

Five layers, cheapest first. Each catches what the one above it can't.

| Layer | Tool | What it proves | Runs in | Since |
|---|---|---|---|---|
| Unit | pytest (`unit`) | pure logic: tokens, types, messages, state store, cost model, scheduler decisions | CI, `make check` | T01 |
| Integration | pytest (`integration`), real WSS on localhost | Master and Worker code talking over the real wire protocol, no Docker | CI, `make check` | T07 |
| Container | pytest (`requires_docker`) + the compose smoke | the **image** works: CLI entrypoint, Worker container joins a Master container, user containers run through the host socket | CI (`ci-image`, `ci-compose`), Docker host | T28, T31, T17 |
| GPU | pytest (`requires_gpu`) + manual | the bench container, GPU passthrough by UUID, OOM classification | a GPU host, by hand | T30, T17 |
| Fleet | manual, [fleet-check issues](../../.github/ISSUE_TEMPLATE/fleet-check.yml) | NAT traversal, heterogeneous scheduling, the paper's numbers | the real fleet | P5 |

**No browser tests (Playwright, Selenium).** Compute4Me has no web UI and none is planned for v0.1 ([operations.md §8](./operations.md#8-things-this-doc-deliberately-doesnt-cover)): its surfaces are the CLI (tested with pytest and typer's `CliRunner`), the Python API (pytest against a real Master) and the Container Contract (real containers in the container layer). Playwright earns its cost only if a dashboard is added; if one is ever proposed, it brings its own test layer and this table changes.

**Coverage** is reported in `ci-test` (`--cov`) but not gated for v0.1: the integration and container layers matter more than a line count, and a gate would push tests toward easy-to-cover code.

## Where each check runs

| Check | Catches | Since | pre-commit | CI (every PR + push to `main`) | Local `make check` | Local, Docker host | Real fleet |
|---|---|---|---|---|---|---|---|
| Ruff lint + format (one pinned version) | style, likely bugs, import order | T01; one version T28 | ✅ | ✅ `ci-lint` | ✅ | ✅ | — |
| mypy `--strict` on `src/` (same env as CI) | type contract breaks | T01; local hook T28 | ✅ | ✅ `ci-types` | ✅ | ✅ | — |
| Import contracts (import-linter) | `worker` ↔ `master` imports, `sdk` importing the package | T28 | — | ✅ `ci-imports` | ✅ | ✅ | — |
| Unit tests (`tests/unit/`, marker `unit`) | logic errors in pure modules; profiler with fake probes; import hygiene (no torch) | T01 | — | ✅ `ci-test` | ✅ | ✅ | — |
| Integration tests (`tests/integration/`, `integration`) | Master ↔ Worker over localhost WSS/HTTP with fakes; E2E Search with fake runners (T17) | T07 | — | ✅ `ci-test` | ✅ | ✅ | — |
| Image build + `--help` + `version` | packaging bugs (editable installs, missing system packages) | T28 | — | ✅ `ci-image` | `make image-smoke` | ✅ | — |
| Compose join smoke (a Master container and a Worker container) | anything between the CLI, the image and Docker networking | T31 | — | ✅ `ci-compose` | `make smoke` | ✅ | — |
| Markdown format + relative links (with anchors) | broken doc links, format drift | T28 | ✅ | ✅ `ci-docs` | — | — | — |
| Secrets scan (gitleaks) | committed keys and tokens (public repo) | T28 | ✅ | ✅ `ci-secrets` | — | — | — |
| PR title (Conventional Commit) | bad squash-commit subjects | T28 | — (commit messages: optional hook) | ✅ `pr-title` | — | — | — |
| `requires_docker` tests | bench image, real-Docker E2E (T17) | T30 | — | — (skipped automatically) | — | ▶ before marking the PR ready | — |
| `requires_gpu` tests | GPU passthrough, bench on CUDA | T30 | — | — (skipped automatically) | — | ▶ on a GPU host | ▶ |
| Card's **Verify in Docker** step | the task working the way users run it | every task ([ADR-0020](../adr/0020-docker-is-the-verification-surface.md)) | — | — | — | ▶ output pasted in the PR | — |
| `compute4me doctor` | host can't be a Worker (socket, GPU, network, fingerprint) | T33 | — | — | — | ▶ | ▶ each fleet host |
| Fleet checks (NAT join, real GPUs, 3-arm eval) | what no simulation shows | P5 | — | — | — | — | ▶ tracked on the "Needs the real fleet" issue |

## Commands

| Command | Runs |
|---|---|
| `make check` | lint + types + tests without `requires_docker`/`requires_gpu`; import contracts join it in T28. The same as the CI jobs that need no Docker |
| `uv run pytest` | every test this machine can run; `requires_docker`/`requires_gpu` tests skip themselves with a reason when Docker or a GPU is missing (T28 `conftest.py`) |
| `uv run pytest -m 'task("T16")'` | one task's tests |
| `make image-smoke` (T28) | build the image, then `--help` and `version` |
| `make smoke` (T31) | the compose join smoke test |
| `uv run pre-commit run --all-files` | every hook on every file |

## Notes

- **Every test carries `task("Txx")` and exactly one of `unit` / `integration`**; T28's `conftest.py` fails collection otherwise, and `--strict-markers` rejects typos.
- **Timeouts:** 60 s per test (`pytest-timeout`), 15 min per CI job. An integration test that waits on the network uses explicit `asyncio.wait_for` timeouts and prints the event log on failure; never `sleep`.
- **The bench image is never pulled in CI** (multi-GB). The compose smoke runs the Worker with `C4M_BENCHMARK=skip`; the bench path is checked by hand on a Docker host and a GPU host.
