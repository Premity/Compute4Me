# Changelog

All notable changes to Compute4Me are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [Semantic Versioning](https://semver.org/) with the project on `0.x.y` — *no API stability guarantees pre-1.0*.

For per-version Product Requirements (scope, acceptance criteria), see [docs/prd.md](./docs/prd.md) (current milestone) and [docs/archive/](./docs/archive/) (past milestones). For decisions, see [docs/adr/](./docs/adr/).

## [Unreleased]

### Added
- **Planning and process rewrite (docs only; modelled on the Fovea project's process).**
  - `docs/plan.md`: phases, task index, dependency graph, open items, Definition of Done, and stubs for P3–P5.
  - `docs/tasks/`: card template, full cards for T28–T31, T10–T17, and a session prompt for coding agents.
  - New tasks: **T28** dev tooling and CI hardening, **T29** logging and events, **T30** benchmark as a container, **T31** runnable `serve`/`token issue`/`worker` with a compose join smoke, **T32** experiment run records, **T33** `compute4me doctor`.
  - **ADR-0016** benchmark as its own container (fixes the Worker image being unable to join); **ADR-0017** Python toolchain; **ADR-0018** logging, events and log shipping; **ADR-0019** experiment run records; **ADR-0020** the Docker image as the verification surface.
  - `CLAUDE.md`, `docs/background/challenges-faced.md`, `docs/architecture/test-map.md`, and a `Task` issue form.
- **T09 — Capability profiler + micro-benchmark (`worker/profiler.py`)**: `profile()` assembles a `CapabilityProfile` from injectable probes — GPU via `nvidia-smi` (`detect_gpu`, falling back to `model='cpu'`), CPU/RAM/disk via psutil/shutil (`host_stats`), and `datasets_cached` from the cache layout (`scan_cached_datasets`). `ensure_host_id` persists a UUID in the data volume (stable across restarts). `run_micro_benchmark` is the fixed ResNet18 fwd/bwd yardstick (samples/sec); it lazily imports PyTorch and raises `BenchmarkUnavailable` if absent. **PyTorch is the optional `bench` extra** (not in the default install or either image — the user's container carries the real ML stack, ADR-0006); Worker hosts install the CUDA-matched build once via `scripts/setup-worker.sh`. Bandwidth/RTT fields are left `0.0` (Master-probed in T10).
- **T08 — Worker daemon + join handshake (`worker/daemon.py`, `master/server.py`)**: `WorkerDaemon` opens the outbound WSS connection, pins the Master cert by fingerprint, sends `join` with its Capability Profile (injected — the real profiler is T09), and handles `join_ack` (records the assigned `worker_id`) / `join_reject` (raises `JoinRejected` with a reason); `connect_once()` heartbeats on an interval, `run()` reconnects with exponential backoff (1s→30s) after transient drops while treating a reject as terminal. Completes the server side of the handshake: `ControlServer._on_join` now replies `join_ack`/`join_reject`, assigns a `worker_id`, and persists the Worker (`status='idle'`) via the state store. Verified end-to-end by integration tests (join→worker_id, bad/revoked token→reject, Worker persisted, heartbeat keeps the connection, reconnect after a drop).
- **T07 — WebSocket transport server (`master/server.py`)**: `ControlServer` accepts one persistent WSS connection per Worker over the T06 self-signed cert, parses inbound `WorkerMessage`s, and pushes `MasterMessage`s via a per-Worker `asyncio.Queue` (`push`). Tracks connections (`connected_count`, `is_connected(jti)`); on `join` it verifies the token + `admit`s a slot, and `release`s it when the socket closes. Verified by integration tests driving a real WSS client (connect → heartbeat → tracked connected → close → release; plus a Master→Worker push round-trip). Full join handshake/heartbeat-liveness deferred to T08.
- **T06 — Self-signed TLS + fingerprint (`master/server.py`, `worker/daemon.py`)**: the Master generates and persists a self-signed cert (`ensure_cert`, idempotent across restarts — no CA, no domain), exposing its sha256 DER fingerprint (`fingerprint_of`) for the [token service](./docs/architecture/modules.md) to embed in issued tokens. The Worker pins that fingerprint: `pinning_ssl_context` (chain verification off, self-signed) + `verify_fingerprint` compares the presented cert and raises `CertPinError` on mismatch. Verified end-to-end over a real TLS handshake (match connects, mismatch refused). Implements [ADR-0011](./docs/adr/0011-tls-fingerprint-in-token.md).
- **T05 — Token service (`master/tokens.py`)**: `TokenService` with `issue`/`verify`/`revoke`/`admit`/`release` per [modules.md §Token service](./docs/architecture/modules.md). JWT (HS256) sign/verify with an injected Master-held key and cert fingerprint (cert generation lands in T06); standard `exp`/`jti` registered claims; `verify` raises `InvalidToken` on bad signature, expiry, or revoked `jti`. In-memory revocation set (rebuilt from durable metadata on construction, so revocations survive restart) + per-`jti` live-Worker counter for the `max_workers` cap. Adds `save_token`/`set_token_revoked`/`load_revoked_jtis` to the state store (the `tokens` table T03 left model-less).
- **T04 — Wire message models (`proto/messages.py`)**: Pydantic models for every WebSocket control-channel message in [wire-protocol.md §2](./docs/architecture/wire-protocol.md) — Worker→Master (`join`/`heartbeat`/`task_progress`/`task_result`/`profile_update`) and Master→Worker (`join_ack`/`join_reject`/`task_assign`/`task_cancel`/`bandwidth_probe`). Two `type`-discriminated unions (`WorkerMessage`/`MasterMessage`) with `parse_worker_message`/`parse_master_message` helpers that reject an unknown `type` while tolerating unknown fields (additive evolution). `join` carries a full `CapabilityProfile`; `task_assign`/`task_result` reuse `ArtifactRef`/`TaskRequires` and the `TaskResult` outcome fields.
- **T03 — Master state store (`master/state.py`)**: `StateStore`, a SQLite-backed durable store applying the [data-model.md](./docs/architecture/data-model.md) §Master State Store schema on construction (idempotent — reopening an existing DB is a no-op). Upsert `save_room`/`save_worker`/`save_job`/`save_task`/`save_result` plus restart recovery via `load_open_jobs()` (queued/running Jobs) and `load_pending_tasks(job_id)` (non-terminal Tasks). Adds the durable-record models `Room`/`Worker`/`Job` to `types.py` and documents them in `data-model.md`.
- **T02 — Core types (`types.py`)**: Pydantic models per [data-model.md](./docs/architecture/data-model.md) — `CapabilityProfile`/`GpuInfo`, `TokenClaims`, `SearchJobSpec`/`MapJobSpec`/`ShardStrategy`, and the internal `Task`/`TaskRequires`/`ArtifactRef`/`ShardDescriptor`/`TaskError`/`TaskResult`. `ShardStrategy` enforces `n_shards > 0` for non-`whole` kinds. `data-model.md` gains the previously-named-only `ShardDescriptor`/`ArtifactRef`/`TaskError` definitions.
- **T01 — Repo skeleton + packaging + image**: `pyproject.toml` (uv, Python 3.13, ruff + mypy + pytest config), the `src/compute4me/` package per [docs/prd.md §5](./docs/prd.md#5-repository-layout) with docstring-only module stubs, single `Dockerfile` (`serve`/`worker` entrypoints), `Makefile` (`dev`/`test`/`lint`/`types`/`image`/`e2e`), `docker-compose.dev.yml`, `.github/workflows/ci.yml` (`ci-test`/`ci-lint`/`ci-types`), and the `compute4me` CLI surface from [wire-protocol.md §4.1](./docs/architecture/wire-protocol.md).
- Repository layout: `docs/` holds all project documentation (PRD, context, roadmap, ADRs, architecture, research, archive); root limited to GitHub-recognized files (README, LICENSE, CONTRIBUTING, CHANGELOG, SECURITY).
- **Architecture reference** under `docs/architecture/`: `overview.md`, `data-model.md`, `modules.md`, `wire-protocol.md`, `error-handling.md`. Extracted from PRD §4–§7 so architecture stays durable across version-specific PRDs.
- **Research consolidation**: `docs/research/{related-work,novelty}.md` replace eight long-form drafts + PDF renders.
- **ADR-0013** — CLI design and observability command split (flat structure + token group; five-command observability split: status/progress/logs/events/fetch; foreground-default for `serve`/`worker`).
- **ADR-0014** — Admin tokens for Job submission (extends [ADR-0002](./docs/adr/0002-closed-membership-rooms.md) with an `admin` capability bit on Invite Tokens; the Python submission API requires admin tokens).
- **Container Contract** extended with `env={...}` pass-through on Job specs — the W&B / MLflow / TensorBoard integration path.
- **ADR-0015** — Master URL passed separately from the Token (via `--master` or `C4M_MASTER`) so the Master can be moved without re-issuing tokens.
- **`docs/architecture/operations.md`** — running and maintaining a deployment: backup/restore, in-place upgrade, Master migration, cert rotation, pausing/decommissioning Workers, multi-Room operation, co-located Master+Worker, storage growth, emergency procedures.
- **`docs/architecture/deployment.md`** — practical deployment reference (volume mounts, GPU flags, Docker socket grant, multi-GPU hosts, where the CLI lives).
- **`docs/style-guide.md`** — Python + Markdown conventions (replaces earlier placeholder).
- **README.md** restructured by persona (Worker contributor / Master operator / Researcher) instead of a flat install section.
- **SECURITY.md** extended with Docker socket privilege note and admin-token elevated-trust caveat.
- Development workflow captured in `CONTRIBUTING.md`: feature branches `feat/T<NN>-<slug>`, squash merges, Conventional Commits, PR template with acceptance criteria checkboxes and verification + exploratory testing sections, polish issue triage.
- CI scaffolding: `.pre-commit-config.yaml` (ruff, mypy, mdformat, markdown link check), `scripts/check_md_links.py` (relative-link verification), `.github/PULL_REQUEST_TEMPLATE.md`, `.github/ISSUE_TEMPLATE/{polish,bug,config}.{md,yml}`.
- `SECURITY.md` (vulnerability reporting).
- `tests/INDEX.md` scaffold (T-task → test file map; populated as code lands).

### Changed
- **PRD rewritten:** per-task detail moved to plan and cards; non-functional requirements (NFR-01…11), updated risks, acceptance criteria mapped to tasks, and three new user stories (host check, task resources, event history).
- **All diagrams are Mermaid** (overview components, join / dispatch / failure sequences, Worker / Task / Job state machines, control-channel lifecycle); the style guide adds Diagrams and Logging sections.
- **Diagram set** filled out, each marked *As built* or *Planned* with its task: system context and Master-restart sequence (overview); deployment topology (deployment); package map with import rules, as-built class diagram, planned P2 interfaces, Scheduler decision flow, failure handling, Worker daemon connection states and Task execution on a Worker (modules); model map and SQLite ER diagram (data-model); Container Contract, message models, shard fetch and CLI command tree (wire-protocol). Index in [docs/architecture/README.md](docs/architecture/README.md#diagrams).
- **ADRs:** edited in place with a History line (replacing the append-only rule); 0001–0015 gained dates, Alternatives and History; content fixes in 0002 (token claims), 0006 (no base image), 0011 (consequences), 0013 (command count) and 0014 (neutral persona wording).
- **Docs brought in line with the code and with each other:** wire-protocol §5.1 (the URL is not in the token, ADR-0015) and its versioning rule (unknown types are dropped, not ignored); context.md field names and terms (Event, Dataset); deployment.md benchmark section; operations.md reconnect cap (30 s) and cert hostname note; the README's GPU claim and status; CONTRIBUTING (repository settings as they really are, task cards, Docker verification); the roadmap's missing deferred items.
- Python target version: 3.11 → **3.13**.
- PRD lifecycle: living `docs/prd.md` describes the current milestone; archived to `docs/archive/prd-vX.Y.md` on each version ship (Pattern B).
- Versioning: SemVer Pattern A (no pre-releases for v0.x); tag every minor; GitHub Releases authored only when there's an audience.

### Fixed
- **Worker no longer retries a cert fingerprint mismatch forever.** `WorkerDaemon.run` treated `CertPinError` as transient and reconnected with backoff indefinitely, though the token's pinned fingerprint never starts matching; it is now terminal like `join_reject` (T31 maps both to exit code 3).
- **Master logs dropped frames.** `ControlServer` silently discarded frames that weren't JSON or failed validation; it now logs a WARNING with the message type and the failing fields, never the frame itself or Pydantic's input-echoing error text (a `join` carries the token). Matches wire-protocol.md §Versioning and ADR-0018.
- Corrected docstrings: `proto/messages.py` contradicted itself on unknown types, and `JoinReject` / `JoinRejected` listed a fingerprint mismatch, which the Master can't detect (the Worker checks it before sending `join`). The CLI placeholders now name the task that implements each command (T31, T22, T24) instead of `prd.md §8`.

### Notes
- Greenfield repo. The pre-implementation period set up the design corpus (PRD, CONTEXT, ROADMAP, 14 ADRs, architecture docs, research framing) and the development workflow (CONTRIBUTING, PR/issue templates, CI gates).
- Code implementation begins with **T01 — Repo skeleton + packaging + image** (now [docs/plan.md](./docs/plan.md)).

---

<!-- Future-version sections are added top-down as releases are cut. Template:

## [vX.Y.Z] — YYYY-MM-DD

### Added
- New features.

### Changed
- Changes to existing functionality.

### Deprecated
- Soon-to-be-removed features.

### Removed
- Features removed in this release.

### Fixed
- Bug fixes.

### Security
- Vulnerability remediations.

-->
