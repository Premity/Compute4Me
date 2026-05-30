# Compute4Me

> A Docker-native, master-orchestrated distributed deep-learning **Fabric** for heterogeneous, firewall-constrained machines. Pool your lab GPUs and a friend's RTX 3070 into one compute pool — with one `docker run` per machine, no SSH, no port forwarding.

## Status

**v0.1 — in development.** Greenfield: the design is done; implementation is starting. See [docs/prd.md](./docs/prd.md) for the v0.1 milestone scope and acceptance criteria, and [docs/roadmap.md](./docs/roadmap.md) for what comes after.

## Why this exists

Researchers with scattered compute (a few lab GPUs, a CPU box, a friend's spare GPU at home) currently can't pool it easily. **Ray / Horovod / PyTorch DDP** assume an admin-provisioned cluster with SSH and firewall control. **Hivemind / SWARM** can pool internet volunteers but force the model into Decentralized Mixture-of-Experts — useless for a standard InceptionResNet. None of them know that a 24 GB RTX 3070 is 4× faster than a 6 GB GTX 1060.

Compute4Me targets exactly that gap: one `docker run` to join, no firewall changes, model code stays vanilla (no `import compute4me` required), and the scheduler is **DL-aware** — it knows VRAM, throughput, and cached datasets, and places work where it'll finish soonest.

See [docs/research/novelty.md](./docs/research/novelty.md) for the full positioning vs. Ray and the wider landscape.

## Quick start *(once v0.1 ships)*

> Compute4Me is pre-release. The commands below describe the intended UX per the v0.1 spec; they don't run yet.

Three personas with very different setups. Pick the one that's you.

### As a Worker contributor

You want to lend a GPU. One command, anywhere — behind NAT, behind a corporate firewall, doesn't matter. No SSH, no port forwarding, no firewall changes.

```bash
docker run -d --gpus all \
  -e C4M_MASTER=wss://master.example:8443 \
  -e C4M_TOKEN=eyJ... \
  -v c4m-cache:/var/cache/c4m \
  -v /var/run/docker.sock:/var/run/docker.sock \
  ghcr.io/premity/compute4me:latest worker
```

(The operator gives you the URL and the token together, out-of-band.)

That's it. The Worker connects outbound only, profiles your hardware, joins the Room, and starts taking Tasks. `docker logs -f` shows it live; `docker stop` removes it.

(The `-v /var/run/docker.sock:...` gives the Worker access to your host's Docker — needed because it runs the user's model containers. This is standard for CI-runner-style workloads but is a real privilege grant; see [SECURITY.md](./SECURITY.md).)

### As a Master operator

You're hosting the compute pool. The Master runs in a Docker container; you talk to it with `docker exec`.

```bash
# Start the Master (one time):
docker run -d --name c4m \
  -v c4m-data:/data -p 8443:8443 \
  ghcr.io/premity/compute4me:latest serve --room lab

# Issue an invite token for a Worker:
docker exec c4m compute4me token issue --room lab --max-workers 1 --ttl 24h
# → prints a JWT; hand it to the contributor out-of-band (Signal, email).

# Check who's connected:
docker exec c4m compute4me status

# Issue an admin token for yourself (lets you submit Jobs from your laptop):
docker exec c4m compute4me token issue --room lab --admin --ttl 30d
```

**Optional ergonomic shortcut.** If you'll be running these often, one shell alias makes it feel native:
```bash
alias compute4me='docker exec c4m compute4me'
# Then: compute4me token issue --room lab
```
Skip it if you prefer.

### As a Researcher submitting Jobs

You have an admin token and want to submit work from your laptop. Install the Python package — it gives you both the Python API and the `compute4me` CLI on your host:

```bash
pip install compute4me
export C4M_MASTER=wss://master.example:8443
export C4M_TOKEN=eyJ...                  # admin token from the operator

# CLI:
compute4me status
compute4me fetch j_4z8c --out ./results

# Or Python:
python << 'EOF'
from compute4me import Client, loguniform, uniform
c = Client.from_env()
job = c.submit_search(
    image="ghcr.io/you/your-model:latest",
    metric="val_auc", direction="maximize",
    n_trials=64, top_k=5, sampler="optuna",
    search_space={"lr": loguniform(1e-5, 1e-2), "dropout": uniform(0, 0.5)},
    inputs=["my-dataset/v1"],
)
c.wait(job)
c.download(job, out="./results")
EOF
```

The Master schedules 64 trials across the available Workers — biggest trials to the fastest GPUs, never on Workers with insufficient VRAM, preferring Workers that already have the dataset cached.

**No-Python fallback for ad-hoc CLI use:**
```bash
docker run --rm \
  -e C4M_MASTER=wss://master.example:8443 \
  -e C4M_TOKEN=eyJ... \
  ghcr.io/premity/compute4me:latest status
```

For the full operator surface, see [docs/architecture/wire-protocol.md](./docs/architecture/wire-protocol.md) and [docs/architecture/deployment.md](./docs/architecture/deployment.md).

## Directory structure

```
.
├── README.md                       # ← you are here
├── LICENSE                         # Apache-2.0
├── CONTRIBUTING.md                 # dev workflow (branches, commits, PRs, tests, manual phase)
├── CHANGELOG.md                    # per-version release notes
├── SECURITY.md                     # vulnerability reporting
├── docs/
│   ├── README.md                   # docs index — start here
│   ├── prd.md                      # current milestone's Product Requirements Document
│   ├── context.md                  # canonical glossary
│   ├── roadmap.md                  # what's deferred to v0.2+
│   ├── architecture/               # durable system reference (overview, data model, modules, wire protocol)
│   ├── adr/                        # Architecture Decision Records
│   ├── research/                   # literature review + positioning
│   └── archive/                    # frozen snapshots of past-version PRDs
└── (src/, tests/, examples/, scripts/, etc. land as code is written)
```

## How it works (in one paragraph)

A **Master** process opens a **Room** and issues **Invite Tokens**. A contributor runs one Docker container with a token and becomes a **Worker** — connecting *outbound only* to the Master, with no inbound ports or SSH. Each Worker advertises a **Capability Profile** (GPU, VRAM, throughput micro-benchmark, cached datasets, bandwidth). The researcher submits a **Job** — either a **Map** (containerized batch over data shards) or a **Search** (containerized batch over config space). The Master's **Scheduler** assigns work via best-fit placement: faster Workers get heavier Tasks, VRAM-infeasible Tasks are filtered, cached data is preferred. Workers run user images per the **Container Contract** (env-vars-in, files-out — no `import compute4me` required), report results, and stay idle for more.

For the full picture: [docs/architecture/overview.md](./docs/architecture/overview.md).

## What's in scope vs not (v0.1)

**v0.1 does:**
- Docker-native onboarding behind any NAT / firewall.
- Capability-aware scheduling (VRAM, throughput, locality).
- Two Job primitives: Map (sharded batch) and Search (Optuna HPO + raw lists).
- Reliability: heartbeat detection (~30s), retries (≤3), OOM-promotion, quarantine, Master persistence.
- Closed-membership Rooms via signed Invite Tokens.

**v0.1 deliberately does *not*:**
- Distributed training — that's v0.4.
- Models that don't fit on one GPU — pipeline parallelism is v0.6/v1.0.
- Open/public Rooms or Byzantine-robust aggregation — see [ADR-0002](./docs/adr/0002-closed-membership-rooms.md).
- Multi-tier hierarchical aggregation — see [ADR-0001](./docs/adr/0001-flat-master-not-hierarchical.md).

Full registry: [docs/roadmap.md](./docs/roadmap.md).

## Contributing

This is currently a one-person project with no external contributors. The development workflow (branches, commits, PRs, tests, manual verification, docs convention) is documented in [CONTRIBUTING.md](./CONTRIBUTING.md). Issue templates and a PR template ship with the repo.

If you want to discuss or contribute regardless, open an issue — the polish template fits informal feedback, the bug template fits actual broken behavior.

## License

Apache License 2.0 — see [LICENSE](./LICENSE).

## Research framing

Compute4Me is a research project as well as a tool. The v0.1 milestone produces a measurement of **DL-aware, automatic-capability-discovery, heterogeneity-native scheduling** via a 3-arm comparison (Ray default / Ray with manual resource labels / Compute4Me) on a real heterogeneous fleet, plus a simulation arm at 10/50/200 Workers. See [docs/research/](./docs/research/) for context.
