from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, Field

from .control_v2 import ControlV2Model
from .edge_execution import EdgeExecutionReceipt
from .execution_authorization import ExecutionAuthorization


class AgentCommandEnvelope(ControlV2Model):
    """Execution-only control model, excluded from OBSERVE_ONLY packages."""

    command_id: str = Field(min_length=1, max_length=160)
    command_type: Literal["SEND_MESSAGE"]
    agent_id: str = Field(min_length=1, max_length=128)
    device_id: str = Field(min_length=1, max_length=128)
    store_id: str = Field(min_length=1, max_length=160)
    execution_authorization: ExecutionAuthorization
    reply_text: str = Field(min_length=1, max_length=8_000, repr=False)
    issued_at: AwareDatetime
    expires_at: AwareDatetime


class AgentCommandPollResponse(ControlV2Model):
    command: AgentCommandEnvelope | None
    server_time: AwareDatetime


class AgentReceiptSubmission(ControlV2Model):
    agent_id: str = Field(min_length=1, max_length=128)
    device_id: str = Field(min_length=1, max_length=128)
    receipt: EdgeExecutionReceipt
    submitted_at: AwareDatetime


class AgentReceiptAck(ControlV2Model):
    receipt_id: str
    status: Literal["PERSISTED", "DUPLICATE"]
    persisted_at: AwareDatetime


class ServiceApprovalDelivery(ControlV2Model):
    approval_delivery_id: str = Field(min_length=1, max_length=160)
    agent_id: str = Field(min_length=1, max_length=128)
    device_id: str = Field(min_length=1, max_length=128)
    store_id: str = Field(min_length=1, max_length=160)
    conversation_id: str = Field(min_length=1, max_length=255)
    customer_reference: str = Field(min_length=1, max_length=255)
    message_id: str = Field(min_length=1, max_length=255)
    decision_id: str = Field(min_length=1, max_length=128)
    approval_id: str = Field(min_length=1, max_length=128)
    operator_reference: str = Field(min_length=1, max_length=160)
    reply_text: str = Field(min_length=1, max_length=8_000, repr=False)
    policy_version: str = Field(min_length=1, max_length=128)
    selector_evidence_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    activation_grant_id: str = Field(min_length=1, max_length=160)
    approved_at: datetime


class ServiceApprovalAck(ControlV2Model):
    approval_delivery_id: str
    command_id: str
    execution_id: str
    status: Literal["QUEUED", "DUPLICATE"]
    queued_at: AwareDatetime


__all__ = [
    "AgentCommandEnvelope",
    "AgentCommandPollResponse",
    "AgentReceiptAck",
    "AgentReceiptSubmission",
    "ServiceApprovalAck",
    "ServiceApprovalDelivery",
]
