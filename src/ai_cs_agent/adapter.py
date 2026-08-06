from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class NormalizedMessage:
    message_id: str
    channel: str
    store_id: str
    conversation_id: str
    sender: str
    content: str
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class AdapterHealth:
    channel: str
    status: str
    reason_code: str


@dataclass(frozen=True, slots=True)
class AuthorizedOutboundCommand:
    execution_id: str
    decision_id: str
    approval_id: str
    lease_token: str
    idempotency_key: str
    content: str


class ChannelAdapter(Protocol):
    """Production port only. This RC intentionally ships no platform implementation."""

    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def receive_messages(self) -> tuple[NormalizedMessage, ...]: ...

    def send_message(self, command: AuthorizedOutboundCommand) -> str: ...

    def health_check(self) -> AdapterHealth: ...

    def get_conversation(self, conversation_id: str) -> object | None: ...
