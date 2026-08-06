from __future__ import annotations

from datetime import timedelta
from typing import Literal, Protocol, runtime_checkable

from pydantic import AwareDatetime, Field, model_validator

from .lifecycle import ChannelSession
from .protocol import (
    AdapterHealth,
    ChannelModel,
    ChannelSendReceipt,
    NormalizedMessage,
    OutboundMessage,
)


class ExecutionSendAuthorization(ChannelModel):
    """Short-lived fencing evidence derived from the authoritative ledger."""

    authorization_id: str = Field(min_length=1, max_length=128)
    decision_id: str = Field(min_length=1, max_length=128)
    approval_id: str = Field(min_length=1, max_length=128)
    execution_id: str = Field(min_length=1, max_length=128)
    operation: Literal["SEND_MESSAGE"] = "SEND_MESSAGE"
    execution_risk: Literal["LOW"] = "LOW"
    approved_by: str = Field(min_length=1, max_length=160)
    worker_id: str = Field(min_length=1, max_length=160)
    execution_lease_token: str = Field(min_length=1, max_length=128, repr=False)
    issued_at: AwareDatetime
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def validate_window(self) -> ExecutionSendAuthorization:
        if self.expires_at <= self.issued_at:
            raise ValueError("send authorization expiry must follow issue time")
        if self.expires_at - self.issued_at > timedelta(minutes=5):
            raise ValueError("send authorization lifetime cannot exceed five minutes")
        return self


class AuthorizedOutboundMessage(ChannelModel):
    message: OutboundMessage
    authorization: ExecutionSendAuthorization

    @model_validator(mode="after")
    def validate_execution_identity(self) -> AuthorizedOutboundMessage:
        if self.message.execution_id != self.authorization.execution_id:
            raise ValueError("outbound execution does not match authorization")
        if self.message.approved_by != self.authorization.approved_by:
            raise ValueError("outbound approver does not match authorization")
        return self


class ExecutionBoundaryDenied(PermissionError):
    pass


@runtime_checkable
class SendAuthorizationVerifier(Protocol):
    def verify(self, command: AuthorizedOutboundMessage) -> None:
        """Fail closed unless Decision, Approval, Execution and lease are current."""


@runtime_checkable
class PlatformAdapter(Protocol):
    @property
    def channel(self) -> str:
        """Stable platform registry key."""

    def receive_message(self) -> NormalizedMessage | None:
        """Receive one external message as a normalized six-field message."""

    def send_message(
        self,
        command: AuthorizedOutboundMessage,
    ) -> ChannelSendReceipt:
        """Execute only a ledger-authorized, lease-fenced send command."""

    def health_check(self) -> AdapterHealth:
        """Return connection, session and authentication health."""

    def get_session(self) -> ChannelSession | None:
        """Return sanitized session metadata without platform credentials."""


__all__ = [
    "AuthorizedOutboundMessage",
    "ExecutionBoundaryDenied",
    "ExecutionSendAuthorization",
    "PlatformAdapter",
    "SendAuthorizationVerifier",
]
