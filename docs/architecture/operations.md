# Operations

Reference for running, maintaining, and moving a Compute4Me deployment. Practical recipes; assumes you've already done first-time bootstrap per [deployment.md](./deployment.md). For terminology see [context.md](../context.md); for design rationale see [adr/](../adr/).

## 1. Master lifecycle

### 1.1 Backup `master.db`

The Master's SQLite database holds all durable state: tokens, workers, jobs, tasks, artifacts, results. Lose it and you lose everything ([ADR-0012](../adr/0012-content-addressed-artifacts.md) — the Master is the artifact origin).

**Online backup (safe while Master is running)** — uses SQLite's `.backup` mechanism, which is WAL-aware:

```bash
docker exec c4m sqlite3 /data/master.db ".backup /data/master.db.bak"
docker cp c4m:/data/master.db.bak ./backup-$(date +%F).db
```

**Cold backup (Master stopped)** — straight file copy:

```bash
docker stop c4m
docker run --rm -v c4m-data:/data -v $(pwd):/backup alpine \
  tar czf /backup/c4m-data-$(date +%F).tgz -C /data .
docker start c4m
```

The cold backup captures the cert as well as the DB. Use cold backups when moving between hosts (§1.4).

### 1.2 Restore from backup

```bash
docker stop c4m
docker rm c4m
docker volume rm c4m-data                # only if you want a clean restore; otherwise skip
docker volume create c4m-data
docker run --rm -v c4m-data:/data -v $(pwd):/backup alpine \
  tar xzf /backup/c4m-data-YYYY-MM-DD.tgz -C /data
docker run -d --name c4m \
  -v c4m-data:/data -p 8443:8443 \
  ghcr.io/premity/compute4me:latest serve --room lab
```

After restore: existing tokens stay valid (cert and DB are restored together). Workers reconnect on next attempt — for them, it looks like a brief Master outage.

### 1.3 Upgrade the Master in place

```bash
docker pull ghcr.io/premity/compute4me:latest
docker stop c4m
docker rm c4m
docker run -d --name c4m \
  -v c4m-data:/data -p 8443:8443 \
  ghcr.io/premity/compute4me:latest serve --room lab
```

The volume persists; the new container loads the existing `master.db` and resumes.

**Schema-migration note (v0.1):** the SQLite schema is fixed for v0.1; no migration logic yet. Once schema changes between minor versions become real, a `_meta` table will track version + the Master will run forward-migrations on startup. For now, only upgrade within a single minor version unless release notes say otherwise.

**Worker / client compatibility:** the wire protocol is additive-only ([wire-protocol.md §Versioning](./wire-protocol.md)). Mixed-version Master / Worker / client deployments work as long as both sides are within v0.x.

### 1.4 Move the Master to a different host

Tokens stay valid across the move. The Master URL changes, so Workers need the new URL — but no token re-issuance.

This works because of [ADR-0015](../adr/0015-master-url-separate-from-token.md): tokens carry the cert fingerprint, not the URL. Copy the volume → cert is preserved → fingerprint unchanged → existing tokens still validate.

**Procedure:**

```bash
# On the OLD host:
docker stop c4m
docker run --rm -v c4m-data:/data -v $(pwd):/out alpine \
  tar czf /out/c4m-data.tgz -C /data .

# Transfer c4m-data.tgz to the NEW host (scp, rsync, USB stick, whatever).

# On the NEW host:
docker volume create c4m-data
docker run --rm -v c4m-data:/data -v $(pwd):/in alpine \
  tar xzf /in/c4m-data.tgz -C /data
docker run -d --name c4m \
  -v c4m-data:/data -p 8443:8443 \
  ghcr.io/premity/compute4me:latest serve --room lab

# Tell every Worker the new URL (out-of-band):
#   "Update your worker to use C4M_MASTER=wss://new-host.example:8443"
# Each Worker host does:
docker stop c4m-worker
docker rm c4m-worker
docker run -d --gpus all \
  -e C4M_MASTER=wss://new-host.example:8443 \
  -e C4M_TOKEN=<same token as before> \
  -v c4m-cache:/var/cache/c4m \
  -v /var/run/docker.sock:/var/run/docker.sock \
  ghcr.io/premity/compute4me:latest worker
```

**What you lose during the move:** in-flight Tasks. Workers disconnect when the OLD Master stops; Tasks running on them are re-queued when Workers reconnect to the new Master. Completed results are preserved (they're in the DB you just moved).

**What you don't need to do:** re-issue tokens, regenerate the cert, change any token claims. The migration is volume-copy + URL-update.

### 1.5 Rotate the Master cert (rare)

If the self-signed cert is compromised, you have to invalidate it. Every issued token carries the old fingerprint, so **all tokens become unusable** when the cert changes.

**Procedure:**

```bash
docker stop c4m
docker exec c4m rm /data/cert.pem /data/key.pem    # delete cert files
docker start c4m                                   # generates a fresh cert on boot
# All existing tokens now refuse to validate the new cert fingerprint.
# Re-issue every active token:
docker exec c4m compute4me token revoke <each old jti>   # optional but clean
docker exec c4m compute4me token issue --room lab --max-workers 4 --ttl 24h
# Distribute new tokens.
```

This is intentional friction — cert rotation should be a deliberate operator action, not something that happens accidentally. If you need to rotate frequently, see [ADR-0011](../adr/0011-tls-fingerprint-in-token.md)'s "revisit when" criteria — we'd need a different bootstrap design.

### 1.6 Decommission the Master

```bash
docker stop c4m
docker rm c4m
# Optional: archive the DB for forensics / future restore
docker run --rm -v c4m-data:/data -v $(pwd):/out alpine \
  tar czf /out/c4m-final-archive.tgz -C /data .
docker volume rm c4m-data
```

All connected Workers will see heartbeat timeout, retry-with-backoff for a while, then exit. No graceful Master shutdown signal in v0.1; this is acceptable for the closed-membership trust model.

## 2. Worker lifecycle

### 2.1 Pausing contribution (temporary, e.g., need GPU for desktop)

The clean way:

```bash
docker stop c4m-worker      # Worker disconnects; in-flight Task re-queued by Master
# ...later...
docker start c4m-worker     # Worker reconnects; resumes taking Tasks
```

The Worker's cache is preserved (volume), so the next Task with the same dataset costs zero transfer.

**`docker pause` works too** but Master sees the Worker as `down` after 30s and re-queues. `docker stop` is more honest about your intent.

### 2.2 Inspecting a stuck Task

A Task that's been "running" for hours with no output is the common operational mystery. Layered debugging:

1. **From the Master:**
   ```bash
   docker exec c4m compute4me status                    # which Worker has it?
   docker exec c4m compute4me logs task t_001 --tail 50 # what's the user container saying?
   docker exec c4m compute4me progress t_001            # any live metric updates?
   ```

2. **From the Worker host** (when user container is silent):
   ```bash
   docker ps                              # find the user container's ID
   docker top <container>                 # what processes are running inside?
   docker exec -it <container> /bin/bash  # interactive inspection (if image has a shell)
   docker stats <container>               # CPU / memory / GPU usage live
   ```

3. **GPU inspection** (Worker host):
   ```bash
   nvidia-smi                             # is the GPU actually being used?
   nvidia-smi pmon                        # per-process GPU activity
   ```

If the Task is genuinely stuck (deadlock, infinite loop), the cure is `docker exec c4m compute4me cancel JOB_ID` from the operator side — this SIGTERM-then-SIGKILLs the Task container.

### 2.3 Decommissioning a Worker

**Hard stop** (Worker is preemptible by design — the design assumes contributors close laptops):

```bash
docker stop c4m-worker
docker rm c4m-worker
# Cache volume can be deleted too if Worker isn't coming back:
docker volume rm c4m-cache
```

The in-flight Task is re-queued by the Master after a 30s heartbeat timeout; another Worker picks it up.

**Graceful drain** (finish current Task, then exit) is not in v0.1 — a deferred ergonomics item ([roadmap.md v0.3](../roadmap.md#v03--fabric-ergonomics--robustness)). For now, a hard stop is fine because retries are idempotent.

### 2.4 Worker reconnect behavior

Workers auto-reconnect with exponential backoff after a transient disconnect (Master restart, network blip, laptop sleep). No operator action needed. The maximum backoff is ~60s; after that, the Worker keeps trying every 60s indefinitely until told to stop.

## 3. Multi-Room operation

A single Master can host multiple Rooms — useful for separating concerns (`lab` for the InceptionResNet sweep, `personal` for one-off experiments). Rooms are namespaces; Workers and Jobs are scoped to one Room.

**Creating a second Room:**

A Room is implicitly created on first token issuance:

```bash
docker exec c4m compute4me token issue --room personal --admin --ttl 30d
# Auto-creates Room 'personal' if it doesn't exist.
```

No explicit `room create` command — keeps the surface small.

**Working with multiple Rooms:**

| Operation | Default behavior |
|---|---|
| `compute4me status` (no `--room`) | Lists all Rooms with a section per Room |
| `compute4me status --room lab` | Just one Room |
| `compute4me token list` (no `--room`) | All tokens across all Rooms |
| `compute4me jobs` (no `--room`) | All Jobs across all Rooms |
| `compute4me fetch JOB_ID` | Doesn't need `--room`; Job ID is unique |
| `compute4me cancel JOB_ID` | Same |

Set `C4M_ROOM` in your shell to scope all subsequent commands to one Room without typing `--room` repeatedly.

**Cross-Room considerations:**

- Workers belong to exactly one Room. To contribute a single host to two Rooms, run two Worker containers with two different tokens.
- Tokens are Room-scoped. An `admin` token for Room `lab` cannot submit Jobs to Room `personal`.
- Artifacts are shared across Rooms in the Master's content-addressed store (content hash is global). This means a dataset uploaded for `lab` is reusable from `personal` if you know its hash — convenient when you're the operator of both.

## 4. Co-locating Master and Worker on one host

You want to run both on your VPS / lab box, contributing the host's GPU to its own Room. Fully supported.

### 4.1 Quick form (one host, one terminal session)

```bash
# Start the Master (detached):
docker run -d --name c4m-master \
  -v c4m-data:/data -p 8443:8443 \
  ghcr.io/premity/compute4me:latest serve --room lab

# Issue a token for the local Worker:
TOKEN=$(docker exec c4m-master compute4me token issue --room lab --max-workers 1 --ttl 30d --quiet)

# Start the Worker, pointing at the local Master:
docker run -d --name c4m-worker \
  --gpus all \
  --network host \
  -v c4m-cache:/var/cache/c4m \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e C4M_MASTER=wss://localhost:8443 \
  -e C4M_TOKEN=$TOKEN \
  ghcr.io/premity/compute4me:latest worker
```

`--network host` lets the Worker reach `localhost:8443` directly. Trade-off: the Worker shares the host's network namespace (sees all host ports, can bind any port). Acceptable on a single-tenant lab machine; not great in a multi-tenant environment.

### 4.2 Cleaner form: Docker Compose

For repeatability, use Compose:

```yaml
# docker-compose.yml
version: '3.8'
services:
  master:
    image: ghcr.io/premity/compute4me:latest
    command: serve --room lab
    volumes:
      - c4m-data:/data
    ports:
      - "8443:8443"

  worker:
    image: ghcr.io/premity/compute4me:latest
    command: worker
    depends_on:
      - master
    environment:
      C4M_MASTER: wss://master:8443
      C4M_TOKEN: ${C4M_TOKEN}                # set in .env
    volumes:
      - c4m-cache:/var/cache/c4m
      - /var/run/docker.sock:/var/run/docker.sock
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]

volumes:
  c4m-data:
  c4m-cache:
```

Bootstrap:

```bash
# Start Master alone first, issue a token, set it in .env:
docker compose up -d master
export C4M_TOKEN=$(docker compose exec master compute4me token issue --room lab --max-workers 1 --quiet)
echo "C4M_TOKEN=$C4M_TOKEN" > .env
# Now bring up the Worker:
docker compose up -d worker
```

The Worker reaches the Master via the Compose-managed network (`wss://master:8443` resolves automatically). No `--network host` needed; cleaner isolation.

### 4.3 Quirks

- The Master's self-signed cert is valid for *all* hostnames (`*` SAN). The Worker can reach it via `localhost`, `master` (Compose DNS), or any other name; the fingerprint check still works.
- One Worker container per GPU even on a co-located setup. A 2-GPU host running both Master and Worker → two Worker containers (one per GPU) + one Master.
- Resource competition: the Master is lightweight (it's a control plane), but if the GPU is busy with user containers, the Worker should set `--max-vram-mb` to leave headroom — otherwise the Master's modest CPU footprint contests with whatever else is going on.

## 5. Operating the Master from an unreliable host

**Don't.** The Master must be reachable for Workers to do anything; if it sleeps, all in-flight Tasks heartbeat-timeout and Jobs stall.

If you have no choice (no VPS available, lab box on a flaky link):

- **Treat outages as Worker disconnects.** When the Master comes back, Workers reconnect, Master re-queues lost Tasks, work resumes. Total throughput suffers in proportion to uptime.
- **Use a power profile that prevents sleep.** On Linux: `systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target`. On a laptop, plug it in and configure "do nothing on lid close."
- **Run the Master in a `restart: unless-stopped` container** so it comes back automatically on host reboot:
  ```bash
  docker run -d --name c4m --restart unless-stopped \
    -v c4m-data:/data -p 8443:8443 \
    ghcr.io/premity/compute4me:latest serve --room lab
  ```

Master HA (multi-process replicas) is explicitly out of scope for v0.1 — see [docs/context.md "Out of scope"](../context.md).

## 6. Storage growth (what fills up over time)

v0.1 has no automatic GC of historical state. Three things grow unbounded:

| Thing | Where | When it matters |
|---|---|---|
| **`master.db` size** | Master's `/data/master.db` | Tens of thousands of completed Tasks |
| **Artifact store** | Master's `/data/artifacts/` (or wherever artifacts live) | Many large datasets / checkpoints |
| **Worker artifact cache** | Worker's `/var/cache/c4m/` | Many distinct datasets across Jobs |

**Mitigation in v0.1 (manual):**

- Periodically remove old Jobs you no longer need: `compute4me jobs --all --status completed` to list; no automatic delete command yet — drop into `sqlite3` if you really need to (advanced).
- Worker cache: stop Worker → delete `c4m-cache` volume → restart Worker. Re-fetches on next Job.

**v0.3 will add proper GC** ([roadmap.md v0.3](../roadmap.md#v03--fabric-ergonomics--robustness)): LRU cache eviction on Workers, configurable retention on the Master.

## 7. Emergencies

### 7.1 Stop everything

```bash
docker exec c4m compute4me cancel <each job ID>    # SIGTERM the user containers
docker stop c4m                                    # stop the Master
# On every Worker host:
docker stop c4m-worker
```

### 7.2 Kick a single Worker without revoking a whole token

There's no direct command in v0.1 — quarantining is automatic on repeated failure. If you need to manually evict a specific Worker, simplest is to ask the contributor to `docker stop c4m-worker` themselves. If the contributor is unresponsive, revoke their token: they'll be disconnected and won't be able to rejoin.

### 7.3 Token leaked

```bash
docker exec c4m compute4me token revoke <jti>
```

Active Workers using that token are kicked. New joins refused.

### 7.4 Master compromised

Worst case. Treat as:

1. `docker stop c4m`
2. Revoke all tokens via DB inspection (`sqlite3 /data/master.db "UPDATE tokens SET revoked=1"`)
3. Cert rotation (§1.5)
4. Re-issue tokens
5. Inspect Worker hosts for any user containers that might have been launched from a compromised admin token (in the worst case, the attacker had `docker run` on every Worker via the socket mount — see [SECURITY.md](../../SECURITY.md))

This is why the trust model is closed-membership ([ADR-0002](../adr/0002-closed-membership-rooms.md)): if your Master is compromised, every Worker host you've enrolled is potentially compromised. Keep admin tokens carefully.

## 8. Things this doc deliberately doesn't cover

- **Performance tuning.** Defer until v0.2 brings calibrated cost model.
- **Multi-Master / federation.** Not on the roadmap.
- **Detailed schema-migration recipes.** v0.1 has a frozen schema.
- **Per-Worker resource quotas beyond `max_workers`.** Deferred ([roadmap.md "Someday"](../roadmap.md#someday--unscheduled-no-version-committed)).
- **Web UI for ops.** None planned for v0.1. CLI is the primary surface.
