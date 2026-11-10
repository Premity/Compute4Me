# T11: Artifact store, Master origin

| | |
|---|---|
| Phase | P2 |
| Size | L (5–8 h) |
| Depends on | T03, T31 |
| Unblocks | T12, T17, T22 (remote commands need an HTTP API) |
| Branch | `feat/T11-artifact-store` |
| Issue | — |
| Status | Not started |

## Why this task exists

Every Job needs bytes to move: datasets and checkpoints to Workers, results back. [ADR-0012](../adr/0012-content-addressed-artifacts.md) makes the Master the origin and identifies blobs by SHA-256. This task builds the store and the HTTP channel ([wire-protocol.md §3](../architecture/wire-protocol.md#3-artifact-channel-worker--master-http)). It is also the first HTTP surface on the Master, so it settles how HTTP and the existing WSS control channel share the network.

## Background you need

- **What exists:** the `artifacts` table (hash, name, version, kind, size_bytes, origin, created_at) and index `(name, version)` in [data-model.md](../architecture/data-model.md); no store code. `ControlServer` serves WSS with the `websockets` library on one port (8443, the only port the Dockerfile `EXPOSE`s). `starlette`, `uvicorn` and `httpx` are already dependencies.
- **The `websockets` server can't host HTTP routes** beyond a minimal `process_request` hook, so it can't do multipart uploads or streamed `Range` responses. Starlette *can* host WebSocket endpoints, so one ASGI app under uvicorn (with `ssl_keyfile`/`ssl_certfile` = the Master cert) can serve both on one port.
- **Never hold a dataset in memory.** `put(bytes)` in modules.md is the interface shape; the implementation must stream: hash while writing to a temp file in the same directory, `fsync`, then `os.replace` into `artifacts/sha256/<ab>/<full-hash>`. The same bytes give the same path, so re-uploads are no-ops.
- **`Range`:** Starlette's `FileResponse` handles `Range` requests in recent versions (**Unverified** for the version in `uv.lock`; check before relying on it, otherwise implement 206 responses with a small helper).
- **Auth:** every HTTP request carries `Authorization: Bearer <token>`, checked by `TokenService.verify`. GET needs any valid token for the Room; `POST /artifacts` needs an **admin** token ([ADR-0014](../adr/0014-admin-tokens-for-submission.md)); `POST /tasks/{id}/outputs` is for the assigned Worker (T17 enforces this).
- **URL ingest** (`POST /artifacts {url}`): stream with `httpx`, hashing as you go; cap the size (config constant) and time out.

## Decide first

1. **One port or two?** (plan.md Open items.)
   - **A. One port (Recommendation):** move the control channel onto a Starlette WebSocket route in one uvicorn app on 8443. The firewall story stays "one outbound port", and the docs keep `-p 8443:8443`. Cost: port `ControlServer`'s connection handling from `websockets.ServerConnection` to Starlette's `WebSocket`; the T07/T08 integration tests must keep passing, which proves it. The Worker client (`websockets.connect`) is unchanged.
   - **B. Two ports (8443 WSS, 8444 HTTPS):** no rewrite now, but a second inbound port on every Master, a second firewall rule, and every `docker run -p` in the docs changes.
   Record the choice in ADR-0007's History.
2. **Upload body.** Recommendation: raw streamed body (`Content-Type: application/octet-stream`) plus `?name=&version=&kind=` query parameters, not multipart (simpler to stream and hash). JSON `{url}` for URL ingest.

## Steps

1. If Decide 1 is A: create `master/app.py` (Starlette app; routes below plus `/ws` for the control channel) and refactor `ControlServer` to accept connections from it. Keep the public behaviour and tests.
2. `master/artifacts.py`: `ArtifactStore(root, store)` with `put_stream(chunks) -> str`, `put_url(url) -> str`, `path(hash) -> Path`, `exists(hash)`, `resolve(name_or_hash) -> hash`, `set_alias(hash, name, version)`.
3. Routes: `GET /artifacts/{hash}` (`Range`), `HEAD /artifacts/{hash}`, `POST /artifacts`, `GET /artifacts/resolve?name=&version=`. (`/shard` is T12; `/tasks/{id}/outputs` is T17.)
4. A shared auth dependency (bearer token → claims, admin check).
5. Events: none required. INFO log per ingest (hash, size, origin).
6. Docs: wire-protocol §3 (auth, the upload format, the port decision), modules.md, deployment.md (if ports change), ADR-0007 History.

## Outputs

`master/app.py` (if A), `master/artifacts.py`, `master/server.py`, docs above, CHANGELOG.

## Tests

| File | Markers | Proves |
|---|---|---|
| `tests/unit/test_artifacts.py` | `task("T11")`, `unit` | same bytes → same hash and one file; streamed put of a 50 MB generated stream uses bounded memory; alias resolves; an interrupted put leaves no partial file |
| `tests/integration/test_artifact_http.py` | `task("T11")`, `integration` | upload then GET returns identical bytes; `Range: bytes=10-19` returns 206 and those bytes; non-admin upload → 403; no token → 401; URL ingest from a local test server hashes correctly |
| T07/T08 integration tests | existing | still pass over the new app (if A) |

## Verify in Docker

`make smoke` still passes (the control channel moved, if A). Then `curl -k -H "Authorization: Bearer $ADMIN" --data-binary @somefile "https://localhost:8443/artifacts?name=x&version=v1"` against the compose Master, and `curl -k … /artifacts/<hash> | sha256sum` matches.

## Done when

- [ ] Content-addressed, streamed, atomic store with aliases.
- [ ] HTTP routes with token auth; `Range` works.
- [ ] Port decision made, recorded in ADR-0007, reflected in Dockerfile and deployment docs.
- [ ] Existing control-channel tests pass unchanged.

## If this fails

- **Porting the control channel to Starlette breaks reconnect or heartbeat behaviour in ways that take more than ~2 h to chase:** switch to option B (two ports) for v0.1 and file a `spec-issue` to revisit.
- **uvicorn TLS with the self-signed cert misbehaves:** test `ssl_keyfile`/`ssl_certfile` in isolation first; the Worker pins by fingerprint, so only the cert, not the chain, matters.

## References

- [ADR-0012](../adr/0012-content-addressed-artifacts.md), [ADR-0007](../adr/0007-websocket-http-transport.md), [ADR-0014](../adr/0014-admin-tokens-for-submission.md)
- Starlette WebSockets: https://www.starlette.io/websockets/ · uvicorn SSL settings: https://www.uvicorn.org/settings/#https

## History

- 2026-11-10: Card written (planning rewrite).
