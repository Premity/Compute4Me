"""T04 acceptance: each WS message round-trips, unknown `type` is rejected, join carries a profile.

Messages are validated through the direction-keyed discriminated unions
(`parse_worker_message` / `parse_master_message`), mirroring how the control channel
decodes inbound JSON.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from compute4me.proto.messages import (
    BandwidthProbe,
    Heartbeat,
    Join,
    JoinAck,
    JoinReject,
    ProfileUpdate,
    TaskAssign,
    TaskCancel,
    TaskProgress,
    TaskResultMsg,
    parse_master_message,
    parse_worker_message,
)
from compute4me.types import ArtifactRef, CapabilityProfile, GpuInfo, TaskRequires


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


def _worker_messages() -> list[object]:
    return [
        Join(token="eyJ...", profile=_profile()),
        Heartbeat(worker_id="w1", task_id="t1", throughput_sample=410.0),
        Heartbeat(worker_id="w1"),
        TaskProgress(task_id="t1", fields={"epoch": 3, "loss": 0.42}),
        TaskResultMsg(task_id="t1", status="succeeded", metrics={"val_auc": 0.91}),
        TaskResultMsg(task_id="t1", status="failed", error="non-finite metric"),
        ProfileUpdate(worker_id="w1", profile=_profile()),
    ]


def _master_messages() -> list[object]:
    return [
        JoinAck(worker_id="w1"),
        JoinReject(reason="token revoked"),
        TaskAssign(
            task_id="t1",
            code_ref="ghcr.io/hamda/spacesight-train:latest",
            args={"lr": 0.01},
            input_refs=[ArtifactRef(hash="h1")],
            requires=TaskRequires(min_vram_mb=4096, gpu_required=True, est_work_units=1000.0),
        ),
        TaskCancel(task_id="t1"),
        BandwidthProbe(),
    ]


@pytest.mark.unit
@pytest.mark.task("T04")
@pytest.mark.parametrize("msg", _worker_messages())
def test_worker_message_round_trips(msg: object) -> None:
    restored = parse_worker_message(msg.model_dump())  # type: ignore[attr-defined]

    assert restored == msg


@pytest.mark.unit
@pytest.mark.task("T04")
@pytest.mark.parametrize("msg", _master_messages())
def test_master_message_round_trips(msg: object) -> None:
    restored = parse_master_message(msg.model_dump())  # type: ignore[attr-defined]

    assert restored == msg


@pytest.mark.unit
@pytest.mark.task("T04")
def test_join_carries_full_capability_profile() -> None:
    join = Join(token="eyJ...", profile=_profile())

    restored = parse_worker_message(join.model_dump())

    assert isinstance(restored, Join)
    assert restored.profile == _profile()


@pytest.mark.unit
@pytest.mark.task("T04")
def test_unknown_worker_type_rejected() -> None:
    with pytest.raises(ValidationError):
        parse_worker_message({"type": "not_a_real_message", "worker_id": "w1"})


@pytest.mark.unit
@pytest.mark.task("T04")
def test_unknown_master_type_rejected() -> None:
    with pytest.raises(ValidationError):
        parse_master_message({"type": "definitely_not", "task_id": "t1"})


@pytest.mark.unit
@pytest.mark.task("T04")
def test_wrong_direction_type_rejected() -> None:
    # A Master-only type must not validate as a Worker message, and vice versa.
    with pytest.raises(ValidationError):
        parse_worker_message(JoinAck(worker_id="w1").model_dump())
    with pytest.raises(ValidationError):
        parse_master_message(Heartbeat(worker_id="w1").model_dump())


@pytest.mark.unit
@pytest.mark.task("T04")
def test_missing_type_rejected() -> None:
    with pytest.raises(ValidationError):
        parse_worker_message({"worker_id": "w1"})


@pytest.mark.unit
@pytest.mark.task("T04")
def test_unknown_fields_ignored_for_additive_evolution() -> None:
    # wire-protocol.md §Versioning: a reader tolerates unknown *fields* (newer sender).
    restored = parse_worker_message(
        {"type": "heartbeat", "worker_id": "w1", "some_future_field": 123}
    )

    assert isinstance(restored, Heartbeat)
    assert restored.worker_id == "w1"
