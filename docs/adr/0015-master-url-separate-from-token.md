---
status: accepted
---

# Master URL Passed Separately From Token

## Context

A **Worker** needs two things to join: a way to reach the **Master** (URL) and credentials to prove it should be admitted (Invite Token). The Token already carries `room`, `max_workers`, `expires_at`, `master_cert_fp`, and `admin` ([data-model.md §5.4](../architecture/data-model.md)). The question we never explicitly settled: does it also carry the Master's URL, or is the URL passed separately?

Earlier drafts of the deployment docs showed `compute4me worker --token <T>` with no URL flag. That implicitly meant the URL must come from somewhere — either the Token, environment, or a flag — but didn't pin which. This ADR settles it.

## Decision

The **Master URL is passed separately from the Token**, via either:

- `--master URL` flag, or
- `C4M_MASTER` environment variable.

The Token contains credentials and the cert fingerprint, but not the URL. Operators distribute URL + Token together out-of-band (a single shareable string like `wss://vps:8443|eyJ...` is fine), but they're independent values to the Worker daemon.

Concretely:

```bash
# Worker startup:
docker run -d --gpus all \
  -e C4M_MASTER=wss://vps.example:8443 \
  -e C4M_TOKEN=eyJ... \
  -v c4m-cache:/var/cache/c4m \
  -v /var/run/docker.sock:/var/run/docker.sock \
  ghcr.io/premity/compute4me:latest worker

# Or with flags instead of env:
docker run -d --gpus all \
  ghcr.io/premity/compute4me:latest worker --master wss://vps.example:8443 --token eyJ...
```

The Worker validates the cert it sees against the `master_cert_fp` carried in the Token; URL ↔ cert correspondence is enforced at TLS handshake time.

## Why

1. **Master migration becomes possible without re-issuing tokens.** If the operator moves the Master to a new host (keeping the same `master.db` and self-signed cert via volume copy), Workers reconnect by being given the new URL — Tokens stay valid because the cert (and therefore its fingerprint) hasn't changed. If the URL were embedded in the Token, every move would require re-issuing every active Token to every contributor. That's a real operational friction point we'd hit the first time a VPS got replaced.

2. **URL is deployment topology, not credential.** A URL is "where this Master currently lives." A Token is "who's allowed to join." Conflating them couples credentials to topology, which is the wrong direction.

3. **One extra arg (or env var) is acceptable UX cost.** The "one `docker run`" promise still holds — it's now `docker run ... -e C4M_MASTER=X -e C4M_TOKEN=Y ...` instead of `... -e C4M_TOKEN=Y...`. Operators distributing a token to a contributor send both values; a single combined string like `wss://vps:8443?token=eyJ...` could be parsed as sugar later if friction is felt.

4. **Symmetric with client commands.** Client invocations (`compute4me status`, `compute4me fetch`, etc.) already use `C4M_MASTER` + `C4M_TOKEN` separately ([wire-protocol.md §4.8](../architecture/wire-protocol.md)). Worker uses the same pattern — one mental model.

## Alternatives considered

- **URL in Token (embedded as a `master_url` claim).** Most "one-arg UX" friendly. Rejected because Master migration becomes traumatic (every Token invalidated on every move), and it ties an issued credential to a specific deployment that the operator might want to change.

- **URL discovered automatically (mDNS / multicast / DHT).** Works on a LAN, breaks across the internet. Adds discovery complexity for the v0.1 single-Master-per-Room model. Revisit if/when multi-Master or federated deployments arrive.

- **Single combined credential string (`wss://vps:8443?token=eyJ...`).** Nice UX. Parseable. But it conflates URL and Token under one variable, which loses the override-URL-without-reissuing-Token property. Could be added as *sugar* on top of the two-value design later (e.g., `--connect URL_WITH_TOKEN` flag that splits internally), without changing the underlying split.

## Consequences

- Worker examples in [deployment.md](../architecture/deployment.md), [README.md](../../README.md), and Quick Start sections show `--master` / `C4M_MASTER` explicitly.
- The Master migration runbook in [operations.md](../architecture/operations.md) relies on this — tokens portable across Master moves.
- `TokenClaims` ([data-model.md §5.4](../architecture/data-model.md)) does NOT have a `master_url` field. Comment in the schema notes the absence and points here.
- Tokens are URL-agnostic but cert-specific: a Worker validates whatever Master URL it's told to contact against the cert fingerprint in the Token. URL spoofing fails at TLS.
- A combined `wss://...|TOKEN` distribution format is fine as operator convention; the daemon takes two values.

## Revisit when

- A multi-Master / failover topology becomes real (then URL discovery or a coordination layer becomes worth the complexity).
- Operators consistently complain about the two-arg UX (unlikely — almost everyone uses env vars or the optional alias).
