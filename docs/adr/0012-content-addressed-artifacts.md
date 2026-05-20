---
status: accepted
---

# Content-Addressed Artifacts, Master as Origin

## Context

Datasets, model checkpoints, and Task outputs must move between Master and Workers. Two questions: how are these blobs identified (by path/name, or by content hash?), and where does the canonical copy live?

## Decision

An **Artifact** is a **content-addressed blob** (bytes + SHA-256 + metadata); a human name+version (`kepler-q1-q17/v3`) is a friendly alias that resolves to a hash. The **Master is the origin / source of truth**; **Workers pull Artifacts over HTTP and cache them content-addressed locally**, advertising what they hold via `datasets.cached` in their Capability Profile.

## Why

1. **Content addressing earns its keep.** It enables Worker-side cache hits ("do I already have hash `abc123`?"), automatic dedup, integrity verification after download, and immutability (the hash *is* the version — no "v3 changed under me" surprises).
2. **It powers data-locality scheduling.** `datasets.cached` lets the smart-pull scheduler ([ADR-0008](./0008-smart-pull-scheduling.md)) prefer placing Tasks on Workers that already hold the inputs — critical the moment any Worker is on a slow WAN link.
3. **Master-as-origin follows from the network model.** With outbound-only Workers and the Master on the data plane ([ADR-0003](./0003-master-on-data-plane.md)), routing Artifact bytes through the Master is consistent and keeps the firewall story simple.

## Revisit when

- v0.3 adds streaming partial transfer and external result sinks (Workers write directly to S3 / user fs), relieving the Master of being the sole result conduit.
- v0.5 adds P2P artifact distribution between Workers for large WAN fleets where the Master's uplink saturates.
