# Session prompt: starting a task with a coding agent

Paste everything below the line into a new session. Fill in the blank marked `<…>`.

---

I'm building **Compute4Me** (repo: this directory; GitHub: https://github.com/Premity/Compute4Me, public), a Docker-native, master-orchestrated deep-learning fabric. Planning is done; this session implements one task.

**This session:** task `<T__>` (or "help me pick the next one from docs/plan.md").

## 1. Read before doing anything

Read these in order; the cards assume you know the decisions.

1. `CLAUDE.md`: non-negotiables and commands.
2. `docs/plan.md`: phases, task index, dependency graph, open items, Definition of Done.
3. **The task card** `docs/tasks/T__-*.md`, in full. For a stub task (P3–P5), writing the full card from the stub and the template in `docs/tasks/README.md` comes first, with me.
4. Every ADR (`docs/adr/`) and architecture section (`docs/architecture/`) the card links.
5. `docs/context.md` (terms are canonical) and `CONTRIBUTING.md` (workflow).
6. The existing code and tests the card names.
7. `docs/background/challenges-faced.md`, so the same problems aren't hit twice.

Then check the live state: `git status`, `git log --oneline -10`, `git branch -a`, `gh pr list`, `gh issue list`. Confirm the task's dependencies are merged and that `make check` is green on an up-to-date `main`; if setup is broken, fix that first.

## 2. How I want to work

**Before writing code:**

- Summarise in a few lines what the task delivers, what it depends on and what it unblocks.
- Give your plan as short steps mapped to the card's **Done when** list.
- Go through the card's **Decide first** items **one at a time**, each with your recommendation and the reason, and wait for my answer. If the code or docs answer a question, look it up instead of asking.
- Point out anything in the card that looks wrong, stale or contradicted by another doc or by the code. Don't silently work around it.
- Wait for my "go".

**While working:**

- Branch `feat/T__-<slug>` (tooling tasks: `chore/T__-<slug>`) from up-to-date `main`. Never commit to `main`.
- Ask me before: each commit; pushing; opening, updating or readying a PR; merging; editing issues or repo settings; deleting branches or files; installing system packages; pulling multi-GB images; anything that sends data to an external service.
- ≥ 2 commits split by seam (`feat:` / `test:` / `docs:`), Conventional Commit messages; PR title `feat(T__): <card title>`.
- When you hit a real decision mid-task (a card fallback, an API that doesn't behave as documented, a number that looks wrong), stop and discuss it with a recommendation.
- Never invent API details, versions or figures; check the installed library or the docs and mark anything unchecked **Unverified**.
- Docs travel with the code (CONTRIBUTING's table). Record decisions in the card's History line and in an ADR when it qualifies; tell me which files you touched.
- Real problems that changed a design go in `docs/background/challenges-faced.md`.

**Verification:**

- Tests as the card specifies, with `task("T__")` and kind markers; update `tests/INDEX.md`.
- Run `make check`, then the card's **Verify in Docker** step against a freshly built image, and paste the output in the PR.
- Render any Mermaid diagram you add and look at it.

**Reporting back:**

- At natural checkpoints: what's done, what's next, what I need to decide.
- At the end: go through **Done when** item by item (done / not done, and why), with the real `make check` and Docker output. If something was skipped or failed, say so plainly.
- Update the card's Status in the PR, and remind me of anything that needs a human: real-fleet checks, GPU hosts, repo settings.

Start with step 1. Then give me the summary, the plan and the first Decide-first question.
