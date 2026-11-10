"""Capability profiler + throughput micro-benchmark.

``profile()`` gathers GPU (nvidia-smi or ``cpu``), CPU/RAM/disk (psutil/shutil), and
``datasets_cached``; ``run_micro_benchmark()`` runs a fixed 30s ResNet18 fwd/bwd to a
samples/sec ``throughput_ref``. Maintains a persistent ``host_id``. Designed to accept
injected fake probes for testing.

Only ``run_micro_benchmark`` needs PyTorch, and it is imported lazily — the Compute4Me
Worker shells out to the *user's* container for real training (the Container Contract,
ADR-0006), so torch is not a runtime dependency of the Worker itself. It is declared as the
optional ``bench`` extra and installed once per host (see scripts/setup-worker.sh); the rest
of this module imports and runs without it.
"""

from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import psutil

from compute4me.types import CapabilityProfile, GpuInfo

if TYPE_CHECKING:
    from collections.abc import Callable

_HOST_ID_FILE = "host-id"


class BenchmarkUnavailable(RuntimeError):
    """Raised when the micro-benchmark is requested but PyTorch (the ``bench`` extra) is absent."""


# --- Persistent host identity ----------------------------------------------


def ensure_host_id(data_dir: str | Path) -> str:
    """Return this host's stable id, generating and persisting it on first call.

    Stored in the Worker's data volume so it survives container restarts (the Scheduler's
    data-locality keys off a stable host identity).
    """
    data = Path(data_dir)
    data.mkdir(parents=True, exist_ok=True)
    path = data / _HOST_ID_FILE
    if path.exists():
        return path.read_text().strip()
    host_id = uuid.uuid4().hex
    path.write_text(host_id)
    return host_id


# --- Hardware probes (real implementations; injectable for tests) ----------


def detect_gpu() -> GpuInfo:
    """Probe the GPU via ``nvidia-smi``; fall back to ``model='cpu'`` on a CPU-only host.

    Reports the first GPU. Any failure (no ``nvidia-smi``, no driver, parse error) is a
    CPU-only host as far as the profile is concerned.
    """
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return GpuInfo(model="cpu", vram_total_mb=0, vram_free_mb=0)
    return parse_nvidia_smi(out)


def parse_nvidia_smi(output: str) -> GpuInfo:
    """Parse one CSV line of ``name, total_mb, free_mb`` into a GpuInfo (cpu on bad output)."""
    lines = output.strip().splitlines()
    if not lines:
        return GpuInfo(model="cpu", vram_total_mb=0, vram_free_mb=0)
    parts = [p.strip() for p in lines[0].split(",")]
    if len(parts) != 3:
        return GpuInfo(model="cpu", vram_total_mb=0, vram_free_mb=0)
    name, total, free = parts
    try:
        return GpuInfo(model=name, vram_total_mb=int(total), vram_free_mb=int(free))
    except ValueError:
        return GpuInfo(model="cpu", vram_total_mb=0, vram_free_mb=0)


def host_stats(data_dir: str | Path) -> tuple[int, int, int]:
    """Return ``(cpu_cores, ram_mb, disk_free_mb)`` for the host and its data volume."""
    cores = psutil.cpu_count(logical=True) or 1
    ram_mb = psutil.virtual_memory().total // (1024 * 1024)
    disk_free_mb = shutil.disk_usage(str(data_dir)).free // (1024 * 1024)
    return cores, ram_mb, disk_free_mb


def scan_cached_datasets(cache_dir: str | Path) -> list[tuple[str, str]]:
    """List ``(dataset_id, version_hash)`` pairs cached locally for data-locality.

    v0.1 derives them from the cache directory layout (``<dataset_id>/<version_hash>/``).
    Returns ``[]`` when the cache is empty or absent. The cache itself lands in T12; this
    reads whatever is present without requiring it.
    """
    cache = Path(cache_dir)
    if not cache.is_dir():
        return []
    pairs: list[tuple[str, str]] = []
    for dataset in sorted(cache.iterdir()):
        if not dataset.is_dir():
            continue
        for version in sorted(dataset.iterdir()):
            if version.is_dir():
                pairs.append((dataset.name, version.name))
    return pairs


def run_micro_benchmark(seconds: float = 30) -> float:
    """Fixed ResNet18 fwd/bwd loop; returns samples/sec — the cross-Worker yardstick.

    Lazily imports PyTorch (the ``bench`` extra). Raises :class:`BenchmarkUnavailable` if
    torch is not installed. Uses CUDA when available, else CPU.
    """
    import time

    try:
        import torch
        from torchvision.models import resnet18
    except ImportError as exc:  # torch / torchvision not installed
        raise BenchmarkUnavailable(
            "run_micro_benchmark needs PyTorch; install the 'bench' extra "
            "(uv sync --extra bench) or run scripts/setup-worker.sh"
        ) from exc

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = resnet18().to(device).train()
    optimizer = torch.optim.SGD(model.parameters(), lr=0.01)
    loss_fn = torch.nn.CrossEntropyLoss()
    batch = 16
    inputs = torch.randn(batch, 3, 224, 224, device=device)
    targets = torch.randint(0, 1000, (batch,), device=device)

    samples = 0
    start = time.perf_counter()
    while time.perf_counter() - start < seconds:
        optimizer.zero_grad()
        loss = loss_fn(model(inputs), targets)
        loss.backward()
        optimizer.step()
        samples += batch
    if device.type == "cuda":
        torch.cuda.synchronize()
    elapsed = time.perf_counter() - start
    return samples / elapsed


# --- Assembly --------------------------------------------------------------


def profile(
    *,
    data_dir: str | Path,
    cache_dir: str | Path,
    gpu_probe: Callable[[], GpuInfo] = detect_gpu,
    stats_probe: Callable[[str | Path], tuple[int, int, int]] = host_stats,
    dataset_scan: Callable[[str | Path], list[tuple[str, str]]] = scan_cached_datasets,
    benchmark: Callable[[], float] | None = None,
) -> CapabilityProfile:
    """Build the full Capability Profile the Worker advertises on ``join``.

    Probes are injectable so this is unit-testable with fakes (no real hardware / torch).
    ``benchmark`` defaults to :func:`run_micro_benchmark` (lazy torch); pass a fake in tests.
    ``bandwidth_to_master_mbps`` / ``rtt_to_master_ms`` are left at ``0.0`` here — they are
    Master-initiated probes populated in T10.
    """
    cores, ram_mb, disk_free_mb = stats_probe(data_dir)
    bench = benchmark if benchmark is not None else run_micro_benchmark
    return CapabilityProfile(
        host_id=ensure_host_id(data_dir),
        gpu=gpu_probe(),
        cpu_cores=cores,
        ram_mb=ram_mb,
        disk_free_mb=disk_free_mb,
        datasets_cached=dataset_scan(cache_dir),
        throughput_ref=bench(),
        bandwidth_to_master_mbps=0.0,
        rtt_to_master_ms=0.0,
    )
