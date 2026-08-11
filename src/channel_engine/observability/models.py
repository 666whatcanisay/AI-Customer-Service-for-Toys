from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

from channel_engine.models.entities import new_id, utc_now


OBSERVABILITY_CONTRACT_VERSION = "1.0"


class ObservabilityModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    observability_version: Literal["1.0"] = OBSERVABILITY_CONTRACT_VERSION


class StructuredEventType(StrEnum):
    CHANNEL_CONNECTED = "CHANNEL_CONNECTED"
    MESSAGE_RECEIVED = "MESSAGE_RECEIVED"
    MESSAGE_NORMALIZED = "MESSAGE_NORMALIZED"
    SESSION_CHANGED = "SESSION_CHANGED"
    DECISION_REQUEST_SENT = "DECISION_REQUEST_SENT"
    DECISION_CREATED = "DECISION_CREATED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVAL_GRANTED = "APPROVAL_GRANTED"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    EXECUTION_STARTED = "EXECUTION_STARTED"
    EXECUTION_SUCCESS = "EXECUTION_SUCCESS"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    EXECUTION_UNKNOWN = "EXECUTION_UNKNOWN"
    RECEIPT_CREATED = "RECEIPT_CREATED"
    RECOVERY_STARTED = "RECOVERY_STARTED"
    RECOVERY_COMPLETED = "RECOVERY_COMPLETED"
    RECOVERY_MANUAL_INTERVENTION = "RECOVERY_MANUAL_INTERVENTION"


class StructuredEventStatus(StrEnum):
    INFO = "INFO"
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    BLOCKED = "BLOCKED"


_SENSITIVE_KEYS = (
    "cookie",
    "token",
    "password",
    "secret",
    "authorization",
    "customer_message",
    "content",
    "message_text",
    "proposed_content",
    "answer",
    "sender",
    "payload",
)
_SENSITIVE_VALUE_MARKERS = (
    "bearer ",
    "cookie=",
    "set-cookie",
    "password=",
    "secret=",
    "token=",
)


def metadata_is_safe(value: object, *, depth: int = 0) -> bool:
    if depth > 6:
        return False
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).casefold()
            aggregate_only = normalized.endswith(("_length", "_count", "_size"))
            if not aggregate_only and any(
                marker in normalized for marker in _SENSITIVE_KEYS
            ):
                return False
            if not metadata_is_safe(item, depth=depth + 1):
                return False
        return True
    if isinstance(value, (list, tuple)):
        return len(value) <= 100 and all(
            metadata_is_safe(item, depth=depth + 1) for item in value
        )
    if isinstance(value, str):
        normalized = value.casefold()
        return len(value) <= 512 and not any(
            marker in normalized for marker in _SENSITIVE_VALUE_MARKERS
        )
    return value is None or isinstance(value, (bool, int, float))


class StructuredEvent(ObservabilityModel):
    event_id: str = Field(default_factory=lambda: new_id("ops-event"), max_length=128)
    event_type: StructuredEventType
    trace_id: str = Field(min_length=1, max_length=128)
    message_id: str | None = Field(default=None, max_length=128)
    conversation_id: str | None = Field(default=None, max_length=128)
    request_id: str | None = Field(default=None, max_length=160)
    decision_id: str | None = Field(default=None, max_length=128)
    approval_id: str | None = Field(default=None, max_length=128)
    execution_id: str | None = Field(default=None, max_length=128)
    receipt_id: str | None = Field(default=None, max_length=128)
    store_id: str | None = Field(default=None, max_length=128)
    timestamp: AwareDatetime = Field(default_factory=utc_now)
    status: StructuredEventStatus
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def reject_sensitive_metadata(
        cls, value: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        if not metadata_is_safe(value):
            raise ValueError("observability metadata contains sensitive material")
        return value


class StructuredEventPage(ObservabilityModel):
    items: tuple[StructuredEvent, ...]
    count: int = Field(ge=0)
    limit: int = Field(ge=1, le=500)
    newest_first: bool


class TraceStopReason(StrEnum):
    RECEIVING = "RECEIVING"
    REQUESTING_DECISION = "REQUESTING_DECISION"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    EXECUTION_PENDING = "EXECUTION_PENDING"
    EXECUTION_RUNNING = "EXECUTION_RUNNING"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    EXECUTION_UNKNOWN = "EXECUTION_UNKNOWN"
    COMPLETED = "COMPLETED"
    RECOVERY = "RECOVERY"
    MANUAL_INTERVENTION = "MANUAL_INTERVENTION"


class WorkflowTrace(ObservabilityModel):
    trace_id: str
    message_id: str | None = None
    conversation_id: str | None = None
    request_id: str | None = None
    decision_id: str | None = None
    approval_id: str | None = None
    execution_id: str | None = None
    receipt_id: str | None = None
    store_id: str | None = None
    current_step: str
    why_stopped: TraceStopReason
    next_step: str
    events: tuple[StructuredEvent, ...]
    started_at: AwareDatetime
    updated_at: AwareDatetime


class ApprovalMonitorState(StrEnum):
    WAITING = "WAITING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ApprovalMonitorItem(ObservabilityModel):
    decision_id: str
    conversation_id: str
    message_id: str
    approval_id: str | None = None
    store_id: str | None = None
    state: ApprovalMonitorState
    requires_approval: bool
    waiting_since: AwareDatetime
    decided_at: AwareDatetime | None = None
    decided_by: str | None = Field(default=None, max_length=160)
    action: str


class ApprovalReviewDetail(ObservabilityModel):
    """Business-facing, read-only material required for a human review."""

    decision_id: str
    conversation_id: str
    message_id: str
    customer_question: str = Field(min_length=1, max_length=8_000)
    ai_suggestion: str | None = Field(default=None, max_length=8_000)
    knowledge_sources: tuple[str, ...] = ()
    knowledge_source_status: Literal["AVAILABLE", "NOT_PROVIDED"]
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "UNSPECIFIED"]
    risk_basis: str = Field(min_length=1, max_length=500)
    state: str
    action: str
    requires_approval: bool
    gateway_version: str
    next_step: str = Field(min_length=1, max_length=500)


class ExecutionLedgerItem(ObservabilityModel):
    execution_id: str
    decision_id: str
    approval_id: str
    trace_id: str | None = None
    state: str
    attempt: int = Field(ge=0)
    error_code: str | None = None
    receipt_id: str | None = None
    receipt_outcome: str | None = None
    created_at: AwareDatetime
    started_at: AwareDatetime | None = None
    completed_at: AwareDatetime | None = None
    recorded_at: AwareDatetime | None = None
    automatic_retry_allowed: bool
    next_step: str


class RecoveryRecordState(StrEnum):
    RECOVERING = "RECOVERING"
    RECOVERED = "RECOVERED"
    UNKNOWN = "UNKNOWN"
    MANUAL_INTERVENTION = "MANUAL_INTERVENTION"


class RecoveryRecord(ObservabilityModel):
    recovery_id: str
    component: str
    state: RecoveryRecordState
    attempts: int = Field(ge=1)
    reason_code: str
    execution_id: str | None = None
    started_at: AwareDatetime
    completed_at: AwareDatetime | None = None
    requires_manual_action: bool
    next_step: str


class OpsApprovalAction(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


class OpsApprovalCommand(ObservabilityModel):
    operator: str = Field(
        min_length=1,
        max_length=160,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,159}$",
    )
    confirmation_text: str = Field(min_length=8, max_length=180)
    acknowledgement: Literal[
        "HUMAN_ACTION_REVIEWED_NO_AUTOMATIC_EXECUTION"
    ]
    reason: str | None = Field(default=None, max_length=500)


class OpsApprovalActionResult(ObservabilityModel):
    action: OpsApprovalAction
    decision_id: str
    approval_id: str
    execution_id: str | None = None
    decision_state: str
    execution_state: str | None = None
    automatic_execution_started: Literal[False] = False
    real_send_triggered: Literal[False] = False
    next_step: str


class OpsAgentAdminCommand(ObservabilityModel):
    """Explicit local-host confirmation for a destructive device action."""

    reason: str = Field(min_length=8, max_length=512)
    confirmation_text: Literal[
        "确认解绑设备",
        "确认禁用设备",
        "确认恢复为待绑定",
    ]


class OpsComponentStatus(ObservabilityModel):
    component: str
    status: str
    reason_code: str


class OpsRuntimeStatus(ObservabilityModel):
    overall: str
    runtime: OpsComponentStatus
    channel: OpsComponentStatus
    browser: OpsComponentStatus
    gateway: OpsComponentStatus
    storage: OpsComponentStatus
    worker: OpsComponentStatus
    outbox: OpsComponentStatus
    policy: OpsComponentStatus
    pending_approvals: int = Field(ge=0)
    execution_queue_depth: int = Field(ge=0)
    execution_unknown: int = Field(ge=0)
    event_count: int = Field(ge=0)
    latest_event_at: AwareDatetime | None = None
    checked_at: AwareDatetime


class OpsConsoleSnapshot(ObservabilityModel):
    runtime: OpsRuntimeStatus
    recent_events: tuple[StructuredEvent, ...]
    pending_approvals: tuple[ApprovalMonitorItem, ...]
    recent_executions: tuple[ExecutionLedgerItem, ...]
    generated_at: AwareDatetime


__all__ = [
    "ApprovalMonitorItem",
    "ApprovalReviewDetail",
    "ApprovalMonitorState",
    "ExecutionLedgerItem",
    "OBSERVABILITY_CONTRACT_VERSION",
    "ObservabilityModel",
    "OpsComponentStatus",
    "OpsApprovalAction",
    "OpsApprovalActionResult",
    "OpsApprovalCommand",
    "OpsAgentAdminCommand",
    "OpsConsoleSnapshot",
    "OpsRuntimeStatus",
    "RecoveryRecord",
    "RecoveryRecordState",
    "StructuredEvent",
    "StructuredEventPage",
    "StructuredEventStatus",
    "StructuredEventType",
    "TraceStopReason",
    "WorkflowTrace",
    "metadata_is_safe",
]
