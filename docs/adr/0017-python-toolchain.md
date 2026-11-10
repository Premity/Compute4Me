---
status: accepted
date: 2026-11-10
---

# Python Toolchain: One Pinned Python, One Lockfile, One Version per Tool

## Context

Compute4Me is Python throughout ([context.md](../context.md) §Implementation stack), packaged with uv and shipped as one Docker image. By T09 the toolchain had drifted in ways that each cost a debugging detour:

- `requires-python = ">=3.13"` with no `.python-version`: the local venv silently became Python 3.14 while the image and mypy target 3.13.
- Ruff at three versions (lockfile 0.15.15, pre-commit v0.9.10, `pyproject.toml` `>=0.9`). Formatters of different versions disagree.
- The pre-commit mypy hook ran in an isolated environment with only `pydantic`, so its `--strict` result differed from CI's.
- `pre-commit` itself was not a dependency, so no hook ever ran.

## Decision

1. **Python 3.13 exactly:** `.python-version` = `3.13`, `requires-python = ">=3.13,<3.14"`, the Docker base `python:3.13-slim`, and mypy `python_version = "3.13"`. A Python upgrade is one PR that changes all four.
2. **uv with a committed `uv.lock`**; CI and the Dockerfile use `uv sync --frozen`.
3. **One version per tool.** Dev tools are pinned exactly in the `dev` dependency group. Pre-commit hooks for tools that are already dependencies (ruff, mypy) run as `repo: local` hooks through `uv run`, so the hook and CI use the same binary. When an external hook `rev` must be used, a comment names the file to keep in sync.
4. **One package** (`src/compute4me`), one image with two entrypoints (`serve`, `worker`). ML libraries (torch) are never dependencies of the package or the image ([ADR-0016](./0016-benchmark-runs-as-a-container.md)). An import-hygiene test checks that importing the Worker modules never loads torch.
5. **Module boundaries are enforced** with import-linter: `worker` and `master` never import each other; `types`, `proto` and `errors` sit at the bottom; `sdk` imports nothing from the package (it runs inside user containers).

Implemented in [T28](../tasks/T28-dev-tooling.md).

## Why

1. **"Passes locally" must mean "passes in CI" must mean "works in the image."** Each drift above broke that chain once.
2. **Exact pins are cheap for a solo project.** Upgrades are deliberate PRs, not surprises on a fresh clone.
3. **Boundaries are a design decision, not a habit.** The Master/Worker split mirrors the network split; letting code cross it would make the Worker image depend on Master code paths.

## Alternatives considered

- **Floating versions with `>=` everywhere:** less maintenance, and exactly what produced the drift.
- **Python 3.14 now:** possible, but the image, the lock and the CI were all built for 3.13; moving is a separate decision.
- **mirrors-mypy with a long `additional_dependencies` list:** works, but that list must be kept in step with `pyproject.toml` by hand; `uv run mypy` cannot drift.

## Consequences

- Dependency upgrades are explicit (`uv lock --upgrade-package …`) and land in their own PRs.
- Contributors need uv (already required).

## History

- 2026-11-10: Accepted (planning rewrite).
