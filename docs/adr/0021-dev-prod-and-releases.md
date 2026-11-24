---
status: accepted
date: 2026-11-24
---

# Dev and Production Differ Only at Runtime; Releases Publish Versioned Images

## Context

There is one image ([ADR-0020](./0020-docker-is-the-verification-surface.md)) with two modes, `serve` and `worker`. The docs disagreed about which image to run. The Makefile builds `ghcr.io/premity/compute4me:dev` locally, while the README, deployment.md and operations.md tell people to pull `ghcr.io/premity/compute4me:latest`. **No workflow publishes any image**, so that pull fails today. The repo also has a `docker-compose.dev.yml` for running a Master and Workers on one machine, and operations.md shows a different compose file for real hosts. Nothing said how the two relate.

The question is whether development and production need different images (debug tools, an editable install, different defaults) or only different configuration.

## Decision

1. **One image, one Dockerfile, no dev or prod build target.** Development and production differ only in how the image is run.
2. **Development** uses `docker-compose.dev.yml` on one host:
   - the image is built from the checkout as `:dev`;
   - Workers run on CPU with `C4M_BENCHMARK=skip`;
   - logs are human-readable on a TTY;
   - the T31 make targets (`up`, `worker`, `logs`, `down`, …) wrap it.

   It is never used for a real Room.
3. **Production** runs a released image, `ghcr.io/premity/compute4me:<version>`. It is started with the `docker run` commands in [deployment.md](../architecture/deployment.md), or with operations.md's example compose for a Master host. Logs are JSON when stdout isn't a TTY ([ADR-0018](./0018-logging-and-events.md)).
4. **Tags:**
   - `:dev` is local only and never pushed.
   - `:<version>` (for example `:0.1.0`) is immutable and pushed by the release workflow.
   - `:latest` moves to the newest release.
   - The bench image follows the same scheme ([ADR-0016](./0016-benchmark-runs-as-a-container.md)).
   - Docs show `:<version>` in commands people copy; `:latest` is for trying the project out.
5. **Releases are automated** (T34): a pushed tag `vX.Y.Z` builds the image, runs the image smoke, pushes `:X.Y.Z` and `:latest` to GHCR, and (later) the bench image. The [release checklist](../../CONTRIBUTING.md#release-checklist) gates the tag.

## Why

1. **The image under test must be the image that ships.** A separate dev image would reintroduce the gap ADR-0020 closed: tests pass on one artefact while another one ships.
2. **What dev needs is configuration, not code:** skip the benchmark, run on CPU, read logs on a terminal, start and stop a stack quickly. Environment variables and compose already provide all of it.
3. **Versioned tags make bug reports and the paper reproducible.** A fleet run records exactly which image ran ([ADR-0019](./0019-experiment-run-records.md)); `:latest` alone can't say that.

## Alternatives considered

- **Dockerfile `dev` and `prod` targets** (dev: editable install, dev tools, debug logging). Rejected because it gives two artefacts to verify. Debugging can use the dev venv locally, or `docker run --entrypoint sh` on the same image.
- **No published images; users build from source.** Rejected: contributors lending a GPU should need nothing but `docker run`, which is the project's premise.
- **Push `:main` or `:edge` on every merge.** Not needed with one maintainer. It is easy to add later, as a second tag in the same workflow.

## Consequences

- Until T34 lands, nobody can pull the image. The README quick start already says it is pre-release; deployment.md says to build locally with `make image` and use `:dev` until the first release.
- The dev compose file and operations.md's production example are separate on purpose. Each links to the other and says which one it is.
- GHCR package visibility must be public for unauthenticated pulls (Unverified for organisation-owned packages; check when T34 runs).

## History

- 2026-11-24: Accepted (docs audit; user decision "runtime-only split plus a release task").
