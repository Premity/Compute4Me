# CLAUDE.md

Guidance for AI coding assistants working in this repo.

## What this is

**Compute4Me** is a Docker-native, master-orchestrated fabric for embarrassingly parallel deep-learning work (hyperparameter search, batch inference) on heterogeneous, firewall-constrained machines. A Master container opens a Room; Workers join with one `docker run` and an Invite Token, connecting outbound only; the Scheduler places Tasks using measured capabilities. v0.1 is also the substrate for a scheduler paper (3-arm comparison against Ray). Solo project; Python 3.13; one Docker image.

## Read first, in this order

1. [docs/plan.md](docs/plan.md): phases, task index, Definition of Done, open items.
2. **The task card** in [docs/tasks/](docs/tasks/README.md) you're working on (for a stub task, the stub in plan.md; writing the full card comes first, with the user).
3. Every ADR and architecture section the card links.
4. [docs/context.md](docs/context.md): canonical terms. Use them exactly (Master, Worker, Room, Invite Token, Capability Profile, Job, Task, Artifact, Event, …).
5. [CONTRIBUTING.md](CONTRIBUTING.md): branches, commits, PR lifecycle, tests.
6. [docs/prd.md](docs/prd.md) when scope or acceptance is in question; it wins over every other doc.

Then check the live state: `git status`, `git log --oneline -10`, `gh pr list`, `gh issue list`.

## Non-negotiables

- **Settle the card's "Decide first" items with the user before coding.** One question at a time, each with a recommendation. If the docs or code answer it, look it up instead of asking. Record each answer in the card's History line (and an ADR if it qualifies).
- **Verify in the image** ([ADR-0020](docs/adr/0020-docker-is-the-verification-surface.md)). Run the card's "Verify in Docker" step and paste the output in the PR. Never write "No Docker rebuild needed" unless the card says so.
- **No ML framework in the package or the image.** torch etc. live only in user containers and the bench image ([ADR-0016](docs/adr/0016-benchmark-runs-as-a-container.md)). Anything that might pull torch is imported lazily.
- **Module boundaries:** `worker` never imports `master` and vice versa; `sdk` imports nothing from the package; `types`/`proto`/`errors` sit at the bottom ([ADR-0017](docs/adr/0017-python-toolchain.md)).
- **Logging:** `logging.getLogger(__name__)`; never `print` in library code; never log tokens, signing keys or Job `env` values; nothing fails silently; state transitions are Events ([ADR-0018](docs/adr/0018-logging-and-events.md), [style-guide §Logging](docs/style-guide.md#logging)).
- **The Worker uses the host's Docker** through the socket: container GPU flags and volume paths refer to the **host**, not the Worker container.
- **Wire changes are additive only** ([wire-protocol.md §Versioning](docs/architecture/wire-protocol.md#versioning-of-the-wire-protocol)).
- **Docs travel with code** in the same PR (CONTRIBUTING has the table). Don't let a doc contradict the code; if you find a contradiction, fix it or raise it, never silently work around it.
- **Decisions are recorded.** Small ADR changes are edited in place with a dated History line; reversals need a new superseding ADR.
- **Never invent** API behaviour, version numbers or figures. Check the installed library or the docs; mark anything unchecked **Unverified**.
- **Python 3.13 only** (`requires-python <3.14`).

## Ask before

Each commit, pushing, opening/updating/readying a PR, merging, editing GitHub issues or settings, deleting branches or files, installing system packages, pulling multi-GB images (the bench image), and anything that sends data to an external service.

## Commands

```bash
make dev                 # uv sync + pre-commit hooks
make check               # lint + types + tests (no Docker/GPU)
make image               # build ghcr.io/premity/compute4me:dev
make image-smoke         # build + --help + version            (from T28)
make smoke               # compose: Master + Worker join smoke  (from T31)
uv run pytest -m 'task("T16")'    # one task's tests
```

## Conventions

- Branch `feat/T<NN>-<slug>` (tooling tasks: `chore/T<NN>-<slug>`); PR title `feat(T<NN>): <card title>`; squash-merge.
- **≥ 2 commits per task, split by seam** (`feat:` code, `test:` tests, `docs:` docs/changelog/index); one commit only when the change is atomic.
- Tests carry `@pytest.mark.task("T<NN>")` plus `unit` or `integration` (plus `requires_docker`/`requires_gpu` as needed); update `tests/INDEX.md`.
- Diagrams are Mermaid; render them locally (`npx -y @mermaid-js/mermaid-cli@11 -i file.md -o /tmp/out.md -e png`) and look at the PNG. No `;` in sequence-diagram text.
- Real problems that changed a design go in [docs/background/challenges-faced.md](docs/background/challenges-faced.md).
