# Challenges faced

The real problems hit while building Compute4Me: ones that forced a design change, would have produced wrong behaviour, or blocked progress. It feeds the paper's and the eventual write-up's "lessons" section, and explains to a future reader why some things are the way they are.

**What belongs here:** a problem that changed a design, would have quietly produced wrong results, or stopped progress, with evidence. Small slips (a typo, a test fixed on the spot) don't; their fixes live in commit messages and ADR History lines.

**Adding one:** in the PR that solves it, under the task's heading, using the same five parts:

- **The problem:** what went wrong and why it mattered.
- **How we found it**
- **Why it happened**
- **What we did**
- **Evidence:** the ADR, test, PR or run that shows it.

## T01: Repo skeleton and image

### 1. The package wasn't in the image, and only the Docker build showed it

- **The problem:** the image built, but `compute4me` couldn't be imported at runtime. The builder stage installed the project *editable*, which writes a `.pth` pointer back to `/app/src`, and the runtime stage copied only the venv, so the pointer led nowhere.
- **How we found it:** building and running the image during T01, after first planning to "dockerise later". Local `uv sync` and `pytest` were green.
- **Why it happened:** uv installs the project editable by default, which is right for development and wrong for a multi-stage image.
- **What we did:** `uv sync --frozen --no-dev --no-editable` in the builder, so the package is baked into the venv's `site-packages`; and the decision that the image is verified per task, not later.
- **Evidence:** [Dockerfile](../../Dockerfile) (`--no-editable` with its comment); PR #1; [ADR-0020](../adr/0020-docker-is-the-verification-surface.md).

## Planning rewrite (2026-11-10, after T09)

An audit before P2 (comparing the repo with a sibling project's process and running every tool) found the problems below. Each had already cost a debugging detour or would have.

### 2. The shipped Worker image could never join a Room

- **The problem:** `profile()` runs the ResNet18 benchmark directly. The benchmark needs torch; the Worker image deliberately has none (user containers carry the ML stack), so `profile()` raised `BenchmarkUnavailable` and the Worker never sent `join`. The documented fix, `scripts/setup-worker.sh`, installed torch on the **host**, which the Worker *container* can't see. It also chose the wrong wheel: its `case` matched `12.*` before `12.1|12.2|12.3`, and CUDA 13 drivers fell through to a **CPU** build, which would have benchmarked a GPU host on its CPU and fed the Scheduler a wrong speed. deployment.md meanwhile said the Worker "runs fine" without torch.
- **How we found it:** reading `profile()` against the Dockerfile and the deployment docs during the audit; T09's tests injected a fake benchmark, so they never exercised the real path.
- **Why it happened:** T09 was verified with pytest only ("No image rebuild needed"), and `worker` couldn't be run from the image anyway (see 4).
- **What we did:** the benchmark becomes its own image, run by the Worker through the host Docker socket on the same GPU; a failed benchmark no longer blocks joining.
- **Evidence:** [ADR-0016](../adr/0016-benchmark-runs-as-a-container.md); [T30 card](../tasks/T30-benchmark-container.md).

### 3. "Passes locally" didn't mean "passes in CI" didn't mean "works in the image"

- **The problem:** four kinds of drift.
  - The local venv was Python **3.14.10**, while the image and mypy targeted 3.13: there was no `.python-version` and no upper bound on `requires-python`.
  - Ruff existed at three versions (lock 0.15.15, pre-commit v0.9.10, pyproject `>=0.9`).
  - The pre-commit mypy hook saw only `pydantic`, so its `--strict` result differed from CI's.
  - `pre-commit` wasn't a dependency at all, so `make dev` failed on its second line and no hook had ever run.
- **How we found it:** running `uv run pre-commit --version` ("No such file") and `uv lock --check` (which reported "Using CPython 3.14.10") during the audit.
- **Why it happened:** the hooks were configured before `pyproject.toml` existed and never revisited; floating `>=` pins hid the drift.
- **What we did:** one pinned Python, exact tool pins, local hooks running through `uv run`, and CI that builds the image.
- **Evidence:** [ADR-0017](../adr/0017-python-toolchain.md); [T28 card](../tasks/T28-dev-tooling.md).

### 4. Nothing could be run from the image until P4

- **The problem:** `serve`, `worker` and `token issue` were scheduled for T22 (P4). For nine tasks the image could only print `--help`, so the P1 tracer bullet ("a Worker joins") existed only inside pytest, every PR said "No Docker rebuild needed", and problem 2 went unnoticed.
- **How we found it:** reading `cli.py` and the PR history (#3–#10) during the audit.
- **Why it happened:** the task order followed the module layers (types → store → transport → … → CLI) rather than "runnable first".
- **What we did:** a new P1 task wires the minimal CLI and adds a compose smoke test to CI, before any more features.
- **Evidence:** [ADR-0020](../adr/0020-docker-is-the-verification-surface.md); [T31 card](../tasks/T31-runnable-cli.md); [plan.md](../plan.md#phases).

### 5. The docs contradicted the code, GitHub and each other

- **The problem:** an agent (or a returning human) follows the docs, and the docs were wrong in ways that changed behaviour:
  - wire-protocol §5.1 said the token carries the Master URL, contradicting ADR-0015;
  - context.md used field names the code doesn't have (`cpu.cores`, `datasets.cached`) and said the Master aggregates gradients in v0.1;
  - operations.md gave a 60 s reconnect cap (the code uses 30 s) and a wildcard certificate SAN that doesn't exist;
  - CONTRIBUTING claimed branch protection, required checks and auto-delete, none of which were set;
  - task links pointed to "PRD §11" when tasks lived in §8.
- **How we found it:** reading every doc against the code and the GitHub API during the audit.
- **Why it happened:** task specs were 2–4 lines in the PRD, so details were settled ad hoc in PRs and written back only to the doc the PR happened to touch.
- **What we did:** task specs moved to full cards with a "Decide first" section and a History line; the Definition of Done requires the docs that a change touches; ADRs are edited in place with History lines; the link checker gains anchor validation.
- **Evidence:** [plan.md](../plan.md), [tasks/](../tasks/README.md), [adr/README.md](../adr/README.md#changing-an-adr), [T28 card](../tasks/T28-dev-tooling.md) (link checker).
