---
status: accepted
---

# TLS via Self-Signed Cert Fingerprint in the Invite Token

## Context

Workers must authenticate the Master they connect to (so a token can't be replayed against an impostor Master) and the channel must be encrypted. The usual options are a public CA / Let's Encrypt cert (needs a domain) or mutual TLS (needs cert distribution to every Worker).

## Decision

The Master holds a **self-signed certificate**; its fingerprint rides inside every **Invite Token**, and the Worker **pins** it on connect. No CA, no domain, no Let's Encrypt. Not mutual — the Worker is authenticated by the token itself.

## Why

1. **The token already establishes trust** ([ADR-0002](./0002-closed-membership-rooms.md)), so it can also carry the Master's cert fingerprint — making the Invite Token a *complete bootstrap credential*: it identifies the Room, authorizes the Worker, and authenticates the Master. TLS pinning falls out for free.
2. **No domain or CA required.** A Master on a bare VPS IP or a lab hostname works. Let's Encrypt would force a domain the Master may not have.
3. **mTLS is overkill.** The token already authenticates the Worker; issuing and distributing client certs would add onboarding friction for no security gain at this trust level.

## Revisit when

- A future open/public-Room mode (someday) admits Workers without out-of-band tokens — that needs a different trust bootstrap, since the token can no longer be assumed trustworthy.
