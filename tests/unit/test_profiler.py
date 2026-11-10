"""T09 acceptance: profile() reports real GPU on a GPU host, model='cpu' on CPU-only, a
positive throughput_ref, and a host_id stable across restarts — all via injected fake probes.

The profiler is the only hardware-touching Worker module, so these unit tests inject fakes
for the GPU/stats/dataset/benchmark probes (no nvidia-smi, no psutil reliance, no torch).
The real micro-benchmark (`run_micro_benchmark`) is GPU/torch-touching and exercised
manually on a real host, not in CI.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from compute4me.types import GpuInfo
from compute4me.worker.profiler import (
    BenchmarkUnavailable,
    ensure_host_id,
    parse_nvidia_smi,
    profile,
    run_micro_benchmark,
    scan_cached_datasets,
)


def _fake_stats(_data_dir: str | Path) -> tuple[int, int, int]:
    return (8, 32000, 500000)


def _gpu_info() -> GpuInfo:
    return GpuInfo(model="NVIDIA GeForce RTX 3070", vram_total_mb=8192, vram_free_mb=8000)


@pytest.mark.unit
@pytest.mark.task("T09")
def test_profile_reports_real_gpu_on_gpu_host(tmp_path: Path) -> None:
    prof = profile(
        data_dir=tmp_path,
        cache_dir=tmp_path / "cache",
        gpu_probe=_gpu_info,
        stats_probe=_fake_stats,
        benchmark=lambda: 412.5,
    )

    assert prof.gpu.model == "NVIDIA GeForce RTX 3070"
    assert prof.gpu.vram_total_mb == 8192


@pytest.mark.unit
@pytest.mark.task("T09")
def test_profile_reports_cpu_on_cpu_only_host(tmp_path: Path) -> None:
    cpu = lambda: GpuInfo(model="cpu", vram_total_mb=0, vram_free_mb=0)  # noqa: E731

    prof = profile(
        data_dir=tmp_path,
        cache_dir=tmp_path / "cache",
        gpu_probe=cpu,
        stats_probe=_fake_stats,
        benchmark=lambda: 50.0,
    )

    assert prof.gpu.model == "cpu"
    assert prof.gpu.vram_total_mb == 0


@pytest.mark.unit
@pytest.mark.task("T09")
def test_profile_has_positive_throughput(tmp_path: Path) -> None:
    prof = profile(
        data_dir=tmp_path,
        cache_dir=tmp_path / "cache",
        gpu_probe=_gpu_info,
        stats_probe=_fake_stats,
        benchmark=lambda: 412.5,
    )

    assert prof.throughput_ref > 0


@pytest.mark.unit
@pytest.mark.task("T09")
def test_profile_carries_stats_and_zero_network_fields(tmp_path: Path) -> None:
    prof = profile(
        data_dir=tmp_path,
        cache_dir=tmp_path / "cache",
        gpu_probe=_gpu_info,
        stats_probe=_fake_stats,
        benchmark=lambda: 1.0,
    )

    assert (prof.cpu_cores, prof.ram_mb, prof.disk_free_mb) == (8, 32000, 500000)
    # Bandwidth/RTT are Master-initiated probes (T10) — zero here.
    assert prof.bandwidth_to_master_mbps == 0.0
    assert prof.rtt_to_master_ms == 0.0


@pytest.mark.unit
@pytest.mark.task("T09")
def test_host_id_is_stable_across_restarts(tmp_path: Path) -> None:
    first = ensure_host_id(tmp_path)
    # A "restart" re-reads the persisted id from the same data dir.
    second = ensure_host_id(tmp_path)

    assert first == second
    assert (tmp_path / "host-id").read_text().strip() == first


@pytest.mark.unit
@pytest.mark.task("T09")
def test_distinct_data_dirs_get_distinct_host_ids(tmp_path: Path) -> None:
    a = ensure_host_id(tmp_path / "a")
    b = ensure_host_id(tmp_path / "b")

    assert a != b


@pytest.mark.unit
@pytest.mark.task("T09")
def test_parse_nvidia_smi_reads_first_gpu() -> None:
    gpu = parse_nvidia_smi("NVIDIA GeForce RTX 3070, 8192, 8000\n")

    assert gpu.model == "NVIDIA GeForce RTX 3070"
    assert gpu.vram_total_mb == 8192
    assert gpu.vram_free_mb == 8000


@pytest.mark.unit
@pytest.mark.task("T09")
@pytest.mark.parametrize("bad", ["", "garbage", "name,only-two", "name, notint, 5"])
def test_parse_nvidia_smi_falls_back_to_cpu_on_bad_output(bad: str) -> None:
    assert parse_nvidia_smi(bad).model == "cpu"


@pytest.mark.unit
@pytest.mark.task("T09")
def test_scan_cached_datasets_reads_layout(tmp_path: Path) -> None:
    (tmp_path / "kepler-q1-q17" / "v3").mkdir(parents=True)
    (tmp_path / "mnist" / "abc123").mkdir(parents=True)

    pairs = scan_cached_datasets(tmp_path)

    assert ("kepler-q1-q17", "v3") in pairs
    assert ("mnist", "abc123") in pairs


@pytest.mark.unit
@pytest.mark.task("T09")
def test_scan_cached_datasets_empty_when_absent(tmp_path: Path) -> None:
    assert scan_cached_datasets(tmp_path / "does-not-exist") == []


@pytest.mark.unit
@pytest.mark.task("T09")
def test_micro_benchmark_raises_clearly_without_torch() -> None:
    # torch is the optional 'bench' extra, not installed in CI; the benchmark must fail
    # with a clear, actionable error rather than a bare ImportError.
    try:
        import torch  # noqa: F401
    except ImportError:
        with pytest.raises(BenchmarkUnavailable):
            run_micro_benchmark(seconds=0.01)
    else:
        pytest.skip("torch is installed; the no-torch path can't be exercised here")
