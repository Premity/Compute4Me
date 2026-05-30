## What
<!-- 1–3 sentences: what this PR delivers. -->

## T-tasks
Closes T<NN> (see [docs/prd.md §11](../docs/prd.md#8-implementation-tasks-t01t27)).
<!-- For clusters: Closes T<NN>, T<MM>. -->

## Acceptance criteria
<!-- Copy verbatim from the PRD task's Acceptance section. Check off as verified by automated or manual tests. -->
- [ ] <criterion 1>
- [ ] <criterion 2>

## Tests

### Automated (CI)
<!-- New/modified test files + their pytest markers. The CI status badge above shows pass/fail. -->
- `tests/unit/test_<module>.py` — `task("T<NN>")`, `unit`
- (etc.)

### Manual

**Verification** (scripted; commands + expected outcomes):
- [ ] <command> → <expected outcome>
- [ ] <command> → <expected outcome>

**Exploratory** (free play, ~15–30 min):
- [ ] Used the new functionality end-to-end and judged ergonomics
- [ ] Tried edge cases (bad inputs, mid-operation cancellation, etc.)

Findings:
<!-- For each: (blocker / polish / spec-issue) — description → fixed here / filed as #N / PRD update in this PR -->
- _none_

## ADRs touched
<!-- ADRs consulted or affected (often none). New ADRs in this PR live in docs/adr/. -->
- _none_

## Docs touched
<!-- CONTEXT.md, ROADMAP.md, PRD.md, README.md, INDEX.md changes that travel with this PR. -->
- _none_

## Notes / follow-ups
<!-- Deferred items, known issues, things to address in a later T-task (or "none"). -->
- _none_
