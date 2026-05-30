"""T02 acceptance: core models round-trip JSON, reject bad payloads, enforce n_shards>0."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from compute4me.types import (
    ArtifactRef,
    CapabilityProfile,
    GpuInfo,
    MapJobSpec,
    SearchJobSpec,
    ShardDescriptor,
    ShardStrategy,
    Task,
    TaskError,
    TaskRequires,
    TaskResult,
    TokenClaims,
)


def _profile() -> CapabilityProfile:
    return CapabilityProfile(
        host_id="h1",
        gpu=GpuInfo(model="NVIDIA GeForce RTX 3070", vram_total_mb=8192, vram_free_mb=8000),
        cpu_cores=8,
        ram_mb=32000,
        disk_free_mb=500000,
        datasets_cached=[("kepler-q1-q17", "abc123")],
        throughput_ref=412.5,
        bandwidth_to_master_mbps=94.0,
        rtt_to_master_ms=12.0,
    )


@pytest.mark.unit
@pytest.mark.task("T02")
def test_capability_profile_round_trips_json() -> None:
    profile = _profile()

    restored = CapabilityProfile.model_validate_json(profile.model_dump_json())

    assert restored == profile


@pytest.mark.unit
@pytest.mark.task("T02")
def test_token_claims_round_trips_and_defaults_admin_false() -> None:
    claims = TokenClaims(
        jti="t1",
        room="lab",
        max_workers=4,
        expires_at="2026-07-01T00:00:00Z",
        master_cert_fp="ab:cd",
    )

    restored = TokenClaims.model_validate_json(claims.model_dump_json())

    assert restored == claims
    assert restored.admin is False


@pytest.mark.unit
@pytest.mark.task("T02")
def test_search_job_spec_round_trips_with_defaults() -> None:
    spec = SearchJobSpec(
        image="img:latest", metric="val_auc", n_trials=64, search_space={"lr": [1e-5, 1e-2]}
    )

    restored = SearchJobSpec.model_validate_json(spec.model_dump_json())

    assert restored == spec
    assert restored.direction == "maximize"
    assert restored.sampler == "optuna"


@pytest.mark.unit
@pytest.mark.task("T02")
def test_task_round_trips_with_nested_shard() -> None:
    task = Task(
        id="t_1",
        job_id="j_1",
        args={"lr": 0.01},
        input_refs=[
            ArtifactRef(hash="h1", shard=ShardDescriptor(kind="index-range", start=0, end=100))
        ],
        requires=TaskRequires(min_vram_mb=4096, gpu_required=True, est_work_units=1000.0),
    )

    restored = Task.model_validate_json(task.model_dump_json())

    assert restored == task


@pytest.mark.unit
@pytest.mark.task("T02")
def test_task_error_defaults() -> None:
    err = TaskError(message="boom")

    assert err.oom is False
    assert err.exit_code is None


@pytest.mark.unit
@pytest.mark.task("T02")
def test_task_result_failed_round_trips() -> None:
    result = TaskResult(task_id="t_1", status="failed", error="non-finite metric")

    restored = TaskResult.model_validate_json(result.model_dump_json())

    assert restored == result


@pytest.mark.unit
@pytest.mark.task("T02")
def test_invalid_payload_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        GpuInfo.model_validate({"model": "cpu", "vram_total_mb": "not-an-int", "vram_free_mb": 0})


@pytest.mark.unit
@pytest.mark.task("T02")
def test_unknown_direction_rejected() -> None:
    with pytest.raises(ValidationError):
        SearchJobSpec(image="img", metric="m", n_trials=1, search_space={}, direction="sideways")


@pytest.mark.unit
@pytest.mark.task("T02")
def test_shard_strategy_requires_positive_n_shards_for_split_kinds() -> None:
    with pytest.raises(ValidationError):
        ShardStrategy(kind="index-range", n_shards=0)


@pytest.mark.unit
@pytest.mark.task("T02")
def test_shard_strategy_whole_ignores_n_shards() -> None:
    strategy = ShardStrategy(kind="whole", n_shards=0)

    assert strategy.kind == "whole"


@pytest.mark.unit
@pytest.mark.task("T02")
def test_map_job_spec_propagates_shard_validation() -> None:
    with pytest.raises(ValidationError):
        MapJobSpec(image="img", dataset="d/v1", shard=ShardStrategy(kind="file-list", n_shards=-1))
