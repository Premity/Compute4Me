---
status: accepted
---

# Closed-Membership Rooms via Invite Tokens

## Context

Compute4Me pools compute from machines the operator does not fully administer (a lab, plus friends' and collaborators' GPUs). This raises a trust question: who can join a **Room**, and how do we defend against bad behaviour (poisoned gradients, fabricated results, free-riding)? The literature offers a spectrum from fully-trusted clusters (Ray) through open volunteer pools needing Byzantine-robust aggregation (Hivemind, "Secure Distributed Training at Scale") to fully-adversarial settings needing cryptographic guarantees.

## Decision

Compute4Me uses **closed-membership Rooms gated by signed Invite Tokens**. The Master issues JWT-style tokens carrying `room`, `max_workers` (concurrent-worker cap, nullable for unlimited), and `expires_at` (default 30 days). A Worker presents a token to join; the Master verifies the signature offline and tracks live worker counts per token. Trust is established **out of band** — you only issue tokens to people you trust. Byzantine-robust aggregation and open/public Rooms are explicitly out of scope.

## Why

1. **It matches the actual use case.** The operator knows every contributor personally. The social layer (you DM the token, you revoke it, you can ask Ali why his card is misbehaving) does the work that cryptographic Byzantine defenses would otherwise have to.
2. **It's cheap and standard.** Token-gated joining is the same primitive as Kubernetes join tokens, Tailscale auth keys, or a Discord invite — TLS + a signed token, ~30 lines with a JWT library. No cryptography research.
3. **It scopes out an entire research subfield.** With closed membership, "bad" Workers are almost always *buggy*, not malicious. Bug-level defenses (finite-metric checks and output-schema checks from v0.1; gradient-norm sanity once gradients exist in v0.4) suffice. We do not need median-of-means, Krum, or trimmed-mean aggregation.
4. **Per-token policy gives fine-grained control.** One token for the whole lab (`max_workers=4`), a separate single-use token for a guest, short-TTL tokens for one-off sessions — revocable independently.

## Consequences

- Future readers steeped in volunteer-DL security will ask "where is the Byzantine-robust aggregation?" The answer is here: trust is out-of-band, so it isn't needed at this scope.
- An open/public Room mode (anyone joins, statistical defenses required) would be a *separate mode* layered on later, not a change to this one. The token-gated path remains the default.

## Revisit when

- Compute4Me needs to admit genuinely untrusted participants (a public volunteer pool).
- Contributors are numerous enough that out-of-band trust establishment stops scaling.
