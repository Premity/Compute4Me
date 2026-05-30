# Single image, two entrypoints: `serve` (Master) and `worker`. Symmetric per ADR/overview.
# Multi-stage: build the venv with uv, then copy into a slim runtime image.

# --- builder: resolve and install deps into a self-contained venv ---
FROM python:3.13-slim AS builder

# uv: fast, reproducible dependency resolution. Pinned for build stability.
COPY --from=ghcr.io/astral-sh/uv:0.11.17 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Install dependencies first (cached unless pyproject/lock changes), then the project.
# --mount=type=cache keeps uv's download cache on a reusable BuildKit mount (outside the
# image), so rebuilds skip re-downloads without bloating the layers or the host disk.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY src/ ./src/
COPY README.md ./
# --no-editable bakes the package into .venv/site-packages instead of an editable .pth
# pointing back at /app/src — so the runtime stage can copy just the venv and stay
# self-contained (the source tree is not present at runtime).
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

# --- runtime: slim image with just the venv and the docker CLI ---
FROM python:3.13-slim AS runtime

# The Worker shells out to `docker` for user images via the mounted host socket
# (see SECURITY.md). Only the CLI client is needed — the daemon lives on the host — so
# install docker-cli, not the full docker.io engine package (much smaller).
RUN apt-get update \
    && apt-get install -y --no-install-recommends docker-cli \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Master state and Worker cache live on mounted volumes (see README quick start).
ENV C4M_DATA_DIR=/data \
    C4M_CACHE_DIR=/var/cache/c4m
VOLUME ["/data", "/var/cache/c4m"]

EXPOSE 8443

# `serve` and `worker` are subcommands of the single `compute4me` entrypoint, so
# `docker run <image> serve --room lab` / `docker run <image> worker` both work.
ENTRYPOINT ["compute4me"]
CMD ["--help"]
