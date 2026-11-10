# T10: Bandwidth/RTT probe + periodic profile refresh

| | |
|---|---|
| Phase | P1 (closes it) |
| Size | M (3–5 h) |
| Depends on | T31 (also T07, T09) |
| Unblocks | T24 (`status` shows bandwidth), T15 (transfer-time term, optional), P1 tracer bullet |
| Branch | `feat/T10-bandwidth-probe` |
| Issue | — |
| Status | Not started |

## Why this task exists

`bandwidth_to_master_mbps` and `rtt_to_master_ms` are `0.0` for every Worker today (T09 left them to the Master). PRD user story 14 wants them so the Scheduler avoids sending big datasets over slow links, and story 15 wants profiles refreshed so free VRAM stays current. This task closes P1: after it, the compose smoke shows a joined Worker with a **complete** profile.

## Background you need

- **What exists:** `proto/messages.py` has `BandwidthProbe` (**no fields**) Master→Worker, `ProfileUpdate{worker_id, profile}` Worker→Master and `Heartbeat`. `ControlServer.push(conn_id, message)` sends to one Worker. Nothing sends or handles a probe or a profile update yet.
- **RTT:** the `websockets` library has protocol-level ping/pong: `pong_waiter = await ws.ping(); latency = await pong_waiter` returns the round-trip in seconds (websockets ≥ 12 returns the latency). It needs no new message type and measures the real path, including TLS.
- **Bandwidth direction:** what matters for scheduling is **Master → Worker** (Artifact pulls, ADR-0012). Measure it as: the Master sends a probe carrying N random bytes; the Worker replies at once with a small ack; the Master computes `N·8 / (t_ack − t_send − rtt)`. Small N underestimates (TCP slow start); large N costs the Master's uplink for every Worker on every join.
- **Wire evolution rule** (wire-protocol "Versioning"): additive only. Giving `BandwidthProbe` fields and adding a new Worker→Master `probe_ack` type is allowed; parsers already reject unknown *types*, so the Worker must ship the new type in the same release.
- **When to probe:** once right after `join_ack`, then on every profile refresh (~10 min, [wire-protocol.md §4.12](../architecture/wire-protocol.md#412-whats-not-user-configurable-in-v01) fixes it). Never while the Worker is running a Task: the probe would compete with its Artifact download.

## Decide first

1. **Probe over WebSocket or HTTP?** HTTP is where artifacts flow, but the HTTP app arrives in T11. Recommendation: **WebSocket now** (binary frame payload), revisit after T11 only if numbers disagree with real artifact pulls; record that in T11's card.
2. **Probe size.** Recommendation: 4 MiB, with a constant in `master/` and a test override. At 50 Mbps that is ~0.7 s per Worker; at 10 Workers joining together it is 40 MiB of Master uplink, acceptable at v0.1's scale.
3. **Where the numbers live.** Recommendation: the Master writes them into the stored `CapabilityProfile` (`workers.profile_json`). The Worker never knows its own bandwidth figure, and `profile_update` from the Worker must not overwrite the Master's measured fields with zeros (merge on the Master).

## Steps

1. Messages: `BandwidthProbe{probe_id: str, size_bytes: int}` (payload sent as the next binary frame) and a new Worker→Master `ProbeAck{probe_id, received_bytes}`. Update wire-protocol §2 tables and the lifecycle diagram.
2. Master: after `join_ack`, schedule `probe(worker)`: RTT via `ws.ping()` (median of 3), then bandwidth; update the stored profile; emit `profile_updated` (T29).
3. Worker: answer the probe immediately; every 600 s (constant, test-overridable) rebuild the profile **without** re-running the benchmark (reuse the join-time `throughput_ref`) and send `profile_update`.
4. Master: on `profile_update`, merge (keep measured bandwidth/RTT), persist, emit `profile_updated`, then re-probe.
5. Skip the probe for a Worker that is `busy`; probe it when it next goes idle.

## Outputs

`proto/messages.py`, `master/server.py`, `worker/daemon.py`, wire-protocol.md §2, modules.md, data-model.md (which fields the Master owns), tests/INDEX.md, CHANGELOG.

## Tests

| File | Markers | Proves |
|---|---|---|
| `tests/unit/test_messages.py` (extend) | `task("T10")`, `unit` | new fields and `ProbeAck` round-trip |
| `tests/integration/test_probe.py` | `task("T10")`, `integration` | after join, the stored profile has `rtt_to_master_ms > 0` and `bandwidth_to_master_mbps > 0` (localhost) |
| same | `task("T10")`, `integration` | with a 0.2 s refresh interval, a changed fake `vram_free_mb` reaches the Master's stored profile; measured bandwidth is not overwritten |

## Verify in Docker

`make smoke`, then read the Worker row: `docker compose exec master python -c "…select profile_json from workers…"` shows non-zero bandwidth and RTT. Over a real link (lab ↔ VPS) the numbers go on the "Needs the real fleet" issue.

## Done when

- [ ] A joined Worker's stored profile has non-zero `bandwidth_to_master_mbps` and `rtt_to_master_ms`.
- [ ] A refresh after freeing VRAM updates `vram_free_mb` in the Master's view.
- [ ] Busy Workers aren't probed.
- [ ] Wire-protocol docs include the new message and fields.

## If this fails

- **Bandwidth figures swing wildly between probes:** report the median of the last 3 probes, not the latest.
- **Ping latency unavailable in the installed `websockets` version:** time a `ProbeAck` round-trip with an empty payload instead.

## References

- [wire-protocol.md §2](../architecture/wire-protocol.md#2-control-channel-worker--master-websocket), PRD user stories 14–15
- websockets keepalive and latency: https://websockets.readthedocs.io/en/stable/topics/keepalive.html

## History

- 2026-11-10: Card written (planning rewrite).
