# Style Guide

Conventions for Python code and Markdown docs in Compute4Me. Short and opinionated. The discipline is "consistent across the project," not "follows every recommendation in some external guide."

Tooling automates as much as possible — `ruff` for Python style, `mypy --strict` for types, `mdformat` for Markdown layout, `scripts/check_md_links.py` for link sanity. This document captures the parts that tools can't enforce.

## 1. Python code

### Naming

| Kind | Convention | Example |
|---|---|---|
| Module file | `lowercase_with_underscores.py` | `cost_model.py` |
| Class | `UpperCamelCase` | `CapabilityProfile` |
| Function, method, variable | `lowercase_with_underscores` | `next_task_for` |
| Constant | `UPPER_SNAKE_CASE` | `DEFAULT_HEARTBEAT_SEC` |
| Type alias | `UpperCamelCase` | `ArtifactHash` |
| Private helper | leading underscore | `_validate_token_signature` |
| Dunder methods | only real Python protocols | `__init__`, `__enter__` |

Never invent your own `__double_underscored__` names.

### Type hints

- **Required everywhere.** Enforced by `mypy --strict`.
- No `Any` without an explanatory comment.
- `from __future__ import annotations` at the top of every module. Lets us use forward references without quoting and keeps annotations cheap at import time.
- Prefer builtin generics (`list[str]`) over `typing` imports (`List[str]`).
- `Optional[X]` or `X | None` — pick one per module, don't mix.
- No `from typing import *`; always explicit imports.

### Docstrings

Google style. Tool support is widest (PyCharm, VSCode, Sphinx) and the format is the most scannable.

- **Module docstring** at the top of every module — one paragraph stating purpose. Not an exhaustive content list.
- **Public API methods** (anything reachable via `compute4me.__init__`): full docstring with `Args:`, `Returns:`, `Raises:`.
- **Private helpers**: one-line docstring only if the name isn't self-explanatory. Skip otherwise.
- **Never multi-paragraph docstrings on internal functions.** If you need that much explanation, the function is doing too much, or the reasoning belongs in an ADR.

Example:

```python
def issue(room: str, max_workers: int | None, ttl: timedelta) -> str:
    """Issue a new Invite Token for a Room.

    Args:
        room: Room name to issue the token for.
        max_workers: Cap on concurrent Workers using this token; None = unlimited.
        ttl: How long the token is valid from now.

    Returns:
        Signed JWT-style token string.

    Raises:
        ValueError: If room does not exist.
    """
```

### Comments

Default: **write no comment**. Add one only when removing it would confuse a future reader.

- **Explain WHY, not WHAT.** The code says what; comments add reasoning.
- ❌ `# increment counter` — restates the next line
- ❌ `# refactored from old_module.py` — belongs in git log
- ❌ `# TODO: fix this` — without owner or issue link, it's noise
- ✅ `# Retry up to 3 attempts because cloud APIs occasionally return 503 even when healthy.`
- ✅ `# See ADR-0006 — env-vars-in/files-out is the trust boundary.`

**No `TODO:` comments without a linked issue.** Either fix it now, or file a polish issue and reference it: `# TODO(#42): handle the multi-shard case.` Anything else is noise that accumulates.

### Error handling

- **Raise exceptions; don't return error codes or Result types.** Python idiom.
- **Catch specific exceptions.** Never bare `except:` or `except Exception:` unless re-raising or logging-then-raising.
- **Custom exception classes for the public API** (see [architecture/error-handling.md](./architecture/error-handling.md)). Internal code can raise built-ins (`ValueError`, `RuntimeError`).
- **`assert` is for internal invariants only** — never for input validation, since assertions are stripped under `-O`. Use explicit `raise ValueError(...)` for input checks.

### Logging

Decision record: [ADR-0018](./adr/0018-logging-and-events.md).

- **One logger per module:** `log = logging.getLogger(__name__)` at module top. Never `print()` in library code.
- **Library code never configures logging** (no `basicConfig`, no handlers). Only CLI entry points call `compute4me.log.setup_logging()`.
- **Levels:** `ERROR` = something ended badly and needs a human (cert-pin mismatch, unrecoverable config). `WARNING` = recovered but suspicious (reconnect, dropped frame, benchmark unavailable). `INFO` = lifecycle milestones (listening, joined, Job submitted). `DEBUG` = per-message and periodic detail (heartbeats, wire dumps).
- **Structured fields, not string-pasting:** `log.info("worker joined", extra={"worker_id": wid, "gpu": model})`. The JSON formatter emits them as keys.
- **Never log secrets:** tokens (the redaction filter is a safety net, not a licence), signing keys, Job `env` values. Log a token's `jti` instead.
- **State transitions are events, not just log lines:** use `EventLog.emit(...)`, which also logs. Heartbeats are never events.
- **Nothing fails silently:** every `except` that swallows an error logs it (at least `WARNING`) with the exception text.

### Imports

- `ruff`'s `I` rules handle ordering: stdlib → third-party → local, alphabetized within groups.
- **No `import *`.** Always explicit.
- **Prefer `from module import Name` over `import module as alias`** — explicit > aliased. Aliasing is fine for established conventions like `import numpy as np`.
- **Type-only imports** under `if TYPE_CHECKING:` when they would cause runtime circular imports.

### Data classes — three options

| Use | Tool | Why |
|---|---|---|
| Wire models, validation boundaries (anything crossing process or network), config | **Pydantic `BaseModel`** | Validation, JSON round-trip, helpful errors on bad input |
| Internal pure data with no validation needs, especially when used as dict keys or in sets | **`@dataclass(frozen=True)`** | Lightweight; no Pydantic overhead |
| Dict shapes you have to keep as dicts (parsed JSON you're not validating) | **`TypedDict`** | Avoids unnecessary conversion |

Default to Pydantic. Reach for the other two only when there's a concrete reason.

### Testing

- **File:** `tests/unit/test_<module_under_test>.py` (mirrors source layout).
- **Function name:** `test_<unit>_<scenario>_<expected>`, e.g., `test_scheduler_assigns_biggest_task_to_fastest_worker`.
- **Body:** Arrange / Act / Assert sections separated by blank lines.
- **One logical assertion per unit test.** Multiple OK in integration tests.
- **Fixtures over `setUp/tearDown`.** Pytest fixtures only; no `unittest.TestCase`.
- **Every test declares** `@pytest.mark.task("T<NN>")` + one of `.unit`/`.integration` + any `.requires_*` it needs (enforced by `tests/conftest.py` from T28). See [CONTRIBUTING.md §Tests](../CONTRIBUTING.md#tests).
- **Shared fixtures and fakes** live in `tests/conftest.py` and `tests/fakes/`; don't copy a helper into a second test file, move it there.

### Async

- Sync APIs are primary (see [architecture/wire-protocol.md §5.7](./architecture/wire-protocol.md)).
- Async code lives in `compute4me.async_` submodule. The trailing underscore avoids conflict with the `async` keyword.
- When sync and async coexist at the same level, suffix async functions with `_async` (e.g., `submit_search` vs `submit_search_async`). When inside a fully-async module, no suffix needed.

### What we deliberately *don't* do

- **No mypy plugins** beyond `pydantic`'s. Stay close to stdlib.
- **No `attrs`.** Pydantic + dataclasses cover the use cases.
- **No custom decorator metaprogramming** for "magic" behavior. Explicit > clever.
- **No `**kwargs` passthrough** as a primary API style — type hints lose meaning.
- **No coverage threshold.** Coverage reported, not gated.

## 2. Markdown / docs

### Voice

- **Present tense, neutral.** "The Master verifies the token." Not "The Master will verify..." or "We verify..."
- **Imperative for instructions.** "Run `docker exec ...`." Not "You should run..." or "One can run..."
- **No marketing speak.** No "blazingly fast", "delightful UX", "best-in-class", "world-class".
- **No hedging.** "X is useful when Y" beats "X might possibly be useful sometimes." If unsure, write "Unclear; revisit when Z."
- **Concrete > abstract.** "The Master writes a JWT with `room`, `expires_at`, `master_cert_fp` claims" beats "The Master generates an appropriate credential."

### Structure

- **Sentence case headings.** "Job submission schemas" not "Job Submission Schemas".
- **One H1 per file** (the title). Sub-sections H2, H3, rarely H4. Never H5+.
- **Frontmatter only on ADRs** (`status:` field).
- **Section length** is a soft guideline of ~50 lines. Longer sections probably want H3 subdivisions, but the limit is a forcing function, not a hard rule.
- **File length** is a soft guideline of ~500 lines. Longer files probably want splitting.

### Choosing format

| Format | When |
|---|---|
| **Prose** | Connected ideas; cause-and-effect reasoning; explanations |
| **Bullet list** | Parallel items, short (one line each), no internal structure |
| **Numbered list** | Sequential steps OR rankings |
| **Table** | 3+ columns of structured comparison, or rows sharing the same fields |
| **Code block** | Anything copy-pastable; always language-tagged |
| **Mermaid diagram** | Architecture, data flow, sequences, state machines, dependency graphs |

If a list item runs over ~2 lines, it should probably be a sub-section with prose.

### Tables

- Max ~6 columns. Wider → refactor or split.
- Header row always present.
- Don't put long paragraphs in cells — link to a section instead.

### Code blocks

- **Always language-tagged.** `` ```python ``, not bare `` ``` ``.
- Bash blocks: `bash`, not `sh` or `shell`.
- Output blocks: no tag (`` ``` `` alone) or `text` if rendering matters.
- **Copy-pasteable:** real file paths, real Room names, no `<placeholder>` in paths unless explicitly marked.

### Diagrams

All diagrams are **Mermaid** blocks inside the Markdown (changed from ASCII on 2026-11-10): diffable, rendered by GitHub, and good at sequences, state machines and dependency graphs. Terminal-output samples (CLI banners, error messages) stay as `text` code blocks; they are not diagrams.

- **Render before committing:** `npx -y @mermaid-js/mermaid-cli@11 -i file.md -o /tmp/out.md -e png`, and look at the PNG.
- **Pick the right type:**

  | Showing | Mermaid type |
  |---|---|
  | Context, components, deployment, package dependencies, decision logic | `flowchart` |
  | Classes, interfaces, data models, message unions | `classDiagram` |
  | Database tables and keys | `erDiagram` |
  | Message exchanges between processes | `sequenceDiagram` |
  | Lifecycles and connection states | `stateDiagram-v2` |

- **Say what it shows:** an italic line above each diagram: *As built (Txx)* for the code today, *Planned (Txx)* for a card's recommendation, or *Target* / *Concept* for the v0.1 design. A diagram that claims "as built" and disagrees with the code is a bug.
- **One place per diagram,** in the doc that owns the topic, listed in the [architecture diagram index](./architecture/README.md#diagrams). Link to it; don't copy it.
- **In `classDiagram`,** write generics as `list~Task~` (Mermaid's generic syntax); `str | None` renders as written.
- **Avoid known breakages:**
  - no `;` inside sequence-diagram text (it is a statement separator); use commas;
  - no edges to or from a whole subgraph;
  - no floating nodes;
  - wide graphs (more than ~15 nodes) use `flowchart TB`, not `LR`.
- **When a diagram tangles,** use fewer boxes (one box listing several items) and put the detail in a table underneath.

### Cross-references

- **Always relative paths.** `[overview.md](./overview.md)` from inside `docs/architecture/`. Never absolute paths or full URLs to our own GitHub.
- `[text](./path.md)` Markdown syntax. Bare URLs only in citations (research docs).
- Anchor links use GitHub's auto-form: lowercase, hyphens replace spaces, special chars dropped. E.g., `## 9. Eval / research runbook` → `#9-eval--research-runbook` (the `/` is dropped, leaving two hyphens).
- Link text describes the target's content: `see [Container Contract](...)` not `click [here](...) for the Container Contract`.

### Inline code (backticks)

| Thing | Format |
|---|---|
| Filenames | `` `docs/architecture/overview.md` `` |
| Function and class names | `` `Client.from_token()` `` |
| Commands and CLI flags | `` `compute4me serve`, `--max-workers` `` |
| Variable names and env vars | `` `C4M_MASTER` `` |
| **Concept names** from CONTEXT.md (Master, Worker, Room, Token, etc.) | **bold** on first mention or when emphasizing |
| Emphasis | *italic* — rare; only when truly important |

### Density

- **One idea per paragraph.** If a paragraph has two topic sentences, split it.
- **3–5 sentences per paragraph** is the sweet spot. Walls of text don't get read.
- **Front-load the conclusion.** Put the answer in the first sentence of each section; details follow.

### What docs *don't* contain

- **No emoji in main docs.** Matches the CLI default rendering. Exception: documentation *describing* the `--slop` CLI flag may use emojis, since that's the point.
- **No screenshots in v0.1.** Text is more durable; screenshots rot the moment the UI shifts.
- **No version histories inline** ("v0.2 added X, v0.3 added Y"). That's what [CHANGELOG.md](../CHANGELOG.md) is for. The exception is the **History** section of ADRs and task cards, which records how a decision changed.
- **No "Coming soon" sections** for unbuilt features. If it doesn't exist, don't document it. Use [roadmap.md](./roadmap.md) to flag intent.
- **No tutorials or how-to guides in v0.1.** README quick start covers first-time bootstrap. A proper getting-started tutorial lives in [v0.3 docs work](./roadmap.md#v03--fabric-ergonomics--robustness).

### Where each kind of writing goes

| Writing | Lives in |
|---|---|
| First-time visitor pitch, install, quick start | `README.md` |
| What this version builds, scope, acceptance criteria | `docs/prd.md` |
| Terminology | `docs/context.md` |
| What's deferred and why | `docs/roadmap.md` |
| How the system works (durable) | `docs/architecture/` |
| Why a specific structural choice was made | `docs/adr/` |
| What shipped in each release | `CHANGELOG.md` |
| Dev workflow (branches, PRs, tests) | `CONTRIBUTING.md` |
| Vulnerability reporting + threat model | `SECURITY.md` |
| Style conventions | `docs/style-guide.md` (this file) |
| Order of work, phases, Definition of Done | `docs/plan.md` |
| How to do one task (background, decisions, steps, tests) | `docs/tasks/Txx-*.md` |
| Real problems hit and how they were solved | `docs/background/challenges-faced.md` |
| Which checks run where | `docs/architecture/test-map.md` |
| Short guide for AI coding assistants | `CLAUDE.md` |

If a piece of writing fits two categories, pick the more durable one (ADR > architecture > PRD > README). If it fits none, it probably doesn't belong in docs.

## 3. Other file formats

### Shell scripts and small tools

- For anything over ~20 lines, **prefer Python over Bash.** More readable, easier to test, gets ruff/mypy treatment.
- Shebang + module docstring + `if __name__ == "__main__":` block.
- Use `argparse` for any flags; never hand-roll CLI parsing.
- Match the Python style above.

### Dockerfile

- Multi-stage builds. Pin base image versions (`python:3.13-slim` not `python:slim`).
- Layer ordering: `COPY` last for files that change frequently (improves cache hits).
- One `RUN` for build deps, one for runtime deps — separate from `COPY` for layer caching.
- Comments explaining non-obvious flags.

### YAML (CI workflows, pre-commit, Compose)

- 2-space indent.
- Comments explaining each job / step's purpose.
- Don't optimize before profiling. Readable > clever.

## 4. When in doubt

- **Read existing files in this repo.** They set precedent.
- **Match the closest established pattern.** Consistency within the project matters more than abstract correctness.
- **Ask before deviating.** If you have a strong opinion that conflicts with this guide, raise it as a PR — don't silently deviate. Style rules either evolve or they're load-bearing.
