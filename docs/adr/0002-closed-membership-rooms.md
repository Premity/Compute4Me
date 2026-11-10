---
status: accepted (amended by ADR-0014)
date: 2026-05-20
---

# Closed-Membership Rooms via Invite Tokens

> **Amendment ([ADR-0014](./0014-admin-tokens-for-submission.md)):** the Token machinery is extended with an `admin: bool` capability bit. Worker-only tokens (default) authorize Room joining; admin tokens additionally authorize Job submission via the Python API. Same trust model; one more capability.

## Context

Compute4Me pools compute from machines the operator does not fully administer (a lab, plus friends' and collaborators' GPUs). This raises a trust question: who can join a **Room**, and how do we defend against bad behaviour (poisoned gradients, fabricated results, free-riding)? The literature offers a spectrum from fully-trusted clusters (Ray) through open volunteer pools needing Byzantine-robust aggregation (Hivemind, "Secure Distributed Training at Scale") to fully-adversarial settings needing cryptographic guarantees.

## Decision

Compute4Me uses **closed-membership Rooms gated by signed Invite Tokens**. The Master issues signed JWTs whose claims are listed in [data-model.md](../architecture/data-model.md#invite-token-claims-signed): `jti` (the revocation key), `room`, `max_workers` (concurrent-worker cap, nullable for unlimited), `expires_at` (default 30 days), `master_cert_fp` ([ADR-0011](./0011-tls-fingerprint-in-token.md)) and `admin` ([ADR-0014](./0014-admin-tokens-for-submission.md)). A Worker presents a token to join; the Master verifies the signature offline and tracks live worker counts per token. Trust is established **out of band** — you only issue tokens to people you trust. Byzantine-robust aggregation and open/public Rooms are explicitly out of scope.

## Why

1. **It matches the actual use case.** The operator knows every contributor personally. The social layer (you DM the token, you revoke it, you can ask Ali why his card is misbehaving) does the work that cryptographic Byzantine defenses would otherwise have to.
2. **It's cheap and standard.** Token-gated joining is the same primitive as Kubernetes join tokens, Tailscale auth keys, or a Discord invite — TLS + a signed token, ~30 lines with a JWT library. No cryptography research.
3. **It scopes out an entire research subfield.** With closed membership, "bad" Workers are almost always *buggy*, not malicious. Bug-level defenses (finite-metric checks and output-schema checks from v0.1; gradient-norm sanity once gradients exist in v0.4) suffice. We do not need median-of-means, Krum, or trimmed-mean aggregation.
4. **Per-token policy gives fine-grained control.** One token for the whole lab (`max_workers=4`), a separate single-use token for a guest, short-TTL tokens for one-off sessions — revocable independently.

## Consequences

- Future readers steeped in volunteer-DL security will ask "where is the Byzantine-robust aggregation?" The answer is here: trust is out-of-band, so it isn't needed at this scope.
- An open/public Room mode (anyone joins, statistical defenses required) would be a *separate mode* layered on later, not a change to this one. The token-gated path remains the default.

## Alternatives considered

- **Admin-provisioned, fully trusted membership** (the Ray model): contradicts the premise that the operator does not administer contributors' machines.
- **Open/public Rooms with Byzantine-robust aggregation** (Krum, median-of-means, trimmed mean): needed only for untrusted participants; a research subfield of its own.
- **Cryptographic guarantees** (secure aggregation, differential privacy): out of scope for a closed-membership tool.

## Revisit when

- Compute4Me needs to admit genuinely untrusted participants (a public volunteer pool).
- Contributors are numerous enough that out-of-band trust establishment stops scaling.

## History

- 2026-05-20: Accepted.
- 2026-05-30: Amended by ADR-0014 (the `admin` capability bit), edited in place.
- 2026-11-10: Format normalised (date, alternatives, history) in the planning rewrite. The token claim list now matches data-model.md and the code (`jti`, `master_cert_fp`, `admin` were missing). No change to the decision.
