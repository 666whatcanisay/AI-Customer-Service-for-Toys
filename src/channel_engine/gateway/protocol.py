from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from channel_engine.models.entities import new_id, utc_now
from channel_engine.models.enums import DecisionAction, EventType, ReceiptOutcome


class GatewayModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DecisionRequest(GatewayModel):
    request_id: str = Field(default_factory=lambda: new_id("gateway-request"))
    conversation_id: str
    message_id: str
    customer_message: str = Field(min_length=1, max_length=8_000)
    context: dict[str, Any] = Field(default_factory=dict)
    requested_at: datetime = Field(default_factory=utc_now)


class DecisionResponse(GatewayModel):
    decision_id: str = Field(default_factory=lambda: new_id("decision"))
    action: DecisionAction
    proposed_content: str | None = None
    requires_approval: bool = True
    gateway_version: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionReceipt(GatewayModel):
    receipt_id: str = Field(default_factory=lambda: new_id("gateway-receipt"))
    execution_id: str
    outcome: ReceiptOutcome
    external_reference: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    recorded_at: datetime = Field(default_factory=utc_now)


class Event(GatewayModel):
    event_id: str = Field(default_factory=lambda: new_id("gateway-event"))
    event_type: EventType
    aggregate_type: str
    aggregate_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=utc_now)


class AICSGateway(Protocol):
    def decide(self, request: DecisionRequest) -> DecisionResponse:
        """Return a decision proposal without executing channel actions."""


class GatewayUnavailable(RuntimeError):
    pass
