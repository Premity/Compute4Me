# Security Policy

## Supported Versions

Compute4Me is pre-1.0 (`0.x.y`). There are no formal stability or long-term-support guarantees. Security fixes ship as part of regular minor or patch releases on whatever the current development branch is.

| Version | Supported |
|---|---|
| `0.x` (current dev) | ✅ via the next minor release |
| anything older | ❌ |

## Reporting a Vulnerability

Please **do not open a public issue** for security problems.

Instead, email **hamd.ashfaque@gmail.com** with:

- A description of the issue and its impact.
- Reproduction steps (commands, code, config — whatever lets the issue be confirmed).
- The version / commit SHA you observed it on.
- (Optional) a suggested fix.

You can expect:

- An acknowledgment within ~7 days.
- A best-effort response on triage / mitigation timeline.
- Credit in the relevant release notes once a fix ships (unless you prefer anonymity).

## Scope

Treat the following as in-scope:

- The Compute4Me Master (`compute4me serve`) and its HTTP / WebSocket endpoints.
- The Worker daemon (`compute4me worker`) — particularly token handling, cert pinning, and container-runner isolation.
- The Python client library (`compute4me`).
- The Container Contract (env vars, mount points) as a trust boundary between the runner and user images.

Out of scope (handled by upstream projects):

- Vulnerabilities in Python itself, in Docker / Docker Engine, in PyTorch / Optuna / Pydantic / FastAPI, etc. — please report those to the respective projects.
- User model containers — these are user-supplied code; their security is the user's responsibility. Compute4Me's contract treats them as untrusted in terms of side effects (we don't audit them) but as trusted in terms of returned data (no Byzantine-robust validation in v0.1 — see [ADR-0002](./docs/adr/0002-closed-membership-rooms.md)).

## Threat model (high level)

v0.1 is **closed-membership** — Workers join only with an Invite Token issued out-of-band. The threat model is:

- **Stolen / leaked token:** mitigated by per-token `max_workers` cap, 30-day default TTL, in-memory revocation. Operator can revoke any time.
- **Impostor Master:** mitigated by TLS cert fingerprint pinning embedded in the token ([ADR-0011](./docs/adr/0011-tls-fingerprint-in-token.md)).
- **Network MITM:** mitigated by WSS (TLS) on all control + artifact channels.
- **Buggy Worker returning garbage:** mitigated by result validation (finite metric / output schema). **Not** mitigated for adversarial behavior — Byzantine-robust aggregation is out of scope for v0.1.
- **Leaked admin token:** an admin token authorizes Job submission ([ADR-0014](./docs/adr/0014-admin-tokens-for-submission.md)) — submission means running an arbitrary user image on Workers in the Room. A leaked admin token can therefore execute arbitrary code on every Worker host. Treat admin tokens with elevated care: short TTL, revoke promptly if a researcher's machine is compromised. Worker-only tokens (the default issuance) cannot submit.

Out-of-band trust (you only invite people you'd let SSH into your machines) is load-bearing. Open / public Rooms with Byzantine defenses are a separate research thread, not on the v0.x roadmap.

## Worker host privilege model

The Worker container needs `-v /var/run/docker.sock:/var/run/docker.sock` to run user model images per the [Container Contract](./docs/architecture/wire-protocol.md). Mounting the Docker socket gives the Worker container **root-equivalent access to the host**.

This is standard practice for runner-style workloads (every CI runner — GitHub Actions, GitLab, Jenkins agents — does the same). The trust model assumes:

- You only run the official `ghcr.io/premity/compute4me` image (or an audited fork).
- The Master you joined is operated by someone you trust (see [ADR-0002](./docs/adr/0002-closed-membership-rooms.md)).
- The user model images that the Master assigns are trusted by transitivity — only admin-token holders can submit them.

**Practical implications for the Worker host:**

- The Worker can `docker run` arbitrary images on your host. Anything the user submits runs on your hardware with whatever Docker would allow it.
- The Worker can mount any host path into a user container (if a malicious admin token is in play, this is the vector).
- A compromised user image can escape its container (because it has full Docker access via the socket).

If any of those assumptions fail (untrusted Master, untrusted admin tokens, public/open Rooms), **the socket mount is a vulnerability** and Compute4Me should not be run with this configuration. Alternatives — sysbox, gVisor, rootless Docker, Docker-in-Docker — are out of scope for v0.1; the closed-membership model is what makes the socket mount acceptable. Stricter sandboxing would be needed before considering open/public Rooms.
