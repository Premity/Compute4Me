"""Capability profiler + throughput micro-benchmark.

``profile()`` gathers GPU (nvidia-smi or ``cpu``), CPU/RAM/disk (psutil/shutil), and
``datasets_cached``; ``run_micro_benchmark()`` runs a fixed 30s ResNet18 fwd/bwd to a
samples/sec ``throughput_ref``. Maintains a persistent ``host_id``. Designed to accept
injected fake probes for testing.

Populated in T09.
"""

from __future__ import annotations
