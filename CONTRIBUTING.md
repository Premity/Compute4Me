# Contributing to Compute4Me

This document encodes the development workflow. Currently a solo project; the discipline below is in place so the build stays organized and auditable.

If you're returning to this project after a break, start here. If you're a coding agent picking up a task, read [docs/prd.md §11](./docs/prd.md#8-implementation-tasks-t01t27) first for the specific T-task spec, then this document for *how* to deliver it.

## Quick links

- **Current milestone:** [docs/prd.md](./docs/prd.md)
- **Glossary:** [docs/context.md](./docs/context.md)
- **Decisions:** [docs/adr/](./docs/adr/)
- **Architecture reference:** [docs/architecture/](./docs/architecture/)
- **What's deferred:** [docs/roadmap.md](./docs/roadmap.md)

## Local setup *(once code exists)*

Requires Python 3.13, `uv`, Docker, Git. Linux / macOS / WSL2 supported; native Windows is not.

```bash
git clone https://github.com/Premity/Compute4Me.git
cd Compute4Me
uv sync                        # creates .venv, installs deps
uv run pre-commit install     # installs git hooks (ruff + mypy + md link check)
uv run pytest                 # full test suite (runs with markers — see Testing below)
```

## The unit of work: T-tasks

All v0.1 work is decomposed into **T-tasks** (`T01`–`T27`) in [docs/prd.md §11](./docs/prd.md#8-implementation-tasks-t01t27). Each task is self-contained: prerequisites, deliverables, file paths, acceptance criteria.

Work proceeds **one task or one tightly-related cluster** per feature branch, dependency-ordered through phases P0 → P5. Don't skip ahead — the tracer-bullet milestones at the end of P1 (Worker joins) and P2 (tiny Search Job runs E2E on fake Workers) are load-bearing.

## Branch & commit workflow

### Branches

- **Naming:** `feat/T<NN>-<slug>` for single tasks; `feat/T<NN>-T<MM>-<slug>` for clusters.
  - Examples: `feat/T01-repo-skeleton`, `feat/T05-T08-control-plane-bootstrap`, `feat/T18-T19-failure-and-quarantine`.
  - Slugs are kebab-case, ≤4 words, match the PRD task title.
- **One branch per task or task-cluster.** Don't accumulate unrelated work on a branch.
- **Branches deleted on merge** (GitHub auto-delete enabled).

### Commits within a branch

- **Conventional Commits, lightweight:** `feat:`, `fix:`, `test:`, `refactor:`, `docs:`, `chore:` prefixes.
- No enforcement hook — self-discipline only. Commits get squashed at merge, so WIP and "fix typo" commits within the branch are fine.

### Pull Request

PR title format: **`feat(T<NN>): <Title from PRD §11>`**. For non-task work: `fix:` / `chore:` / `docs:` (no T-ID).
Examples:
- `feat(T01): Repo skeleton + packaging + image`
- `feat(T05-T08): Control-plane bootstrap (tracer bullet 1)`
- `docs: clarify ADR-0011 fingerprint rotation`

**Merge strategy:** squash merge. The PR title becomes the commit subject on `main`; the PR body becomes the commit body. `main`'s history reads as a clean sequence of T-tasks.

## The PR lifecycle

**Draft → Ready → Merge**, with explicit AI/human responsibilities:

1. **Open as Draft** as soon as the branch builds. Fill in the PR template (see below). Pre-populate the **Manual** section with specific, runnable commands and expected outcomes.
2. **CI runs on the Draft.** When all CI jobs are green and acceptance criteria checkboxes are ticked from the automated side, **convert the PR to Ready** — this is the "implementation done; over to you for manual verification" signal.
3. **Manual phase** — see below.
4. **Failures:** comment on the PR. Fixes go on the **same branch** (squashed away on merge). CI re-runs; back to step 3.
5. **Squash-merge** when Manual checkboxes are all green. Branch auto-deletes.

### Manual phase — two flavours

The PR template's Manual section has two subsections:

**Verification** (scripted): specific commands with expected outcomes. Pre-populated by the implementer. Tick after running.
```
- [ ] Ran `compute4me serve --room test` → Master boots, prints port + cert fp
- [ ] Ran `docker run compute4me worker --token <T>` → Worker appears in `status`
```

**Exploratory** (free play, ~15–30 min): you actually *use* the feature — CLI ergonomics, error messages, defaults, integration feel. Catches what scripted tests structurally can't.

**Triage rule** during exploratory: every finding is one of three kinds.
- **Blocker** → fix on the same branch before merge.
- **Polish** → file as a [polish issue](./.github/ISSUE_TEMPLATE/polish.md), don't block.
- **Spec issue** → update PRD / CONTEXT / ADR in the same PR.

This stops exploratory testing from gold-plating every PR while still catching real problems.

## Tests

### Layout

Tests mirror the code under `src/compute4me/`:

```
tests/
├── INDEX.md                              # T-task → test file map; updated per PR
├── unit/                                  # pure, fast, no I/O
│   ├── test_cost_model.py
│   ├── test_scheduler.py
│   └── ...
├── fakes/                                 # FakeWorker, fake hw probes, fake container runner
└── integration/
    └── test_e2e_search.py                # Master + 2 fake Workers + tiny Search Job
```

### Pytest markers

Every test declares (a) its kind, (b) its T-task attribution, (c) any hardware dependency.

```python
@pytest.mark.unit
@pytest.mark.task("T16")
def test_scheduler_assigns_biggest_to_fastest(): ...

@pytest.mark.integration
@pytest.mark.task("T17")
def test_e2e_search_job_completes(): ...

@pytest.mark.requires_docker
@pytest.mark.task("T17")
def test_runner_with_real_container(): ...
```

Marker set:
- `@pytest.mark.unit` — pure, fast, no I/O (most tests).
- `@pytest.mark.integration` — multi-module with fakes; no real network / GPU / Docker.
- `@pytest.mark.requires_docker` — needs real Docker (skipped in CI).
- `@pytest.mark.requires_gpu` — needs CUDA (skipped in CI).
- `@pytest.mark.task("T<NN>")` — attributes the test to one (or more) T-tasks.
- `@pytest.mark.slow` — takes >5s (allows fast iteration via `-m "not slow"`).

### CI vs local invocation

- **CI default:** `pytest -m "not requires_docker and not requires_gpu"` — fully deterministic, runs on GitHub-hosted runners (no hardware).
- **Local full run** (with GPU + Docker available): `pytest` (no filter).
- **Run a specific T-task's tests:** `pytest -m 'task("T16")'`.

### `tests/INDEX.md`

A maintained map: T-task → test file(s) → markers. Updated per PR — every new test gets an entry. Provides a quick "which tests cover T16?" lookup without grep.

## CI quality gates (GitHub Actions)

Three required jobs on every push to a PR; branch protection requires all three before merge.

| Job | Command | Purpose |
|---|---|---|
| `ci-test` | `pytest -m "not requires_docker and not requires_gpu"` | Behavioral correctness |
| `ci-lint` | `ruff check . && ruff format --check .` | Style + import order |
| `ci-types` | `mypy --strict src/` | Type contracts |
| (coverage) | `pytest --cov` | Reported only, **not gated** |

**Branch protection on `main`:**
- Require `ci-test`, `ci-lint`, `ci-types` to pass.
- Require branch up-to-date with `main` before merge.
- No required reviewers (solo).
- Auto-delete head branch on merge.

**Local pre-commit hooks** (configured in `.pre-commit-config.yaml`) run `ruff` + `mypy` + a relative-link checker on `*.md` before every commit. Saves a CI cycle when you typo something.

## Documentation discipline

### Docs travel with code

Doc changes that arise from a feature **live in the same PR as the code**. This includes:

| Doc | When it changes in a feature branch |
|---|---|
| [docs/context.md](./docs/context.md) | New term introduced by this code; rename of an existing term. |
| [docs/adr/](./docs/adr/) | New architectural decision being made in this branch (write the ADR *before* / *alongside* the code, not after). |
| [docs/roadmap.md](./docs/roadmap.md) | Scope shift discovered while implementing (v0.2 item turned out trivial; v0.1 item turned out to need deferring). |
| [docs/prd.md](./docs/prd.md) | Spec correction discovered while implementing (T-task acceptance criterion was wrong). |
| [README.md](./README.md) | New CLI command, install step, etc. |
| [tests/INDEX.md](./tests/INDEX.md) | New tests added — always. |

Exceptions go in their own small `docs:` PR: typos, restructuring, bulk reformat.

### The PR template's "Docs touched" and "ADRs touched" sections

Force you to declare what you changed. If you wrote "none" but you touched a term in CONTEXT.md, the discrepancy gets caught on self-review.

## Issues

Two templates under `.github/ISSUE_TEMPLATE/`:

- **`polish`** — exploratory-testing findings. Severity (`nit` / `minor` / `annoying`) + originating PR + area + description. Goes into a polish backlog; not a merge blocker.
- **`bug`** — actually broken behavior. What happened / expected / repro / environment.

`config.yml` disables blank issues — every issue picks a template.

## Versioning & releases

**SemVer, Pattern A** (no pre-releases for v0.x development):

- Tag `v0.1.0` when v0.1 ships (all 10 acceptance criteria from [docs/prd.md §12](./docs/prd.md) check).
- Tag `v0.2.0` when v0.2 ships. Etc.
- No alpha / beta / rc — intermediate states are referenced by commit SHA or PR number.

**0.x means "no API stability."** Anything can change in any minor-version bump until v1.0.

**GitHub Releases — Path Y:** tag everything; author a Release page **only** when there's an audience (paper submission, going public). For early development, just `git tag` + `git push --tags` is sufficient. The Release wrapper can be added retroactively to any tag.

### When cutting a release (checklist)

Before `git tag vX.Y.Z`:

1. ✅ All acceptance criteria in [docs/prd.md §12](./docs/prd.md) check.
2. ✅ All T-tasks for this version are merged; no open PRs targeting `main` for this milestone.
3. ✅ [CHANGELOG.md](./CHANGELOG.md) has an entry for this version with what changed.
4. ✅ `pyproject.toml` version matches the tag.
5. ✅ All ADRs are `accepted` or `superseded` (no lingering `proposed`).
6. ✅ Archive [docs/prd.md](./docs/prd.md) → `docs/archive/prd-vX.Y.md`; rewrite [docs/prd.md](./docs/prd.md) for the next milestone.

A `scripts/release_check.py` will automate steps 1–5 once v0.1.0 nears ship. Until then, run the checklist by hand.

## When making scope changes (checklist)

If a PR discovers something that affects future scope:

1. **A v0.2 item should land in v0.1?** → Add a T-task to [docs/prd.md §11](./docs/prd.md#8-implementation-tasks-t01t27), remove the entry from [docs/roadmap.md](./docs/roadmap.md), in the same PR.
2. **A v0.1 item should defer?** → Remove from [docs/prd.md §11](./docs/prd.md#8-implementation-tasks-t01t27), add to [docs/roadmap.md](./docs/roadmap.md), update the acceptance criteria in §12 accordingly. Justify in the PR description.
3. **An ADR needs revisiting?** → Don't edit the old ADR. Write a new one with `status: accepted` and add to the old one's frontmatter `status: superseded by ADR-NNNN`.

## Things to avoid

- **Don't relitigate ADRs** without a new one that supersedes. The ADRs exist precisely so the same debates don't recur.
- **Don't add features not in the current PRD §11.** Scope creep is the dominant failure mode for solo research projects. If you spot something worth doing, file it as a polish issue or propose a roadmap update.
- **Don't merge a PR with red CI** — even "I'm sure this test is flaky." Investigate the flake or quarantine the test explicitly.
- **Don't `--no-verify` or `--no-gpg-sign`** to skip hooks. Fix the hook or the issue.
- **Don't force-push to `main`.** Force-push to your own feature branch is fine.

## Communication norms with coding agents

When handing a task to a coding agent (Claude Code, etc.):

- Point at the specific T-task section in [docs/prd.md §11](./docs/prd.md#8-implementation-tasks-t01t27), the architecture docs it depends on, and the relevant ADRs.
- Confirm the agent has read [docs/context.md](./docs/context.md) — the terminology is canonical and not negotiable.
- Ask for a summary back before the agent writes code (Q: "what's the deliverable, what acceptance criteria do you understand, what files will you touch?"). Misalignment is much cheaper to catch before code is written.
- Expect the agent to follow this workflow: branch named `feat/T<NN>-<slug>`, conventional commits, Draft PR with the template filled in, flip to Ready when green.
