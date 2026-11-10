# T28: Dev tooling and CI hardening

| | |
|---|---|
| Phase | P1 |
| Size | M (3–5 h) |
| Depends on | T09 |
| Unblocks | T29, T30, and every later task |
| Branch | `chore/T28-dev-tooling` |
| Issue | — |
| Status | Not started |

## Why this task exists

Through T01–T09 the local hooks never ran, three tools disagreed on versions, the Python version wasn't pinned, and CI never built the image. Each of these produced a "small surprise" in some session. This task makes `make dev && make check` a reliable promise: what passes locally passes in CI, on the same Python, with the same tool versions, and the image is built on every PR. Nothing here changes runtime behaviour.

## Background you need

What is broken today (found 2026-11-10, see [challenges-faced.md](../background/challenges-faced.md)):

| Problem | Where | Effect |
|---|---|---|
| `pre-commit` is not a dependency | `pyproject.toml` `[dependency-groups].dev` | `make dev` fails on its second line; no hook has ever run on any commit |
| No `.python-version`; `requires-python = ">=3.13"` has no upper bound | repo root, `pyproject.toml` | the local `.venv` is **3.14.10**; the image is 3.13; mypy targets 3.13; CI gets whatever uv picks |
| Three ruff versions | `uv.lock` 0.15.15 · `.pre-commit-config.yaml` v0.9.10 · `pyproject.toml` `ruff>=0.9` | different versions format differently, so the hook and CI would fight |
| The mypy hook runs in an isolated env with only `pydantic` | `.pre-commit-config.yaml` | websockets, pyjwt, typer, cryptography become `Any`, so `--strict` results differ from CI |
| No `--strict-markers` | `[tool.pytest.ini_options]` | a typo such as `requires_dokcer` silently runs the test in CI |
| No timeouts | `ci.yml`, pytest | one hung `asyncio.run` in `tests/integration/` hangs CI for 6 hours |
| No image build in CI | `ci.yml` | the T01 editable-install bug was found only by building by hand ([ADR-0020](../adr/0020-docker-is-the-verification-surface.md)) |
| Markdown hooks (mdformat, link check) only in pre-commit | `.pre-commit-config.yaml` | never run anywhere, because pre-commit never ran |
| No secret scanning on a **public** repo that handles JWT signing keys and TLS keys | — | a committed key would be public immediately |
| No `tests/conftest.py`; `_profile()` copied into 4 test files; `_KEY` into 2; `tests/fakes/` empty | `tests/` | every new test file re-invents fixtures |
| Nothing checks that the light modules don't import torch | — | an accidental top-level `import torch` crashes the torch-free image ([ADR-0016](../adr/0016-benchmark-runs-as-a-container.md)) |
| No module-boundary contracts | — | e.g. `worker/` importing `master/` would compile and pass tests |

Every current test already has `task(...)` and a kind marker; this task only enforces it.

Tool notes:

- **uv** reads `.python-version` for `uv sync`, `uv run` and `astral-sh/setup-uv` in CI. The Dockerfile pins `python:3.13-slim` separately; keep them equal.
- **pre-commit `repo: local` hooks with `language: system` and `entry: uv run …`** run in the project's own venv, so mypy sees the real dependencies. This is the standard fix for the "isolated mypy" problem.
- **import-linter** (`lint-imports`) reads contracts from `pyproject.toml`; it sees only module-level imports. A subprocess test is needed for lazy imports (Fovea's `tests/unit/test_import_hygiene.py` is the pattern).
- **`pytest-timeout`**: `timeout = 60` in ini options applies per test; mark the rare slow test explicitly.
- **mdformat with `--wrap=no`** will reformat existing Markdown the first time it runs. Do that in a separate commit so the diff is reviewable.

## Decide first

1. **Ruff version.** Recommendation: pin the version already in `uv.lock` (0.15.15) exactly (`ruff==0.15.15`) in `pyproject.toml`, and use the same `rev` in pre-commit. One comment in each file says "keep in sync with …".
2. **Python upper bound.** Recommendation: `requires-python = ">=3.13,<3.14"` and `.python-version` = `3.13`. Moving to 3.14 is then one deliberate PR touching the Dockerfile, both pins and mypy's `python_version`.
3. **Marker enforcement.** Recommendation: a `pytest_collection_modifyitems` hook in `tests/conftest.py` that errors if a test lacks `task(...)` or a kind marker (`unit` / `integration`). It costs nothing because all 79 tests already comply.

## Steps

1. **Dependencies:** add `pre-commit`, `pytest-timeout` and `import-linter` to the `dev` group; pin ruff exactly; `uv lock`.
2. **Python pin:** add `.python-version`; bound `requires-python`; recreate `.venv` (`rm -rf .venv && make dev`) and confirm `uv run python --version` is 3.13.x.
3. **pre-commit:** ruff `rev` equal to the lock; replace the mirrors-mypy hook with a `repo: local` hook running `uv run mypy --strict src/`; add `gitleaks`; keep mdformat and the link checker. Run `uv run pre-commit run --all-files` and commit the mdformat churn separately.
4. **pytest:** `addopts = "--strict-markers -ra"`, `timeout = 60`.
5. **`tests/conftest.py`:** marker enforcement; auto-skip `requires_docker` (no `docker info`) and `requires_gpu` (no `nvidia-smi`) with a clear reason; shared fixtures `signing_key`, `make_profile(**overrides)`, `master_cert(tmp_path)`.
6. **`tests/fakes/`:** move the profile factory and the `_start_master` helper (now duplicated in `tests/integration/`) here; update the existing tests to use them.
7. **Import hygiene:** `tests/unit/test_import_hygiene.py` imports `compute4me`, `compute4me.cli`, `compute4me.worker.profiler` and `compute4me.worker.daemon` in a subprocess and asserts `torch` is not in `sys.modules`.
8. **Import contracts** in `pyproject.toml` (`[tool.importlinter]`):
   - `compute4me.types`, `compute4me.proto`, `compute4me.errors` import nothing else from `compute4me` (except `proto` → `types`);
   - `compute4me.worker` never imports `compute4me.master`, and vice versa;
   - `compute4me.client` and `compute4me.sdk` import neither `master` nor `worker`;
   - `compute4me.sdk` imports nothing from `compute4me` (it runs inside user containers).
9. **CI** (`.github/workflows/ci.yml`):
   - top-level `concurrency: {group: ${{ github.workflow }}-${{ github.ref }}, cancel-in-progress: true}`;
   - `timeout-minutes: 15` on every job; `enable-cache: true` on setup-uv;
   - keep `ci-test`, `ci-lint`, `ci-types`; add `ci-imports` (`uv run lint-imports`);
   - add **`ci-image`**: `docker build`, then `docker run --rm $IMAGE --help` and `docker run --rm $IMAGE version`;
   - add **`ci-docs`**: `uv run pre-commit run --all-files mdformat` and `check-md-links`;
   - add **`ci-secrets`**: `gitleaks/gitleaks-action@v2` with `fetch-depth: 0` and `permissions: {contents: read, pull-requests: read}`;
   - add **`pr-title`**: `amannn/action-semantic-pull-request@v5`, on `pull_request` `types: [opened, synchronize, reopened, edited]`, types `feat fix docs test refactor perf build ci chore revert`.
10. **Makefile:** a `help` target from `##` comments as the default goal; `hooks` (pre-commit install, including `commit-msg` if a message hook is added); `image-smoke` (build + `--help` + `version`); `clean`; make `e2e` select `tests/integration/test_e2e_*.py` only.
11. **Link checker:** `scripts/check_md_links.py` checks only that files exist; anchors are "checked for presence but not validated", which let `prd.md#13-eval--research-runbook` (a heading that never existed) through. Validate `#fragment`s against the target file's headings using GitHub's slug rules. Its docstring promises "a CI-only job" for external links that doesn't exist; either add a weekly `lychee` workflow or delete the sentence.
12. **`.gitignore`:** `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`, `.coverage*`, `htmlcov/`, `dist/`, `build/`, `*.pem`, `*.key`.
13. **Repo settings** (the user does this in the GitHub UI; record the date in the PR): protect `main` requiring `ci-test`, `ci-lint`, `ci-types`, `ci-imports`, `ci-image`, `ci-docs`, `ci-secrets`, `pr-title`, with admin bypass allowed; squash merge only; auto-delete head branches on.

## Outputs

`pyproject.toml`, `uv.lock`, `.python-version`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml`, `Makefile`, `.gitignore`, `tests/conftest.py`, `tests/fakes/*.py`, `tests/unit/test_import_hygiene.py`, updated test files, [test-map.md](../architecture/test-map.md) (rows for the new jobs), CHANGELOG.

## Tests

| File | Markers | Proves |
|---|---|---|
| `tests/unit/test_import_hygiene.py` | `task("T28")`, `unit` | light modules import without torch |
| `tests/unit/test_conftest_hooks.py` | `task("T28")`, `unit` | a test without `task(...)` fails collection (use `pytester`) |
| existing suite | — | still 79 passing after the fixture move |

## Verify in Docker

```bash
make image-smoke          # builds, then `--help` lists all commands and `version` prints 0.1.0
```

Expect the same output in the `ci-image` job log.

## Done when

- [ ] `rm -rf .venv && make dev && make check` passes on a clean clone, on Python 3.13.
- [ ] `uv run pre-commit run --all-files` passes; the hooks are installed by `make dev`/`make hooks`.
- [ ] One ruff version everywhere; the mypy hook and CI give the same result.
- [ ] CI has the eight jobs above, all green; a PR with a bad title fails `pr-title`.
- [ ] Import hygiene test and import contracts pass.
- [ ] Shared fixtures in `tests/conftest.py` / `tests/fakes/`; no duplicated `_profile()`.
- [ ] Repo settings applied by the user and noted in the PR.
- [ ] [test-map.md](../architecture/test-map.md) and [CONTRIBUTING.md](../../CONTRIBUTING.md) match what was built.

## If this fails

- **mdformat rewrites tables or Mermaid blocks badly:** exclude the affected files with `exclude:` and file a `polish` issue; do not hand-revert its output on every commit.
- **gitleaks flags test fixtures** (the fake signing key): add a `.gitleaks.toml` allowlist for `tests/` paths, never a blanket ignore.
- **The `ci-image` job is slow (> 5 min):** add `docker/setup-buildx-action` + `docker/build-push-action` with `cache-from/cache-to: type=gha`.

## References

- [ADR-0017](../adr/0017-python-toolchain.md) (toolchain), [ADR-0020](../adr/0020-docker-is-the-verification-surface.md) (Docker verification)
- Fovea's `docs/design/test-map.md` note on ruff version drift; `tests/conftest.py` and `tests/unit/test_import_hygiene.py` patterns
- import-linter: https://import-linter.readthedocs.io/

## History

- 2026-11-10: Card written (planning rewrite).
