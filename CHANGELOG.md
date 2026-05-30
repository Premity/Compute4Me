# Changelog

All notable changes to Compute4Me are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow [Semantic Versioning](https://semver.org/) with the project on `0.x.y` — *no API stability guarantees pre-1.0*.

For per-version Product Requirements (scope, acceptance criteria), see [docs/prd.md](./docs/prd.md) (current milestone) and [docs/archive/](./docs/archive/) (past milestones). For decisions, see [docs/adr/](./docs/adr/).

## [Unreleased]

### Added
- **T06 — Self-signed TLS + fingerprint (`master/server.py`, `worker/daemon.py`)**: the Master generates and persists a self-signed cert (`ensure_cert`, idempotent across restarts — no CA, no domain), exposing its sha256 DER fingerprint (`fingerprint_of`) for the [token service](./docs/architecture/modules.md) to embed in issued tokens. The Worker pins that fingerprint: `pinning_ssl_context` (chain verification off, self-signed) + `verify_fingerprint` compares the presented cert and raises `CertPinError` on mismatch. Verified end-to-end over a real TLS handshake (match connects, mismatch refused). Implements [ADR-0011](./docs/adr/0011-tls-fingerprint-in-token.md).
- **T05 — Token service (`master/tokens.py`)**: `TokenService` with `issue`/`verify`/`revoke`/`admit`/`release` per [modules.md §Token service](./docs/architecture/modules.md). JWT (HS256) sign/verify with an injected Master-held key and cert fingerprint (cert generation lands in T06); standard `exp`/`jti` registered claims; `verify` raises `InvalidToken` on bad signature, expiry, or revoked `jti`. In-memory revocation set (rebuilt from durable metadata on construction, so revocations survive restart) + per-`jti` live-Worker counter for the `max_workers` cap. Adds `save_token`/`set_token_revoked`/`load_revoked_jtis` to the state store (the `tokens` table T03 left model-less).
- **T04 — Wire message models (`proto/messages.py`)**: Pydantic models for every WebSocket control-channel message in [wire-protocol.md §2](./docs/architecture/wire-protocol.md) — Worker→Master (`join`/`heartbeat`/`task_progress`/`task_result`/`profile_update`) and Master→Worker (`join_ack`/`join_reject`/`task_assign`/`task_cancel`/`bandwidth_probe`). Two `type`-discriminated unions (`WorkerMessage`/`MasterMessage`) with `parse_worker_message`/`parse_master_message` helpers that reject an unknown `type` while tolerating unknown fields (additive evolution). `join` carries a full `CapabilityProfile`; `task_assign`/`task_result` reuse `ArtifactRef`/`TaskRequires` and the `TaskResult` outcome fields.
- **T03 — Master state store (`master/state.py`)**: `StateStore`, a SQLite-backed durable store applying the [data-model.md](./docs/architecture/data-model.md) §Master State Store schema on construction (idempotent — reopening an existing DB is a no-op). Upsert `save_room`/`save_worker`/`save_job`/`save_task`/`save_result` plus restart recovery via `load_open_jobs()` (queued/running Jobs) and `load_pending_tasks(job_id)` (non-terminal Tasks). Adds the durable-record models `Room`/`Worker`/`Job` to `types.py` and documents them in `data-model.md`.
- **T02 — Core types (`types.py`)**: Pydantic models per [data-model.md](./docs/architecture/data-model.md) — `CapabilityProfile`/`GpuInfo`, `TokenClaims`, `SearchJobSpec`/`MapJobSpec`/`ShardStrategy`, and the internal `Task`/`TaskRequires`/`ArtifactRef`/`ShardDescriptor`/`TaskError`/`TaskResult`. `ShardStrategy` enforces `n_shards > 0` for non-`whole` kinds. `data-model.md` gains the previously-named-only `ShardDescriptor`/`ArtifactRef`/`TaskError` definitions.
- **T01 — Repo skeleton + packaging + image**: `pyproject.toml` (uv, Python 3.13, ruff + mypy + pytest config), the `src/compute4me/` package per [docs/prd.md §5](./docs/prd.md#5-repo-layout-planned) with docstring-only module stubs, single `Dockerfile` (`serve`/`worker` entrypoints), `Makefile` (`dev`/`test`/`lint`/`types`/`image`/`e2e`), `docker-compose.dev.yml`, `.github/workflows/ci.yml` (`ci-test`/`ci-lint`/`ci-types`), and the `compute4me` CLI surface from [wire-protocol.md §4.1](./docs/architecture/wire-protocol.md).
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
- Python target version: 3.11 → **3.13**.
- PRD lifecycle: living `docs/prd.md` describes the current milestone; archived to `docs/archive/prd-vX.Y.md` on each version ship (Pattern B).
- Versioning: SemVer Pattern A (no pre-releases for v0.x); tag every minor; GitHub Releases authored only when there's an audience.

### Notes
- Greenfield repo. The pre-implementation period set up the design corpus (PRD, CONTEXT, ROADMAP, 14 ADRs, architecture docs, research framing) and the development workflow (CONTRIBUTING, PR/issue templates, CI gates).
- Code implementation begins with **T01 — Repo skeleton + packaging + image** ([docs/prd.md §8](./docs/prd.md#8-implementation-tasks-t01t27)).

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
