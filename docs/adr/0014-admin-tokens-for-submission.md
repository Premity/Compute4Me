---
status: accepted
---

# Admin Tokens for Job Submission

Amends [ADR-0002](./0002-closed-membership-rooms.md) — closed-membership Rooms via signed Invite Tokens.

## Context

The Python submission API ([wire-protocol.md §5](../architecture/wire-protocol.md)) lets a researcher submit, cancel, and list Jobs against a remote Master. The Master must therefore authenticate the submitter — but the Invite Token system designed in [ADR-0002](./0002-closed-membership-rooms.md) authorizes *Worker join*, not *Job submission*. Worker-only tokens shouldn't be able to submit Jobs (a Worker container on Ali's laptop shouldn't be able to enqueue work against the Room). So submission needs an auth check distinct from the Worker join check.

Three options for how:

1. **Reuse the Token machinery with an `admin: bool` capability bit.** One token system, two capabilities.
2. **Separate auth scheme for submission** — Master holds a long-lived API key in `master.db`; submitters pass it as `Client(api_key=...)`.
3. **Local-only submission** — Python API only works when the submitter runs on the Master host (Unix socket or `127.0.0.1`-bind).

## Decision

**Option 1: extend the existing Token machinery with an `admin: bool` claim.**

Concretely:

- Add `admin: bool = False` to `TokenClaims` ([data-model.md §5.4](../architecture/data-model.md)).
- Add `--admin` flag to `compute4me token issue` — sets the claim to `True`.
- Master-side authorization: the Python submission API endpoints (`submit_search`, `submit_map`, `cancel`, `list_jobs`) require a token where `admin=True`. Worker-only tokens (the default) cannot submit. The Worker-join endpoint accepts both kinds (admin tokens may also act as Workers).
- CLI listing distinguishes: `compute4me token list` shows the admin bit in its output.

## Why

1. **One auth system, two capabilities.** Reusing the Token machinery keeps the trust model coherent: every credential is a signed JWT-style token, every revocation goes through the same `revoke --jti` flow, every audit trail is one query. A separate API-key scheme would double the surface area of "what auth do I have right now?" without adding meaningful security.

2. **The trust model already permits it.** [ADR-0002](./0002-closed-membership-rooms.md) assumes out-of-band-established trust: the operator chooses who to invite. An admin token is just a more privileged invite — same trust model, more scope. The operator is the same person who decides who joins as a Worker; they're not a different principal.

3. **In v0.1 the researcher and operator are usually the same person.** Hamda runs `serve` and submits her own `spacesight` Jobs. Adding a parallel API-key scheme for this case is bureaucracy without payoff. When operators and researchers diverge (later milestones, or shared deployments), an admin token is still the right primitive — the operator just issues admin tokens to specific researchers.

4. **Single point of trust = single point of revocation.** Compromise an admin token → revoke its `jti`. Same flow as a Worker token. No "where do I find the API key list?" surprise.

## Alternatives considered

- **Separate API-key scheme (option 2).** Slightly more secure in theory — the submission key never crosses to Workers, so a compromised Worker host can't elevate to submission privileges. But: in v0.1 the operator *is* the submitter, so the key already lives on the operator's machine; the threat model doesn't apply. Adds a second auth subsystem to maintain, document, and migrate later.

- **Local-only submission (option 3).** Cleanest in a "Master == workstation" deployment, since no remote-auth question arises. Rejected because the PRD explicitly targets remote submission (researcher's laptop → VPS Master). Forcing the operator onto the Master host every time defeats one of the project's premises.

- **OAuth / OIDC.** Vastly over-engineered for a closed-membership solo / small-team tool. Revisit if/when Compute4Me ever supports federated organizations.

## Consequences

- `TokenClaims` gains one boolean field. Validation, serialization, and migration are trivial.
- `compute4me token issue` gains `--admin` flag. Default remains worker-only — the safer default; explicit opt-in for the privileged form.
- `compute4me token list` shows an `ADMIN` column to make capability visible at a glance.
- New error in [error-handling.md](../architecture/error-handling.md): `AuthError` raised with message `error: token jti=... is not authorized to submit Jobs / hint: ask for an admin token with --admin`.
- Worker join logic unchanged — admin tokens can also act as Workers (the bit is additive, not exclusive).
- A revoked admin token immediately stops accepting submissions and disconnects any active Worker using it — same as any other revocation.

## Revisit when

- A real deployment has untrusted submitters (e.g., a shared Master serving multiple labs). Then we'd want fine-grained per-Job quotas or per-token Room scoping for submission — that's a v1.0+ conversation.
- An incident shows that an admin token leaking is materially worse than a Worker token leaking (it is — admin can submit a malicious image). Worth documenting the elevated trust expectations in operator docs at that point; for v0.1 the closed-membership assumption holds.
