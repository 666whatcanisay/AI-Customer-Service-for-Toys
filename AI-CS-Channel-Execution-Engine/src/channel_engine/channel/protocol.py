from __future__ import annotations

import json
import hashlib
from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import (
    AliasChoices,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from channel_engine.models.entities import utc_now
from channel_engine.models.enums import ReceiptOutcome


class ChannelModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)


def store_scoped_conversation_ref(store_id: str, conversation_id: str) -> str:
    """Create a bounded, collision-resistant key for a store-local id."""

    encoded = json.dumps(
        [store_id, conversation_id],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return "store-scope:" + hashlib.sha256(encoded).hexdigest()


class NormalizedMessage(ChannelModel):
    """Platform-neutral inbound message consumed by Conversation Runtime."""

    channel: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9][a-z0-9._-]{0,79}$",
        validation_alias=AliasChoices("channel", "channel_name"),
    )
    # Runtime-only isolation key.  It is excluded from the legacy wire shape so
    # adding multi-store routing does not drift the frozen gateway contract.
    store_id: str | None = Field(default=None, min_length=1, max_length=128, exclude=True)
    conversation_id: str = Field(
        min_length=1,
        max_length=255,
        validation_alias=AliasChoices(
            "conversation_id", "conversation_external_ref"
        ),
    )
    external_message_id: str = Field(min_length=1, max_length=255)
    sender: str = Field(
        default="customer",
        min_length=1,
        max_length=255,
        pattern=r"^[\s\S]*\S[\s\S]*$",
    )
    content: str = Field(
        min_length=1,
        max_length=8_000,
        pattern=r"^[\s\S]*\S[\s\S]*$",
        validation_alias=AliasChoices("content", "text"),
    )
    timestamp: AwareDatetime = Field(
        default_factory=utc_now,
        validation_alias=AliasChoices("timestamp", "received_at"),
    )


# Foundation compatibility name. Serialization always uses normalized field names.
ChannelMessage = NormalizedMessage


class OutboundMessage(ChannelModel):
    channel: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9][a-z0-9._-]{0,79}$",
    )
    conversation_id: str = Field(min_length=1, max_length=255)
    execution_id: str = Field(min_length=1, max_length=128)
    approved_by: str = Field(
        min_length=1,
        max_length=160,
        pattern=r"^[\s\S]*\S[\s\S]*$",
    )
    content: str = Field(
        min_length=1,
        max_length=8_000,
        pattern=r"^[\s\S]*\S[\s\S]*$",
    )
    idempotency_key: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )
    requested_at: AwareDatetime = Field(default_factory=utc_now)


class ChannelSendReceipt(ChannelModel):
    receipt_id: str = Field(min_length=1, max_length=128)
    channel: str
    conversation_id: str
    execution_id: str
    idempotency_key: str
    external_message_id: str | None
    outcome: ReceiptOutcome
    error_code: str | None
    details: dict[str, object] = Field(default_factory=dict)
    recorded_at: AwareDatetime

    @model_validator(mode="after")
    def validate_outcome(self) -> ChannelSendReceipt:
        if self.outcome is ReceiptOutcome.SUCCESS and self.error_code is not None:
            raise ValueError("SUCCESS cannot carry error_code")
        if self.outcome is not ReceiptOutcome.SUCCESS and self.error_code is None:
            raise ValueError("FAILED and UNKNOWN require error_code")
        return self


class ChannelConversation(ChannelModel):
    channel: str
    conversation_id: str
    participant_ids: tuple[str, ...] = ()
    message_count: int = Field(default=0, ge=0)
    last_message_at: AwareDatetime | None = None


class AdapterHealthStatus(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"


class AdapterHealth(ChannelModel):
    adapter_name: str
    channel: str
    status: AdapterHealthStatus
    checked_at: AwareDatetime
    real_platform_connected: bool
    details: dict[str, object] = Field(default_factory=dict)


@runtime_checkable
class ChannelAdapter(Protocol):
    @property
    def channel(self) -> str:
        """Stable registry key for this adapter."""

    def receive_message(self) -> NormalizedMessage | None:
        """Receive and normalize one inbound platform message."""

    def send_message(self, message: OutboundMessage) -> ChannelSendReceipt:
        """Send one previously approved message and return an immutable receipt."""

    def get_conversation(self, conversation_id: str) -> ChannelConversation | None:
        """Return normalized conversation metadata when known."""

    def health_check(self) -> AdapterHealth:
        """Return adapter-local health without raising for normal degradation."""


class InboundChannel(Protocol):
    def receive_message(self) -> NormalizedMessage | None:
        """Return the next inbound message, or None when the channel is empty."""
