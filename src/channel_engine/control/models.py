from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


CONTROL_PLANE_VERSION = "1.0"

_SENSITIVE_MARKERS = (
    "secret",
    "token",
    "password",
    "cookie",
    "authorization",
    "customer_message",
    "message_content",
    "proposed_content",
    "reply_draft",
)


def _reject_sensitive_marker(value: str) -> str:
    normalized = value.casefold()
    if any(marker in normalized for marker in _SENSITIVE_MARKERS):
        raise ValueError("control-plane metadata contains a prohibited marker")
    return value


class ControlPlaneModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    control_plane_version: Literal["1.0"] = CONTROL_PLANE_VERSION


class KillSwitchState(StrEnum):
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"


class EngineRuntimeState(StrEnum):
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    STOPPED = "STOPPED"


class ComponentHealthState(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"


class AdapterConnectionState(StrEnum):
    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"
    DISCONNECTED = "DISCONNECTED"


class WorkerRuntimeState(StrEnum):
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"


class OutboxRuntimeState(StrEnum):
    HEALTHY = "HEALTHY"
    BACKLOG = "BACKLOG"
    DEGRADED = "DEGRADED"


class ExecutionPolicyState(StrEnum):
    ENABLED = "ENABLED"
    BLOCKED = "BLOCKED"


class ControlPlaneAuditAction(StrEnum):
    KILL_SWITCH_ENABLED = "KILL_SWITCH_ENABLED"
    KILL_SWITCH_DISABLED = "KILL_SWITCH_DISABLED"
    CONFIG_SNAPSHOT_CREATED = "CONFIG_SNAPSHOT_CREATED"
    CONFIG_SNAPSHOT_ACTIVATED = "CONFIG_SNAPSHOT_ACTIVATED"
    CONFIG_SNAPSHOT_ROLLED_BACK = "CONFIG_SNAPSHOT_ROLLED_BACK"


class EngineStatus(ControlPlaneModel):
    state: EngineRuntimeState
    service: str = Field(min_length=1, max_length=128)
    environment: str = Field(min_length=1, max_length=64)
    checked_at: AwareDatetime
    reason_code: str = Field(
        min_length=3,
        max_length=128,
        pattern=r"^[A-Z][A-Z0-9_.:-]{2,127}$",
    )


class AdapterStatus(ControlPlaneModel):
    adapter_name: str = Field(min_length=1, max_length=128)
    channel: str = Field(min_length=1, max_length=80)
    connection: AdapterConnectionState
    health: ComponentHealthState
    real_platform_connected: bool
    checked_at: AwareDatetime


class ExecutionPolicyStatus(ControlPlaneModel):
    state: ExecutionPolicyState
    kill_switch: KillSwitchState
    policy_version: str | None = Field(default=None, max_length=128)
    new_execution_allowed: bool
    pending_claim_allowed: bool
    running_execution_may_finish: bool = True


class KillSwitchStatus(ControlPlaneModel):
    state: KillSwitchState
    revision: int = Field(ge=0)
    updated_at: AwareDatetime
    updated_by: str = Field(min_length=1, max_length=160)
    reason: str = Field(
        min_length=3,
        max_length=128,
        pattern=r"^[A-Z][A-Z0-9_.:-]{2,127}$",
    )

    @field_validator("updated_by", "reason")
    @classmethod
    def reject_sensitive_metadata(cls, value: str) -> str:
        return _reject_sensitive_marker(value)


class ConfigSnapshot(ControlPlaneModel):
    snapshot_id: str = Field(min_length=1, max_length=128)
    adapter_config_version: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    policy_version: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    gateway_version: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    created_at: AwareDatetime
    created_by: str = Field(min_length=1, max_length=160)
    reason: str = Field(
        min_length=3,
        max_length=128,
        pattern=r"^[A-Z][A-Z0-9_.:-]{2,127}$",
    )

    @field_validator(
        "snapshot_id",
        "adapter_config_version",
        "policy_version",
        "gateway_version",
        "created_by",
        "reason",
    )
    @classmethod
    def reject_sensitive_metadata(cls, value: str) -> str:
        return _reject_sensitive_marker(value)


class ControlPlaneAuditState(ControlPlaneModel):
    kill_switch: KillSwitchState
    state_revision: int = Field(ge=0)
    active_config_snapshot_id: str | None = Field(default=None, max_length=128)
    adapter_config_version: str | None = Field(default=None, max_length=128)
    policy_version: str | None = Field(default=None, max_length=128)
    gateway_version: str | None = Field(default=None, max_length=128)

    @field_validator(
        "active_config_snapshot_id",
        "adapter_config_version",
        "policy_version",
        "gateway_version",
    )
    @classmethod
    def reject_sensitive_versions(cls, value: str | None) -> str | None:
        return _reject_sensitive_marker(value) if value is not None else None


class ControlPlaneAuditEvent(ControlPlaneModel):
    audit_event_id: str = Field(min_length=1, max_length=128)
    operator: str = Field(
        min_length=1,
        max_length=160,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,159}$",
    )
    action: ControlPlaneAuditAction
    timestamp: AwareDatetime
    reason: str = Field(
        min_length=3,
        max_length=128,
        pattern=r"^[A-Z][A-Z0-9_.:-]{2,127}$",
    )
    subject_id: str | None = Field(default=None, max_length=128)
    before: ControlPlaneAuditState
    after: ControlPlaneAuditState

    @field_validator("operator", "reason", "subject_id")
    @classmethod
    def reject_sensitive_metadata(cls, value: str | None) -> str | None:
        return _reject_sensitive_marker(value) if value is not None else None


class GatewayStatus(ControlPlaneModel):
    health: ComponentHealthState
    reachable: bool
    gateway_version: str | None = Field(default=None, max_length=128)
    checked_at: AwareDatetime


class WorkerStatus(ControlPlaneModel):
    worker_id: str = Field(min_length=1, max_length=160)
    state: WorkerRuntimeState
    last_transition_at: AwareDatetime


class OutboxStatus(ControlPlaneModel):
    state: OutboxRuntimeState
    pending_count: int = Field(ge=0)
    processing_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    backlog_threshold: int = Field(ge=1)


class OperationalMetrics(ControlPlaneModel):
    execution_count: int = Field(ge=0)
    execution_pending: int = Field(ge=0)
    execution_running: int = Field(ge=0)
    execution_success: int = Field(ge=0)
    execution_failed: int = Field(ge=0)
    execution_unknown: int = Field(ge=0)
    execution_latency_sample_count: int = Field(ge=0)
    execution_latency_avg_ms: float = Field(ge=0)
    execution_latency_max_ms: float = Field(ge=0)
    queue_depth: int = Field(ge=0)
    adapter_healthy: int = Field(ge=0)
    adapter_degraded: int = Field(ge=0)
    adapter_disconnected: int = Field(ge=0)
    receipts_total: int = Field(ge=0)
    outbox_pending: int = Field(ge=0)
    outbox_processing: int = Field(ge=0)
    outbox_published: int = Field(ge=0)
    outbox_failed: int = Field(ge=0)
    audit_events_total: int = Field(ge=0)
    config_snapshots_total: int = Field(ge=0)


class ControlPlaneStatus(ControlPlaneModel):
    kill_switch: KillSwitchStatus
    active_config: ConfigSnapshot | None
    audit_event_count: int = Field(ge=0)
    captured_at: AwareDatetime


class ChannelEngineHealth(ControlPlaneModel):
    engine: EngineStatus
    gateway: GatewayStatus
    adapters: tuple[AdapterStatus, ...]
    worker: WorkerStatus
    outbox: OutboxStatus
    policy: ExecutionPolicyStatus
    kill_switch: KillSwitchStatus
    active_config: ConfigSnapshot | None
    metrics: OperationalMetrics
    checked_at: AwareDatetime


__all__ = [
    "AdapterConnectionState",
    "AdapterStatus",
    "ChannelEngineHealth",
    "ComponentHealthState",
    "ConfigSnapshot",
    "CONTROL_PLANE_VERSION",
    "ControlPlaneAuditAction",
    "ControlPlaneAuditEvent",
    "ControlPlaneAuditState",
    "ControlPlaneStatus",
    "EngineRuntimeState",
    "EngineStatus",
    "ExecutionPolicyState",
    "ExecutionPolicyStatus",
    "GatewayStatus",
    "KillSwitchState",
    "KillSwitchStatus",
    "OperationalMetrics",
    "OutboxRuntimeState",
    "OutboxStatus",
    "WorkerRuntimeState",
    "WorkerStatus",
]
