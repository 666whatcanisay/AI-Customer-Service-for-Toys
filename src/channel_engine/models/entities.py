from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .enums import (
    ApprovalState,
    ConversationStatus,
    DecisionAction,
    DecisionState,
    EventType,
    ExecutionState,
    MessageRole,
    MessageState,
    ReceiptOutcome,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


class DomainModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Conversation(DomainModel):
    conversation_id: str = Field(default_factory=lambda: new_id("conv"))
    channel_name: str
    external_ref: str
    status: ConversationStatus = ConversationStatus.OPEN
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Message(DomainModel):
    message_id: str = Field(default_factory=lambda: new_id("msg"))
    conversation_id: str
    external_message_id: str
    role: MessageRole = MessageRole.CUSTOMER
    content: str = Field(min_length=1, max_length=8_000)
    state: MessageState = MessageState.RECEIVED
    received_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Decision(DomainModel):
    decision_id: str = Field(default_factory=lambda: new_id("decision"))
    conversation_id: str
    message_id: str
    action: DecisionAction
    proposed_content: str | None = None
    requires_approval: bool = True
    state: DecisionState = DecisionState.CREATED
    gateway_version: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Approval(DomainModel):
    approval_id: str = Field(default_factory=lambda: new_id("approval"))
    decision_id: str
    state: ApprovalState = ApprovalState.PENDING
    decided_by: str | None = None
    reason: str | None = None
    decided_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)


class Execution(DomainModel):
    execution_id: str = Field(default_factory=lambda: new_id("execution"))
    decision_id: str
    approval_id: str
    state: ExecutionState = ExecutionState.PENDING
    idempotency_key: str
    attempt: int = Field(default=1, ge=1)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_code: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Receipt(DomainModel):
    receipt_id: str = Field(default_factory=lambda: new_id("receipt"))
    execution_id: str
    outcome: ReceiptOutcome
    external_reference: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    recorded_at: datetime = Field(default_factory=utc_now)


class Event(DomainModel):
    event_id: str = Field(default_factory=lambda: new_id("event"))
    aggregate_type: str
    aggregate_id: str
    event_type: EventType
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str
    occurred_at: datetime = Field(default_factory=utc_now)
