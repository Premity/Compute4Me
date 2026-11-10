# Task cards

One file per task. The index, phases, dependency graph and Definition of Done are in [../plan.md](../plan.md). Tasks in later phases are stubs in the plan until their detailing session.

## How to use a card

Starting a session with a coding agent? Paste [session-prompt.md](./session-prompt.md).

1. Read the whole card, then every ADR and architecture section it links.
2. Settle every item under **Decide first** with the user before writing code. Record the answer in the card's History line (and in an ADR if it is an engineering decision someone would later ask "why?" about).
3. Branch `feat/Txx-<slug>` from up-to-date `main`, open a draft PR early, and copy **Done when** into the PR description.
4. When the code works, run the **Verify in Docker** step and paste its output into the PR.
5. Set **Status** to `Done (PR #N)` in the same PR.

## Card template

Copy this for a new card.

```markdown
# Txx: Title

| | |
|---|---|
| Phase | P1–P5 |
| Size | M / L / L+ (hours) |
| Depends on | Txx, Txx |
| Unblocks | Txx |
| Branch | `feat/Txx-short-name` |
| Issue | #N |
| Status | Not started / In progress / Done (PR #N) |

## Why this task exists
One paragraph: what it gives the project and who needs it next.

## Background you need
Everything needed to start without searching: the existing code to read (with paths), how the libraries behave, known gotchas.

## Decide first
Each open question with options and a **Recommendation**. Settle with the user before coding.

## Steps
Numbered, mapped to the Done-when list.

## Outputs
Files created or changed.

## Tests
File, markers, and what each test proves.

## Verify in Docker
The exact commands to run against the built image, and what to expect. Or "No image impact" with the reason.

## Done when
- [ ] …

## If this fails
Ordered fallbacks, each with the point at which to switch.

## References

## History
- YYYY-MM-DD: what changed and why.
```
