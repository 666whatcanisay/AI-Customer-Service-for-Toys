from __future__ import annotations

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from channel_engine.models.entities import utc_now


class ChannelMessage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    channel_name: str
    conversation_external_ref: str
    external_message_id: str
    text: str = Field(min_length=1, max_length=8_000)
    received_at: datetime = Field(default_factory=utc_now)


class InboundChannel(Protocol):
    def receive(self) -> ChannelMessage | None:
        """Return the next inbound message, or None when the channel is empty."""
