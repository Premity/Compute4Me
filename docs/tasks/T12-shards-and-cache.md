# T12: Shard serving + Worker cache

| | |
|---|---|
| Phase | P2 |
| Size | M (3–5 h), after the dataset-format decision |
| Depends on | T11 |
| Unblocks | T17 |
| Branch | `feat/T12-shards-and-cache` |
| Issue | — |
| Status | Not started |

## Why this task exists

A Map Job over an 80 GB dataset in 20 shards must not send 80 GB to each Worker (PRD story 33), and a Worker that already holds the data must transfer nothing (story 34, and the locality half of the scheduler's novelty). This task gives the Master shard serving and the Worker a verified, content-addressed cache whose contents feed `datasets_cached`.

## Background you need

- **What exists:** `ShardDescriptor{kind: whole|index-range|file-list, start, end, files}` and `ArtifactRef{hash, shard}` ([types.py](../../src/compute4me/types.py)); `scan_cached_datasets(cache_dir)` in T09 reads a `<dataset_id>/<version_hash>/` layout; `ensure_cached(hash, shard) -> Path` is the interface in [modules.md](../architecture/modules.md#artifact-cache--workercachepy).
- **The gap:** an Artifact is one blob. "index-range" and "file-list" only make sense if a dataset has **items**: files, or records in a file. Nothing defines that yet (plan.md Open items).
- **Worker cache location:** `C4M_CACHE_DIR` (`/var/cache/c4m`) on the Worker's volume. T17 mounts subdirectories of it into user containers via the host daemon, so the layout must make a shard a **directory** that can be mounted read-only.

## Decide first

1. **What a dataset Artifact is.**
   - **A. Manifest of file blobs (Recommendation):** a dataset is a JSON manifest Artifact `{"kind": "dataset", "files": [{"path": "q1/kplr001.fits", "hash": "…", "size": …}, …]}` sorted by path; each file is its own content-addressed blob. `index-range [start, end)` = manifest entries by position; `file-list` = named paths. The Worker fetches only the blobs in its shard, dedups across dataset versions (an unchanged file is never re-fetched), and builds the shard directory from hard links into its blob cache. Cost: many small GETs; add a batch endpoint only if measured slow.
   - **B. Tar archive:** a dataset is one `.tar`; a shard is a member range streamed as a new tar. Fewer requests, but no dedup across versions, and the Master re-reads the archive per shard.
   - **C. Record ranges in one file** (lines/rows): fits CSV/JSONL inference but not file-per-sample datasets like light curves.
   Record the choice in ADR-0012's History and context.md (**Artifact**, **Dataset**).
2. **What `datasets_cached` reports.** Recommendation (with A): `(dataset_alias_or_hash, manifest_hash)` for each manifest whose blobs are **all** present. The Scheduler's locality preference is then "has every blob of this Task's shard", computed on the Master from the manifest plus the Worker's reported blob set if needed (keep v0.1 simple: whole-dataset granularity).

## Steps

1. (A) Manifest model in `types.py`; CLI-free helper `build_manifest(dir) -> manifest` plus an ingest path that uploads each file and then the manifest (used by T22/T23 later; test helper now).
2. Master: `serve_shard(manifest_hash, shard) -> list[entry]` and `GET /artifacts/{hash}/shard?kind=&start=&end=` (or POST with a file list) returning the shard's manifest slice.
3. Worker `worker/cache.py`: `ensure_cached(ref) -> Path`: fetch the shard slice, fetch missing blobs (streamed, hash-verified, atomic), build `shards/<task_id>/` with hard links; on hash mismatch discard, re-fetch once, then raise. Report bytes transferred (for the test, and later the events).
4. `scan_cached_datasets` reads the new layout; `datasets_cached` reflects it.
5. Docs: wire-protocol §3, data-model (manifest), deployment (cache layout and size), ADR-0012 History.

## Outputs

`types.py`, `master/artifacts.py`, `worker/cache.py`, `worker/profiler.py` (scan), docs, CHANGELOG.

## Tests

| File | Markers | Proves |
|---|---|---|
| `tests/unit/test_shards.py` | `task("T12")`, `unit` | index-range and file-list slices are exact; 4 shards of a 10-file manifest are non-overlapping and exhaustive |
| `tests/integration/test_cache.py` | `task("T12")`, `integration` | a Worker fetches only its shard (bytes transferred ≈ 1/N of the dataset); a second `ensure_cached` transfers 0 bytes; a corrupted blob is re-fetched, and a persistent mismatch raises |

## Verify in Docker

Upload a small directory dataset to the compose Master; from inside the Worker container run `ensure_cached` for shard 2 of 4 and list the shard directory (only its files present). Paste the bytes-transferred figure.

## Done when

- [ ] Dataset format decided and recorded; shards served exactly.
- [ ] The Worker cache verifies, dedups and skips; `datasets_cached` reflects it.
- [ ] The bytes-transferred test passes.

## If this fails

- **Hard links fail across filesystems** (cache on one mount, shard dirs on another): keep both under `C4M_CACHE_DIR`; if a host still can't, copy instead and log a WARNING.
- **Thousands of small GETs are slow** (more than 2× slower than one tar for the same bytes): add `POST /artifacts/batch` returning a tar stream of the requested blobs; the cache layout is unchanged.

## References

- [ADR-0012](../adr/0012-content-addressed-artifacts.md), [wire-protocol.md §3](../architecture/wire-protocol.md#3-artifact-channel-worker--master-http), PRD stories 31–35

## History

- 2026-11-10: Card written (planning rewrite).
