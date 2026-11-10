# Contributing to Compute4Me

How work gets done here. Compute4Me is currently a one-person project; the discipline below keeps the build organised, auditable, and safe to hand to a coding agent.

> **Short version:** pick the next task in [docs/plan.md](./docs/plan.md) → read its card → settle its **Decide first** questions → branch → draft PR → `make check` → **Verify in Docker** → Ready → manual phase → squash-merge.

## Quick links

| What | Where |
|---|---|
| What v0.1 is and when it's done | [docs/prd.md](./docs/prd.md) |
| Order of work, Definition of Done | [docs/plan.md](./docs/plan.md) |
| How to do one task | [docs/tasks/](./docs/tasks/README.md) |
| Terms (canonical, not negotiable) | [docs/context.md](./docs/context.md) |
| Why things are the way they are | [docs/adr/](./docs/adr/README.md) |
| Which checks run where | [docs/architecture/test-map.md](./docs/architecture/test-map.md) |
| Problems already hit | [docs/background/challenges-faced.md](./docs/background/challenges-faced.md) |
| Guide for AI coding assistants | [CLAUDE.md](./CLAUDE.md) |

## Local setup

Requires Python 3.13 (uv installs it), [uv](https://docs.astral.sh/uv/), Docker, and Git. The Master, Worker and CLI target Linux; macOS and WSL2 work for development and as clients. Native Windows is not supported.

```bash
git clone https://github.com/Premity/Compute4Me.git && cd Compute4Me
make dev          # uv sync + install the pre-commit hooks
make check        # lint + types + tests: what CI runs, minus the Docker jobs
make image        # build the image (needed for every task's Docker verification)
```

> **Until T28 merges:** `pre-commit` isn't a dev dependency, so `make dev` fails at the hook step. Run `uv sync` and then `uvx pre-commit install`. There's also no `.python-version` yet, so pin the interpreter by hand: `uv venv --python 3.13 && uv sync` ([T28](./docs/tasks/T28-dev-tooling.md), [ADR-0017](./docs/adr/0017-python-toolchain.md)).

## The unit of work: a task

All v0.1 work is split into tasks **T01–T33**. [docs/plan.md](./docs/plan.md) lists them with phases, sizes and dependencies; each task in the current and next phase has a **full card** in [docs/tasks/](./docs/tasks/README.md); later ones are stubs in the plan until their detailing session. Task IDs are stable: T28+ were added on 2026-11-10, and the plan's order, not the number, says what comes next.

For each task:

1. **Check the dependencies are merged** (plan's index and graph).
2. **Read the whole card**, plus every ADR and architecture section it links.
3. **Settle every "Decide first" item** with the user before writing code. Record each answer in the card's History line, and in an ADR when it meets the ADR criteria ([adr/README.md](./docs/adr/README.md#when-to-write-one)).
4. **Branch, open a draft PR early, push at the end of every sitting.**
5. **Run the card's "Verify in Docker" step** and paste the output into the PR ([ADR-0020](./docs/adr/0020-docker-is-the-verification-surface.md)).
6. **Meet the Definition of Done** in [plan.md](./docs/plan.md#definition-of-done-every-task).

## Branches and commits

| Branch | For |
|---|---|
| `feat/T<NN>-<slug>` | A feature task (one task per branch; `feat/T<NN>-T<MM>-<slug>` for a tight cluster) |
| `chore/T<NN>-<slug>` | A tooling/CI task (e.g. `chore/T28-dev-tooling`) |
| `fix/<slug>` | A bug fix outside a task |
| `docs/<slug>` | Docs only |
| `chore/<slug>` | Tooling, dependencies, CI outside a task |

Slugs are kebab-case, ≤ 4 words. Never commit to `main`.

**Commits** are Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`, `ci:`, `build:`, `perf:`). Prefer **at least two commits per task, split along natural seams**: `feat:` (implementation), `test:` (tests), `docs:` (docs, changelog, index). GitHub pre-fills the squash body from the commit subjects, so terse, separate commits give a clean, scannable bullet list. Use one commit only when the change is genuinely atomic, and then keep it to a one-line subject.

## Pull requests

**Title** (becomes the commit on `main`): `feat(T<NN>): <card title>`, e.g. `feat(T10): Bandwidth/RTT probe + periodic profile refresh`. For non-task work: `fix: …`, `docs: …`, `chore: …`. CI checks the format from T28 (`pr-title`).

**Merge:** squash only. The PR title is the commit subject and the PR's commit list is the body.

### Lifecycle: Draft → Ready → Merge

1. **Draft** as soon as the branch builds. Fill in the [PR template](./.github/PULL_REQUEST_TEMPLATE.md): the card's Done-when list, the tests, and a **Manual** section with runnable commands and expected outcomes.
2. **Ready** when CI is green, the automated Done-when items are ticked, and the card's **Verify in Docker** output is in the PR. That means "implementation done; over to manual verification".
3. **Manual phase:**
   - **Verification** (scripted): run each command in the Manual section and tick it.
   - **Exploratory** (15–30 min): actually use the feature: CLI ergonomics, error messages, defaults.
   - **Triage every finding** as one of:
     - **Blocker:** fix on the same branch before merging.
     - **Polish:** file a `polish` issue; don't block.
     - **Spec issue:** update the PRD, card, context or ADR in the same PR.
4. **Squash-merge** when the Manual checkboxes are done. Delete the branch.

### Repository settings

These are the settings the docs assume. They are applied by the repo owner as part of T28; until then, **nothing is enforced**, and "don't merge with red CI" is a convention only.

| Setting | Value |
|---|---|
| Visibility | **Public** (Apache-2.0) |
| `main` protection | Required checks: `ci-test`, `ci-lint`, `ci-types`, `ci-imports`, `ci-image`, `ci-docs`, `ci-secrets`, `pr-title` (and `ci-compose` from T31); admin bypass allowed (solo project) |
| Merge methods | Squash only |
| Head branches | Auto-deleted after merge |

## Tests

Layout mirrors `src/compute4me/`:

```text
tests/
├── INDEX.md          # task → test file → markers; updated in every PR that adds tests
├── conftest.py       # marker enforcement, auto-skips, shared fixtures (T28)
├── fakes/            # FakeWorker, fake probes, fake runner, fake docker wrapper
├── unit/             # pure, fast, no network, no Docker
└── integration/      # real Master/Worker objects over localhost, with fakes; E2E with fakes
```

**Markers.** Every test declares a task, exactly one kind, and any hardware it needs:

```python
@pytest.mark.unit
@pytest.mark.task("T16")
def test_scheduler_assigns_biggest_task_to_fastest_worker() -> None: ...

@pytest.mark.requires_docker
@pytest.mark.task("T30")
def test_bench_image_reports_positive_throughput() -> None: ...
```

| Marker | Meaning | In CI |
|---|---|---|
| `unit` | Pure, fast, no I/O | ✅ |
| `integration` | Several modules, localhost network, fakes; no real Docker or GPU | ✅ |
| `requires_docker` | Needs a Docker daemon | skipped (auto-skips without Docker, T28) |
| `requires_gpu` | Needs CUDA | skipped (auto-skips without a GPU, T28) |
| `slow` | Takes > 5 s | ✅ |
| `task("T<NN>")` | Attribution; `pytest -m 'task("T16")'` runs one task's tests | — |

**Rules:** test external behaviour, not internals; put shared helpers in `conftest.py` / `tests/fakes/`, never copy them; every network wait has an explicit timeout; no `sleep`-based synchronisation. Where each check runs: [test-map.md](./docs/architecture/test-map.md).

## CI

| Job | Runs | Since |
|---|---|---|
| `ci-test` | `pytest -m "not requires_docker and not requires_gpu"` with coverage (reported, not gated) | T01 |
| `ci-lint` | `ruff check` + `ruff format --check` | T01 |
| `ci-types` | `mypy --strict src/` | T01 |
| `ci-imports` | import-linter contracts | T28 |
| `ci-image` | build the image, run `--help` and `version` | T28 |
| `ci-docs` | mdformat + Markdown link and anchor check | T28 |
| `ci-secrets` | gitleaks | T28 |
| `pr-title` | Conventional Commit title | T28 |
| `ci-compose` | compose join smoke (a Master container and a Worker container) | T31 |

`make check` runs the jobs that need no Docker; `make image-smoke` and `make smoke` run the Docker ones.

## Documentation travels with code

Doc changes caused by a feature go **in the same PR as the code**:

| Doc | Changes when |
|---|---|
| The task card | Status row; History line for every Decide-first answer |
| [docs/context.md](./docs/context.md) | A term is added or renamed (code and doc in the same PR) |
| [docs/architecture/](./docs/architecture/README.md) | A module, schema, message, CLI flag or deployment step is added or changed |
| [docs/adr/](./docs/adr/README.md) | A decision is made (new ADR) or a detail an ADR left open is settled (History line) |
| [docs/plan.md](./docs/plan.md) | Order, dependencies or scope of a task changes |
| [docs/prd.md](./docs/prd.md) | A requirement or acceptance criterion was wrong |
| [docs/roadmap.md](./docs/roadmap.md) | Something is deferred to, or pulled in from, a later version |
| [docs/background/challenges-faced.md](./docs/background/challenges-faced.md) | A real problem changed a design or would have produced wrong behaviour |
| [CHANGELOG.md](./CHANGELOG.md) | Every task PR (under `[Unreleased]`) |
| [tests/INDEX.md](./tests/INDEX.md) | Tests are added |
| [README.md](./README.md) | A user-visible command or install step changes |

Typos, restructuring and bulk reformatting go in their own `docs:` PR.

## Issues

| Template | For |
|---|---|
| `Task` | One per task; links the card. The card is the spec; the issue tracks who, when and blockers |
| `Bug` | Broken behaviour: what happened, expected, steps, environment, logs (redact tokens) |
| `Polish` | Exploratory-testing findings that don't block a merge: severity, originating PR, area |

Blank issues are disabled. **Milestones** are the phases (P1–P5). **Labels:** `phase:P1`…`phase:P5`, `polish`, `spec-issue`, `bug`, `blocked`, `needs-docker`, `needs-gpu`, `needs-fleet`. One standing issue, **"Needs the real fleet"**, collects every check that only real hardware can do (NAT'd contributor, lab GPUs, VPS Master).

## Versioning and releases

**SemVer, no pre-releases in 0.x.** Tag `v0.1.0` when v0.1 ships; `0.x` means no API stability.

**GitHub Releases:** tag everything; author a Release page only when there's an audience (paper submission, going public). A Release can be added to any tag later.

### Release checklist

Before `git tag vX.Y.Z`:

1. Every acceptance criterion in [docs/prd.md §13](./docs/prd.md#13-acceptance-criteria-v01-done) holds.
2. Every task for the version is merged; no open PRs target `main` for it.
3. [CHANGELOG.md](./CHANGELOG.md) has the version's entry; `pyproject.toml` matches the tag.
4. No ADR is still `proposed`.
5. Archive `docs/prd.md` → `docs/archive/prd-vX.Y.md` (and `docs/plan.md` → `docs/archive/plan-vX.Y.md`); write the next version's PRD and plan.

## Scope changes

1. **A later-version item should land in v0.1:** add a task to [docs/plan.md](./docs/plan.md) (next free ID), remove it from [docs/roadmap.md](./docs/roadmap.md), in one PR.
2. **A v0.1 item should be deferred:** remove it from the plan, add it to the roadmap, update the PRD's acceptance criteria if affected, and justify it in the PR.
3. **A decision needs reversing:** write a new ADR that supersedes the old one ([adr/README.md](./docs/adr/README.md#changing-an-adr)).

## Things to avoid

- **Relitigating an ADR** without writing one that supersedes it.
- **Features not in the plan.** Scope creep is the main failure mode of solo research projects; file a `polish` issue or propose a roadmap entry instead.
- **Merging with red CI**, even "it's flaky": fix the flake or quarantine the test explicitly.
- **`--no-verify`** to skip hooks: fix the hook or the code.
- **"No Docker rebuild needed"** without the card saying so ([ADR-0020](./docs/adr/0020-docker-is-the-verification-surface.md)).
- **Force-pushing `main`.** Force-pushing your own branch is fine.

## Working with coding agents

- Start the session with [docs/tasks/session-prompt.md](./docs/tasks/session-prompt.md); it points the agent at [CLAUDE.md](./CLAUDE.md) and the task card, and sets the ask-before rules.
- Ask for a summary back before any code: the deliverable, the Done-when list, the files to touch, and the **Decide first** questions with recommendations. Settle those one at a time.
- Expect the workflow above: branch name, ≥ 2 commits split by seam, draft PR with the template filled in, Docker verification pasted, Ready only when green.
