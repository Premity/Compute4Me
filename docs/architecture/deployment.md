# Deployment

Practical reference for getting a Master and Workers running. Covers volume mounts, the Docker socket grant on Workers, GPU access flags, and where the CLI binary lives. Not a design document — design lives in [overview.md](./overview.md). The per-persona quick start is in [../../README.md](../../README.md).

## The single Docker image

```
ghcr.io/premity/compute4me:latest
```

One image, two daemon modes (selected by the first arg):

```bash
docker run ... ghcr.io/premity/compute4me:latest serve --room ROOM     # Master
docker run ... ghcr.io/premity/compute4me:latest worker --token TOKEN  # Worker
```

The image's entrypoint is the `compute4me` binary, so any subcommand works:

```bash
docker run --rm ... ghcr.io/premity/compute4me:latest token issue ...  # one-shot client call
docker exec c4m compute4me status                                       # against a running daemon
```

## Where the CLI lives

Three legitimate paths depending on the persona; pick the one that fits.

| Persona | How they invoke the CLI |
|---|---|
| **Master operator** | `docker exec <container> compute4me <cmd>` against the running Master container. Optionally aliased: `alias compute4me='docker exec c4m compute4me'`. No host install. |
| **Researcher with Python** | `pip install compute4me` — gives the CLI on the host *and* the Python submission API. The CLI talks to the Master over WSS like any other client. |
| **Researcher without Python** | `docker run --rm -e C4M_* ghcr.io/premity/compute4me:latest <cmd>` for one-off use. Verbose; fine for occasional commands. |

There is **no separate "CLI install" requirement**. The binary already exists in the image; the question is just whether you want it locally or invoke it through Docker.

## Master deployment

### Minimal

```bash
docker run -d --name c4m \
  -v c4m-data:/data \
  -p 8443:8443 \
  ghcr.io/premity/compute4me:latest serve --room lab
```

### What each flag does

| Flag | Why |
|---|---|
| `-d` | Detached; the daemon runs in the background. Omit `-d` for foreground (you'll see the event stream live; Ctrl-C to stop). |
| `--name c4m` | Convenient label for `docker exec` calls. Pick any name. |
| `-v c4m-data:/data` | Persists `master.db` (SQLite state) and the self-signed cert across container restarts. **Don't skip this** — without it, every restart loses all state. |
| `-p 8443:8443` | Exposes the WSS + HTTP port. The host must be reachable from every Worker (LAN-routable for lab setups; public for cross-internet). |
| `serve --room lab` | The mode + the Room name. Creates the Room if it doesn't exist. |

### Optional flags

| Flag | Default | When to set |
|---|---|---|
| `--data-dir DIR` | `/data` | If you want the SQLite + cert in a non-default location inside the container |
| `--bind HOST:PORT` | `0.0.0.0:8443` | To bind to a specific interface (e.g., `127.0.0.1:8443` for local-only) |

### Networking notes

- The Master needs to be **reachable from every Worker**. For lab deployments, that's a routable IP on your LAN. For cross-internet contributors, that's a small VPS or a port-forwarded home machine.
- TLS is via self-signed cert. Workers pin the fingerprint from the Invite Token (see [ADR-0011](../adr/0011-tls-fingerprint-in-token.md)). No CA, no domain, no Let's Encrypt.
- The Master initiates **no** outbound connections except to fetch images from a registry. All Worker traffic is Worker-initiated.

### Restart, upgrade, migration

- **Restart:** `docker restart c4m` — state in `/data` is preserved; in-flight Jobs resume (see [PRD §8 T20](../prd.md#8-implementation-tasks-t01t27)).
- **Upgrade:** `docker pull` the new image, `docker stop c4m && docker rm c4m`, then run the same `docker run` again. State persists in the named volume.
- **Migrate Master to a new host:** copy the `c4m-data` volume to the new host, run with the same volume. Tokens stay valid (self-signed cert moves with the volume). Workers reconnect automatically. *Detailed migration runbook is queued for the operational-amenities discussion.*

## Worker deployment

### Minimal

```bash
docker run -d \
  --gpus all \
  -e C4M_MASTER=wss://master.example:8443 \
  -e C4M_TOKEN=eyJ... \
  -v c4m-cache:/var/cache/c4m \
  -v /var/run/docker.sock:/var/run/docker.sock \
  ghcr.io/premity/compute4me:latest worker
```

### What each flag does

| Flag | Why |
|---|---|
| `--gpus all` | Exposes all NVIDIA GPUs on the host to the Worker. Requires [nvidia-container-toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/) on the host. Drop this on a CPU-only Worker. |
| `-e C4M_MASTER=...` | The Master URL the Worker connects to. Equivalent flag form: `worker --master wss://...`. The URL is kept separate from the Token so the Master can be moved without re-issuing tokens — see [ADR-0015](../adr/0015-master-url-separate-from-token.md). |
| `-e C4M_TOKEN=...` | The Invite Token (obtained out-of-band from the operator). Equivalent flag form: `worker --token eyJ...`. |
| `-v c4m-cache:/var/cache/c4m` | Persists the Worker's content-addressed Artifact cache across restarts. Repeat Jobs on the same dataset are then free. |
| `-v /var/run/docker.sock:/var/run/docker.sock` | Gives the Worker access to the host's Docker daemon so it can `docker run` the user's model images. **See security note below.** |

### Optional flags

| Flag | Default | When to set |
|---|---|---|
| `--name NAME` | Auto-generated (`w_<uuid>`) | If you want a stable identifier in the operator's `status` view |
| `--cache-dir DIR` | `/var/cache/c4m` | If you want the cache elsewhere inside the container |
| `--max-vram-mb N` | All available | Caps how much VRAM the Worker offers — e.g., contribute 4 GB of an 8 GB card and reserve the rest for your desktop |
| `-d` | foreground | Detach to run as a daemon |

### Throughput benchmark dependency (`bench` extra)

The Worker advertises a `throughput_ref` (samples/sec on a fixed ResNet18 micro-benchmark) so the Scheduler can compare heterogeneous hosts. That benchmark — and *only* that benchmark — needs PyTorch. Real training/inference runs inside the **user's** container, which carries its own ML stack (the [Container Contract](./wire-protocol.md#1-container-contract-masterworker--user-image), ADR-0006), so torch is **not** baked into the Worker image (keeping it lean).

Install the CUDA-matched build **once per host** at setup time — not at container start, so firewall-constrained Workers never download hundreds of MB at runtime:

```bash
scripts/setup-worker.sh   # detects CUDA via nvidia-smi, installs the matching torch (or CPU build)
```

Without it, the Worker runs fine but `run_micro_benchmark` raises `BenchmarkUnavailable`; the rest of the profile (GPU/CPU/RAM/disk/cache) is gathered regardless.

### Running multiple Workers on one host

One container = one Worker. To contribute multiple GPUs from the same host, run multiple Worker containers, each pinned to a different GPU:

```bash
# Worker on GPU 0:
docker run -d --gpus '"device=0"' \
  -e C4M_MASTER=wss://master.example:8443 \
  -e C4M_TOKEN=<TOKEN> \
  -v c4m-cache:/var/cache/c4m \
  -v /var/run/docker.sock:/var/run/docker.sock \
  ghcr.io/premity/compute4me:latest worker

# Worker on GPU 1 (different cache volume to avoid contention):
docker run -d --gpus '"device=1"' \
  -e C4M_MASTER=wss://master.example:8443 \
  -e C4M_TOKEN=<TOKEN> \
  -v c4m-cache-1:/var/cache/c4m \
  -v /var/run/docker.sock:/var/run/docker.sock \
  ghcr.io/premity/compute4me:latest worker
```

Each Worker registers separately with the Master under its own `host_id`. They count separately against the token's `max_workers` cap, so issue a token with `--max-workers 2` for a 2-GPU host.

### Security note — the Docker socket mount

`-v /var/run/docker.sock:/var/run/docker.sock` gives the Worker container **root-equivalent access to the host**. Anything inside the Worker container can `docker run` arbitrary images, mount any host path, escape to root.

This is **standard practice** for runner-style workloads — every CI runner (GitHub Actions, GitLab, Jenkins agents) does the same. The trust model assumes:

- You only run the official `ghcr.io/premity/compute4me` image (or your own audited fork).
- The Compute4Me Master you joined is operated by someone you trust (token-gated, [ADR-0002](../adr/0002-closed-membership-rooms.md)).
- The user model images that the Master assigns are similarly trusted.

If any of those assumptions fail, the socket mount is a vulnerability. Alternatives for stricter setups (sysbox, gVisor, rootless Docker) are out of scope for v0.1 — the closed-membership trust model makes this acceptable.

See [../../SECURITY.md](../../SECURITY.md) for the full threat model.

## Where do user model images come from?

The Worker pulls the image specified in the Job spec (e.g., `ghcr.io/hamda/spacesight-train:latest`) using its host Docker. The image must be accessible from the Worker — meaning either:

- **Public registry** (Docker Hub public, GHCR public): nothing extra needed.
- **Private registry**: the Worker host's Docker daemon must already be `docker login`-ed. Master-mediated image distribution (so Workers don't need registry credentials of their own) is a [v0.3 feature](../roadmap.md#v03--fabric-ergonomics--robustness).

## Co-locating Master and Worker on one host

Yes, this is supported and common — your VPS or lab box can be both. See [operations.md §4](./operations.md) for the quick-form recipe and the Docker Compose alternative.

## Researcher's laptop (client-only)

No Docker needed if you only want to submit and inspect:

```bash
pip install compute4me     # Python 3.13+
export C4M_MASTER=wss://your-master.example:8443
export C4M_TOKEN=eyJ...    # admin token from the operator
compute4me status          # works, talks to the remote Master over WSS
```

The Python API is the same package — see [wire-protocol.md §5](./wire-protocol.md).

## Summary checklist

If you're following along for the first time:

- [ ] Docker installed on Master host
- [ ] Master host has a reachable IP/port from every Worker (LAN or public)
- [ ] `c4m-data` volume mounted to `/data` on the Master
- [ ] Port 8443 (or your chosen port) published
- [ ] On Worker hosts: Docker + nvidia-container-toolkit (for GPU) installed
- [ ] `c4m-cache` and `/var/run/docker.sock` mounted on each Worker
- [ ] Invite Token issued to each Worker out-of-band; admin token issued to each submitter
- [ ] If submitting from outside the Master host: `pip install compute4me` on the submitter's machine

That's the whole list. No service mesh, no Kubernetes, no orchestration layer to learn. Two containers + a Python install if you submit.
