---
status: accepted
date: 2026-11-10
---

# The Docker Image Is the Verification Surface

## Context

Compute4Me's delivery surface is one Docker image run two ways (`serve`, `worker`), plus a host Docker socket for user containers. A green `uv run pytest` does not prove the image works. During T01 the Docker build found a real bug (an editable install left the package outside the runtime venv) that local testing had passed, and the decision "verify locally now, dockerise later" was reversed mid-task. But from T02 to T09 every PR said "No Docker rebuild needed": `serve` and `worker` were unimplemented until T22, so there was nothing to run, and CI never built the image. The T09 Worker image could not join a Room ([ADR-0016](./0016-benchmark-runs-as-a-container.md)), and nothing noticed.

## Decision

1. **CI builds the image on every PR** (`ci-image`: build, `--help`, `version`) and runs a **compose smoke test** (`ci-compose`: a Master container and a Worker container; the Worker joins; checked from the Master's event log). Both are required checks.
2. **Every task card has a "Verify in Docker" step** with exact commands and expected output, pasted into the PR. "No image impact" is allowed only when the card says so and why.
3. **The runnable minimum comes first.** `serve`, `token issue` and `worker` are wired in P1 (T31), before any more features, so every later task has something to verify against.
4. Integration tests on localhost stay the fast inner loop; they do not replace the image check.

## Why

1. **Bugs live at the boundary between the package and its packaging:** install mode, missing system packages (`docker-cli`), PID 1 signal handling, unbuffered output, volume paths seen by the host daemon. Only running the image exercises them.
2. **Making it a required CI check** removes the per-PR judgement call that let "no rebuild needed" become the default.

## Alternatives considered

- **Manual Docker checks only at phase ends:** cheaper per PR, but that is how the T09 join failure went unseen.
- **Run the whole test suite inside the image:** thorough but slow, and the image deliberately has no dev dependencies.

## Consequences

- CI time per PR grows by the image build plus the compose run (target under 5 minutes, with BuildKit layer caching).
- The compose smoke uses `C4M_BENCHMARK=skip`, so CI never pulls the multi-GB bench image; the bench path is checked by hand on a GPU host and recorded on the "Needs the real fleet" issue.

## History

- 2026-11-10: Accepted (planning rewrite).
