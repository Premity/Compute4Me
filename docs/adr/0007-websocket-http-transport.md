---
status: accepted
date: 2026-05-20
---

# WebSocket + HTTP Transport, Not gRPC

## Context

The Master and Workers need a transport for the control channel (heartbeats, Task dispatch, cancellation, progress) and for bulk Artifact movement. In a datacenter the default choice would be gRPC — typed (protobuf), efficient, bidirectional streaming. But Compute4Me's Workers connect *outbound only* through arbitrary firewalls and proxies ([ADR-0003](./0003-master-on-data-plane.md)).

## Decision

A single persistent **outbound WebSocket** (Worker→Master) carries the control channel; the Master pushes Tasks/acks/cancellations down it. Bulk Artifact transfer uses separate **HTTP** GETs.

## Why

1. **WebSocket survives hostile networks.** It's an HTTP/1.1 upgrade and passes through corporate proxies and firewalls that frequently mangle gRPC's HTTP/2. Surviving firewalls is the entire premise — gRPC's typing/streaming benefits don't outweigh that risk.
2. **It matches the outbound-only constraint.** The Worker opens one connection out and keeps it alive; the Master uses it bidirectionally. No inbound ports on the Worker.
3. **HTTP for artifacts is the right tool.** Range-requestable (resumable), cacheable, trivially served — and decoupled from the control channel so a big download doesn't block heartbeats.

## Alternatives considered

- **gRPC:** typed and efficient, but HTTP/2 is frequently mangled by corporate proxies and firewalls; surviving them is the premise.
- **A binary encoding (CBOR/protobuf) on the control channel:** control traffic is KB/s per Worker, so JSON's debuggability wins ([wire-protocol.md §2](../architecture/wire-protocol.md#transport-choice-rationale)).

## Revisit when

- A deployment is known to run entirely on clean networks (e.g. a single managed datacenter) where gRPC's efficiency and codegen would be worth it. The firewall-survival premise is what rules it out by default.

## History

- 2026-05-20: Accepted.
- 2026-11-10: Format normalised (date, alternatives, history) in the planning rewrite; no change to the decision. Open detail owned by T11 (one port or two for WSS + HTTP); its answer is added here as a History line.
