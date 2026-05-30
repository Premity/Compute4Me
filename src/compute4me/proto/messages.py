"""Pydantic models for every WebSocket control-channel message.

Defines the Worker-to-Master and Master-to-Worker messages from
docs/architecture/wire-protocol.md §2 as a discriminated union on ``type``. Unknown
message types are tolerated for additive forward-compatibility (wire-protocol.md
§Versioning).

Each message is a Pydantic model with a ``Literal`` ``type`` tag; the two directions are
modelled as discriminated unions (``WorkerMessage``, ``MasterMessage``) keyed on that tag.
``parse_worker_message`` / ``parse_master_message`` validate an incoming JSON object and
raise ``ValidationError`` on an unknown ``type``. Per wire-protocol.md §Versioning, unknown
*fields* are ignored (additive evolution) while an unknown *discriminator* is rejected: a
Worker only ever sends a type the Master can name, and vice versa.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

from compute4me.types import (
    ArtifactRef,
    CapabilityProfile,
    TaskRequires,
)

# Free-form forwarded payloads: a Task's sampled args and a progress line's fields are
# user-defined JSON objects Compute4Me passes through opaquely (cf. types.JsonObject).
JsonObject = dict[str, Any]


# --- Worker to Master -------------------------------------------------------


class Join(BaseModel):
    """Sent on connect: the Invite Token plus the Worker's full Capability Profile."""

    type: Literal["join"] = "join"
    token: str
    profile: CapabilityProfile


class Heartbeat(BaseModel):
    """Liveness ping every 10s; optionally carries the in-flight Task and a throughput sample."""

    type: Literal["heartbeat"] = "heartbeat"
    worker_id: str
    task_id: str | None = None
    throughput_sample: float | None = None


class TaskProgress(BaseModel):
    """One line from the user container's ``progress.jsonl``, forwarded verbatim."""

    type: Literal["task_progress"] = "task_progress"
    task_id: str
    fields: JsonObject


class TaskResultMsg(BaseModel):
    """Reported on Task completion. Mirrors types.TaskResult's outcome fields."""

    type: Literal["task_result"] = "task_result"
    task_id: str
    status: Literal["succeeded", "failed"]
    metrics: JsonObject | None = None
    output_refs: list[str] | None = None
    error: str | None = None


class ProfileUpdate(BaseModel):
    """Periodic (~10 min) refresh of the Worker's Capability Profile."""

    type: Literal["profile_update"] = "profile_update"
    worker_id: str
    profile: CapabilityProfile


# --- Master to Worker -------------------------------------------------------


class JoinAck(BaseModel):
    """Token verified and capacity available: the Worker is admitted with an assigned id."""

    type: Literal["join_ack"] = "join_ack"
    worker_id: str


class JoinReject(BaseModel):
    """Join refused: bad/expired/revoked token, max_workers exceeded, or fingerprint mismatch."""

    type: Literal["join_reject"] = "join_reject"
    reason: str


class TaskAssign(BaseModel):
    """The Scheduler matched this Worker to a Task.

    ``code_ref`` is the user image / code reference the runner pulls (wire-protocol.md §2);
    ``args``/``input_refs``/``requires`` are the same fields the durable Task carries.
    """

    type: Literal["task_assign"] = "task_assign"
    task_id: str
    code_ref: str
    args: JsonObject
    input_refs: list[ArtifactRef]
    requires: TaskRequires


class TaskCancel(BaseModel):
    """User cancellation; the runner sends SIGTERM (30s) then SIGKILL."""

    type: Literal["task_cancel"] = "task_cancel"
    task_id: str


class BandwidthProbe(BaseModel):
    """Master-initiated probe to measure throughput/RTT for the Capability Profile."""

    type: Literal["bandwidth_probe"] = "bandwidth_probe"


# --- Discriminated unions + parse helpers ----------------------------------

WorkerMessage = Annotated[
    Join | Heartbeat | TaskProgress | TaskResultMsg | ProfileUpdate,
    Field(discriminator="type"),
]
"""Any message a Worker sends to the Master, discriminated on ``type``."""

MasterMessage = Annotated[
    JoinAck | JoinReject | TaskAssign | TaskCancel | BandwidthProbe,
    Field(discriminator="type"),
]
"""Any message the Master sends to a Worker, discriminated on ``type``."""

_worker_adapter: TypeAdapter[Any] = TypeAdapter(WorkerMessage)
_master_adapter: TypeAdapter[Any] = TypeAdapter(MasterMessage)


def parse_worker_message(data: JsonObject) -> Any:
    """Validate a Worker->Master message. Raises ``ValidationError`` on unknown ``type``."""
    return _worker_adapter.validate_python(data)


def parse_master_message(data: JsonObject) -> Any:
    """Validate a Master->Worker message. Raises ``ValidationError`` on unknown ``type``."""
    return _master_adapter.validate_python(data)
