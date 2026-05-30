# Architecture Decision Records

Each file in this folder records a single architectural decision: the context, the decision, the alternatives considered, and the consequences.

## What is an ADR?

An **Architecture Decision Record** is a short markdown document capturing one decision that's:

1. **Hard to reverse** — the cost of changing your mind later is meaningful.
2. **Surprising without context** — a future reader (including future-you) would look at the code and wonder "why on earth was this done this way?"
3. **The result of a real trade-off** — there were genuine alternatives and one was picked for specific reasons.

If any of those three is missing, the decision doesn't need an ADR.

## How they're used

- **When making a decision** that meets the three criteria above, write an ADR *before* (or alongside) the code that implements it.
- **When reading an unfamiliar part of the system**, check the ADRs for the rationale before assuming the implementation is wrong or could be "improved."
- **When proposing to change** something an ADR governs, the new ADR cites and supersedes the old one (status: `superseded by ADR-NNNN`).

## Conventions

- **Naming:** `NNNN-kebab-case-title.md`, four-digit zero-padded sequence.
- **Format:** one H1 title, then short Context / Decision / Why / Consequences (when non-obvious) sections. Most ADRs are 30–80 lines. See existing files for the pattern.
- **Status:** frontmatter `status: accepted | proposed | superseded by ADR-NNNN`. ADRs are append-only — never edit an accepted decision; supersede it.
- **Cross-references:** link to other ADRs with `[ADR-NNNN](./NNNN-slug.md)`-style relative paths (sibling-relative).

## Current ADRs

| # | Title | Status |
|---|---|---|
| [0001](./0001-flat-master-not-hierarchical.md) | Flat Master, not Hierarchical Aggregation | accepted |
| [0002](./0002-closed-membership-rooms.md) | Closed-membership Rooms via signed Invite Tokens | accepted (amended by 0014) |
| [0003](./0003-master-on-data-plane.md) | Master on the data plane; Workers connect outbound only | accepted |
| [0004](./0004-big-models-out-of-scope.md) | Models that don't fit one GPU are out of scope for v0.1–v0.5 | accepted |
| [0005](./0005-roll-our-own-orchestration.md) | Roll our own orchestration, not Ray | accepted |
| [0006](./0006-black-box-container-contract.md) | Black-box Container Contract (env-vars-in / files-out) | accepted |
| [0007](./0007-websocket-http-transport.md) | WebSocket control channel + HTTP artifacts (not gRPC) | accepted |
| [0008](./0008-smart-pull-scheduling.md) | Smart-pull scheduling | accepted |
| [0009](./0009-map-search-primitives.md) | Two primitives — Map and Search — not a job-type enum | accepted |
| [0010](./0010-wrap-optuna.md) | Wrap Optuna behind a pluggable Sampler interface | accepted |
| [0011](./0011-tls-fingerprint-in-token.md) | TLS via self-signed cert fingerprint pinned in the Invite Token | accepted |
| [0012](./0012-content-addressed-artifacts.md) | Content-addressed Artifacts with the Master as origin | accepted |
| [0013](./0013-cli-design-and-observability.md) | CLI design and observability command split | accepted |
| [0014](./0014-admin-tokens-for-submission.md) | Admin tokens for Job submission (amends ADR-0002) | accepted |
| [0015](./0015-master-url-separate-from-token.md) | Master URL passed separately from token | accepted |

When proposing a new ADR, take the next sequence number from this list.
