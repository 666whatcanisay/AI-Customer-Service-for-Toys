from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


RUNTIME_RELIABILITY_VERSION = "1.0"


class ReliabilityModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reliability_version: Literal["1.0"] = RUNTIME_RELIABILITY_VERSION


class RuntimeLifecycleState(StrEnum):
    STARTING = "STARTING"
    READY = "READY"
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


class RecoveryState(StrEnum):
    RECOVERING = "RECOVERING"
    RECOVERED = "RECOVERED"
    MANUAL_INTERVENTION = "MANUAL_INTERVENTION"


class RuntimeComponent(StrEnum):
    CHANNEL = "CHANNEL"
    BROWSER = "BROWSER"
    GATEWAY = "GATEWAY"
    STORAGE = "STORAGE"


class ComponentHealth(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"


class BrowserRuntimeState(StrEnum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


class RuntimeLifecycleSnapshot(ReliabilityModel):
    runtime_id: str = Field(min_length=1, max_length=128)
    state: RuntimeLifecycleState
    generation: int = Field(ge=0)
    revision: int = Field(ge=0)
    reason_code: str = Field(min_length=3, max_length=128)
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    updated_at: datetime


class LifecycleEvent(ReliabilityModel):
    event_id: str
    runtime_id: str
    from_state: RuntimeLifecycleState | None
    to_state: RuntimeLifecycleState
    generation: int = Field(ge=0)
    reason_code: str
    occurred_at: datetime


class ComponentHeartbeat(ReliabilityModel):
    heartbeat_id: str
    runtime_id: str
    cycle_id: str
    component: RuntimeComponent
    health: ComponentHealth
    available: bool
    process_running: bool | None = None
    page_available: bool | None = None
    reason_code: str
    latency_ms: float = Field(ge=0)
    checked_at: datetime


class ProbeReading(ReliabilityModel):
    health: ComponentHealth
    available: bool
    reason_code: str
    process_running: bool | None = None
    page_available: bool | None = None


class HeartbeatReport(ReliabilityModel):
    runtime_id: str
    cycle_id: str
    overall: ComponentHealth
    components: tuple[ComponentHeartbeat, ...]
    checked_at: datetime

    def for_component(self, component: RuntimeComponent) -> ComponentHeartbeat:
        for item in self.components:
            if item.component is component:
                return item
        raise KeyError(component.value)


class RecoveryEvent(ReliabilityModel):
    recovery_event_id: str
    recovery_id: str
    runtime_id: str
    component: RuntimeComponent
    attempt: int = Field(ge=1)
    state: RecoveryState
    reason_code: str
    occurred_at: datetime


class RecoveryResult(ReliabilityModel):
    recovery_id: str
    component: RuntimeComponent
    state: RecoveryState
    attempts: int = Field(ge=1)
    events: tuple[RecoveryEvent, ...]


class BrowserHealth(ReliabilityModel):
    state: BrowserRuntimeState
    health: ComponentHealth
    process_running: bool
    page_available: bool
    real_browser_connected: bool = False
    reason_code: str
    checked_at: datetime


class ExecutionRuntimeStatus(ReliabilityModel):
    total: int = Field(ge=0)
    pending: int = Field(ge=0)
    running: int = Field(ge=0)
    success: int = Field(ge=0)
    failed: int = Field(ge=0)
    unknown: int = Field(ge=0)
    terminal_without_receipt: int = Field(ge=0)
    unapproved_active: int = Field(ge=0)
    approval_required: bool = True
    receipt_required: bool = True
    unknown_auto_retry_allowed: bool = False


class ApprovalRuntimeStatus(ReliabilityModel):
    waiting: int = Field(ge=0)
    approved: int = Field(ge=0)
    rejected: int = Field(ge=0)
    execution_without_approval_allowed: bool = False


class RuntimeDashboardStatus(ReliabilityModel):
    runtime: RuntimeLifecycleSnapshot
    channel: ComponentHeartbeat
    browser: ComponentHeartbeat
    gateway: ComponentHeartbeat
    storage: ComponentHeartbeat
    execution: ExecutionRuntimeStatus
    approval: ApprovalRuntimeStatus
    recovery: RecoveryEvent | None
    health: ComponentHealth
    checked_at: datetime


__all__ = [
    "ApprovalRuntimeStatus",
    "BrowserHealth",
    "BrowserRuntimeState",
    "ComponentHealth",
    "ComponentHeartbeat",
    "ExecutionRuntimeStatus",
    "HeartbeatReport",
    "LifecycleEvent",
    "ProbeReading",
    "RecoveryEvent",
    "RecoveryResult",
    "RecoveryState",
    "RUNTIME_RELIABILITY_VERSION",
    "RuntimeComponent",
    "RuntimeDashboardStatus",
    "RuntimeLifecycleSnapshot",
    "RuntimeLifecycleState",
]
