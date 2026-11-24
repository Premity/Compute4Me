---
description: Rigorous review of a Compute4Me pull request (code, Docker verification, decisions, docs), drafted for a human to post
argument-hint: <PR number> [re-check]
---

# Review Compute4Me PR #$ARGUMENTS

You are reviewing a pull request in Compute4Me, a Docker-native, master-orchestrated fabric
for embarrassingly parallel deep-learning work (Master and Worker containers, smart-pull
scheduling, a scheduler paper on top). A review here decides whether the code, its **Docker
verification** and the **decisions** in the PR can be trusted by the tasks that build on it.
Name what is good as specifically as what is wrong.

**Do not post anything to GitHub.** Write the review in chat as a draft for the user to read,
edit and post. Never approve, merge, push, comment on, or edit the PR or its issue.

## 0. Ground rules

- **Evidence over impression.** Every finding cites `file:line` at the reviewed commit, a
  command you ran, or output you reproduced. If you couldn't check something (no Docker, no
  GPU, no fleet), say so and why.
- **Try to falsify each finding before reporting it.** Read the code path end to end and grep
  for the "missing" thing before claiming it's missing. A wrong finding costs the author more
  than a missed nit.
- **Separate blocking from non-blocking.** Blocking: wrong behaviour, a broken contract (wire,
  Container Contract, module boundary), a secret in logs, red CI, a merge conflict, a missing
  Verify-in-Docker step. Everything else is "smaller" or "side note, not this PR's".
- **Don't invent** API behaviour, versions or figures. Mark anything unchecked **Unverified**.
- Explain plainly: what goes wrong and for whom first, then the technical detail.

## 1. Set up

1. `gh pr view $1 --json title,body,headRefName,headRefOid,baseRefName,mergeable,statusCheckRollup,reviews,comments,files`
   and `gh api repos/{owner}/{repo}/pulls/$1/comments`. Record the **head SHA**: the review is
   of that commit.
2. Fetch without disturbing the working tree (`git fetch origin pull/$1/head`, or a worktree),
   diff against the merge base, and read **every** changed file in full.
3. Read, in order: the task card in `docs/tasks/` (Decide first, Steps, Verify in Docker, Done
   when), the linked issue, every ADR and architecture section the card links, `CLAUDE.md`
   and `CONTRIBUTING.md`, and `docs/context.md` for any term the PR uses.
4. **Re-check** (`re-check` in the arguments, or earlier reviews exist): list every earlier
   point with its status (fixed / open / disputed) and the commit that addressed it, and
   verify each fix yourself.

## 2. Run things

- `make check`, and the PR's new tests by name (`uv run pytest -m 'task("T__")'`). Report counts.
- The card's **Verify in Docker** step against a freshly built image (`make image`), and
  compare with the output pasted in the PR. Missing or different output is blocking (ADR-0020).
- Any `requires_docker` tests if Docker is available; say what was skipped.
- CI state from `statusCheckRollup` (red is blocking) and `mergeable`.
- Never pull the multi-GB bench image, use a GPU, or start anything long-running without
  asking the user first.

## 3. Check the decisions

- Every **Decide first** item is answered in the PR, recorded in the card's History line, and
  in an ADR when it qualifies. Decisions that ride along in an unrelated PR are called out.
- No contract changed silently: wire messages are **additive only**; the Container Contract
  (`C4M_*` env in, files out) is unchanged unless an ADR says so; data-model changes are
  additive.
- Docs state the current truth; history lives only in History lines and commit messages.

## 4. Check the code

- **Module boundaries** (ADR-0017): `worker` never imports `master` and vice versa; `sdk`
  imports nothing from the package; `types`/`proto`/`errors` at the bottom.
- **No ML framework** in the package or image; anything that could pull torch is lazy.
- **Logging** (ADR-0018): `logging.getLogger(__name__)`, no `print` in library code, nothing
  fails silently, state transitions are Events, and **no tokens, signing keys or Job `env`
  values** in any log line, error or exception text (Pydantic errors echo inputs).
- **Docker-outside-of-Docker:** GPU flags and volume paths given to `docker run` from the
  Worker refer to the **host**, not the Worker container.
- **Python 3.13**; async code cancels and awaits its tasks; sockets and files are closed.
- **Correctness:** walk each new function with concrete inputs, including edges (empty,
  reconnect mid-message, a Worker dying, a revoked token, a restart). Look for swallowed
  exceptions, races between the WebSocket handler and the store, and unclear error messages.
- **Tests:** would they fail if the code were wrong? Markers `task("T__")` plus `unit` or
  `integration` (plus `requires_docker`/`requires_gpu`); `tests/INDEX.md` updated.
- **Where else is this assumed?** Grep the repo and the later task cards for code and docs
  that assume the old behaviour.

## 5. Check git and docs

- Title `feat(T__): <card title>` (or `fix:`/`docs:`/`chore:`); ≥ 2 commits split by seam
  unless the change is atomic; no secrets, keys, `.pem` files or data committed.
- The card's Status and Done-when match reality, each Done-when item with evidence.
- Docs travel with code (CONTRIBUTING's table): architecture, context, CHANGELOG
  `[Unreleased]`, ADR History lines; Mermaid diagrams render; links resolve.
- Hand-offs to later tasks are written into *those* tasks' cards.

## 6. Write the review

Draft it in chat, in this shape:

```
## Review of T__ (`<short head SHA>`)

**Verdict: <approve | changes requested on points X, Y | comment only>.** One or two
sentences on why, and what blocks the merge.

What I checked: <commit, commands and test counts, Docker verification, what I couldn't run and why>.

What's especially good:
- <specific, with file:line>

### Points to address
**1. <one-line claim>.** <where, evidence, why it matters, concrete fix>. Blocking?

### Smaller
**N. …**

**Side note, not this PR's:** …
```

For a re-check, lead with a status table of every earlier point, then any new ones.

Below the draft, tell the user in two or three plain lines: what blocks the merge, which
findings you're least sure of, and what you couldn't check.
