from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from channel_engine.channel import AdapterHealthStatus, ChannelMessageV1
from channel_engine.reliability import ComponentHealth


CHANNEL_SESSION_RUNTIME_VERSION = "1.0"


class SessionRuntimeModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    session_runtime_version: Literal["1.0"] = CHANNEL_SESSION_RUNTIME_VERSION


class ChannelInstanceStatus(StrEnum):
    CREATED = "CREATED"
    STARTING = "STARTING"
    CONNECTED = "CONNECTED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    DEGRADED = "DEGRADED"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


class ChannelSessionStatus(StrEnum):
    CREATED = "CREATED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    CONNECTED = "CONNECTED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


class InboxMessageState(StrEnum):
    PERSISTED = "PERSISTED"
    ACKED = "ACKED"
    MANUAL_INTERVENTION = "MANUAL_INTERVENTION"


class CredentialReference(SessionRuntimeModel):
    credential_ref: str = Field(
        min_length=5,
        max_length=255,
        pattern=r"^[a-z][a-z0-9+.-]*://[^\s\r\n]+$",
        repr=False,
    )
    provider: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9._-]{0,63}$",
    )
    version: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$",
    )

    @field_validator("credential_ref")
    @classmethod
    def reject_embedded_secret(cls, value: str) -> str:
        normalized = value.casefold()
        prohibited = (
            "cookie=",
            "token=",
            "password=",
            "passwd=",
            "secret=",
            "authorization:",
            "bearer ",
            "bearer%20",
        )
        if any(marker in normalized for marker in prohibited):
            raise ValueError("credential_ref contains prohibited secret material")
        authority = value.split("://", 1)[1].split("/", 1)[0]
        if "@" in authority or ":" in authority:
            raise ValueError("credential_ref cannot contain URI userinfo")
        return value


class CredentialLease(SessionRuntimeModel):
    credential_ref: CredentialReference
    lease_ref: str = Field(min_length=5, max_length=255)
    acquired_at: AwareDatetime
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def validate_expiry(self) -> CredentialLease:
        if self.expires_at <= self.acquired_at:
            raise ValueError("credential lease expiry must follow acquisition")
        return self


class ChannelInstance(SessionRuntimeModel):
    instance_id: str = Field(min_length=1, max_length=128)
    platform: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9][a-z0-9._-]{0,79}$",
    )
    store_id: str = Field(min_length=1, max_length=128)
    status: ChannelInstanceStatus
    adapter_type: str = Field(min_length=1, max_length=128)
    active_session_id: str | None = Field(default=None, max_length=128)
    failure_code: str | None = Field(default=None, max_length=128)
    created_at: datetime
    updated_at: datetime


class ChannelSession(SessionRuntimeModel):
    session_id: str = Field(min_length=1, max_length=128)
    instance_id: str = Field(min_length=1, max_length=128)
    status: ChannelSessionStatus
    credential_ref: CredentialReference
    credential_lease_ref: str | None = Field(default=None, max_length=255)
    heartbeat_time: datetime | None = None
    expires_at: datetime | None = None
    failure_code: str | None = Field(default=None, max_length=128)
    created_at: datetime
    updated_at: datetime


class ChannelInstanceView(SessionRuntimeModel):
    instance: ChannelInstance
    session: ChannelSession | None
    adapter_health: AdapterHealthStatus
    real_platform_connected: bool = False
    checked_at: datetime


class MessageCursor(SessionRuntimeModel):
    instance_id: str
    cursor_value: str | None = None
    last_sequence: int = Field(ge=0)
    last_acked_sequence: int = Field(ge=0)
    revision: int = Field(ge=0)
    updated_at: datetime


class InboundEnvelope(SessionRuntimeModel):
    message: ChannelMessageV1
    source_cursor: str = Field(min_length=1, max_length=512)
    source_sequence: int = Field(ge=1)


class PersistedMessage(SessionRuntimeModel):
    instance_id: str
    delivery_id: str
    message: ChannelMessageV1
    source_cursor: str
    source_sequence: int = Field(ge=1)
    state: InboxMessageState
    persisted_at: datetime
    duplicate: bool = False


class RetryMarker(SessionRuntimeModel):
    delivery_id: str
    attempt: int = Field(ge=1)
    reason_code: str = Field(min_length=3, max_length=128)
    retry_after: datetime


class MessageDelivery(SessionRuntimeModel):
    instance_id: str
    delivery_id: str
    message: ChannelMessageV1
    source_cursor: str
    source_sequence: int = Field(ge=1)
    delivery_attempt: int = Field(ge=1)
    retry_marker: RetryMarker | None = None


class MessageAck(SessionRuntimeModel):
    ack_id: str
    instance_id: str
    delivery_id: str
    message_id: str
    source_sequence: int = Field(ge=1)
    acknowledged_at: datetime
    duplicate: bool = False


class SessionHeartbeat(SessionRuntimeModel):
    heartbeat_id: str
    cycle_id: str
    instance_id: str
    session_id: str | None
    session_status: ChannelSessionStatus | None
    adapter_health: AdapterHealthStatus
    browser_health: ComponentHealth
    gateway_health: ComponentHealth
    overall: ComponentHealth
    reason_code: str
    checked_at: datetime


class SessionHeartbeatReport(SessionRuntimeModel):
    cycle_id: str
    instances: tuple[SessionHeartbeat, ...]
    overall: ComponentHealth
    checked_at: datetime


__all__ = [
    "CHANNEL_SESSION_RUNTIME_VERSION",
    "ChannelInstance",
    "ChannelInstanceStatus",
    "ChannelInstanceView",
    "ChannelSession",
    "ChannelSessionStatus",
    "CredentialLease",
    "CredentialReference",
    "InboxMessageState",
    "InboundEnvelope",
    "MessageAck",
    "MessageCursor",
    "MessageDelivery",
    "PersistedMessage",
    "RetryMarker",
    "SessionHeartbeat",
    "SessionHeartbeatReport",
]
