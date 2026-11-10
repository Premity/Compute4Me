## What

<!-- 1–3 sentences: what this PR delivers. -->

## Task

Closes #<issue> · Card: [`docs/tasks/T<NN>-….md`](../docs/tasks/) · Plan: [docs/plan.md](../docs/plan.md)

<!-- Non-task work (fix/docs/chore): delete this section. -->

## Decisions settled

<!-- Every "Decide first" item from the card, with the answer and where it's recorded (card History, ADR). "None" if the card had none. -->

- _none_

## Done when (copied from the card)

- [ ] <criterion 1>
- [ ] <criterion 2>

## Checks

- [ ] `make check` passes locally; every CI job is green
- [ ] Tests carry `task("T<NN>")` + `unit`/`integration`; [tests/INDEX.md](../tests/INDEX.md) updated
- [ ] No secrets, tokens or keys in code, tests, logs or this description

## Verify in Docker

<!-- The card's "Verify in Docker" commands and their actual output (trim long logs). "No image impact" only if the card says so. ADR-0020. -->

```text

```

## Manual

**Verification** (scripted; commands + expected outcomes):

- [ ] <command> → <expected outcome>

**Exploratory** (15–30 min):

- [ ] Used the feature end to end; judged errors, defaults and ergonomics
- [ ] Tried edge cases (bad input, interruption, restart)

Findings (each: blocker / polish / spec-issue → fixed here / issue #N / doc updated here):

- _none_

## Docs touched

- [ ] Card Status and History
- [ ] [CHANGELOG.md](../CHANGELOG.md) `[Unreleased]`
- [ ] Architecture / context / roadmap / PRD (list): _none_
- [ ] ADRs (new, or History line): _none_
- [ ] [challenges-faced.md](../docs/background/challenges-faced.md) if a real problem changed the design: _none_

## Follow-ups

<!-- Filed as issues, not just listed here. -->

- _none_
