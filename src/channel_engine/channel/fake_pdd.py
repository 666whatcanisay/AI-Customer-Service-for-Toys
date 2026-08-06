from __future__ import annotations

import hashlib
import json
from collections import deque
from threading import Lock

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from channel_engine.models.entities import new_id, utc_now
from channel_engine.models.enums import ReceiptOutcome

from .protocol import (
    AdapterHealth,
    AdapterHealthStatus,
    ChannelConversation,
    ChannelSendReceipt,
    NormalizedMessage,
    OutboundMessage,
)


class ChannelAdapterError(RuntimeError):
    pass


class ChannelAdapterUnavailable(ChannelAdapterError):
    pass


class ChannelConversationNotFound(ChannelAdapterError):
    pass


class ChannelIdempotencyConflict(ChannelAdapterError):
    pass


class FakePDDInboundMessage(BaseModel):
    """Synthetic platform-shaped input; it is not a real PDD payload."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chat_id: str = Field(min_length=1, max_length=255)
    message_id: str = Field(min_length=1, max_length=255)
    buyer_id: str = Field(min_length=1, max_length=255)
    body: str = Field(
        min_length=1,
        max_length=8_000,
        pattern=r"^[\s\S]*\S[\s\S]*$",
    )
    created_at: AwareDatetime = Field(default_factory=utc_now)


class FakePDDAdapter:
    """In-memory PDD-shaped simulator with no platform or network connection."""

    channel = "fake-pdd"
    adapter_name = "FakePDDAdapter"

    def __init__(
        self,
        *,
        send_outcome: ReceiptOutcome = ReceiptOutcome.SUCCESS,
        receive_unavailable: bool = False,
        send_unavailable: bool = False,
        healthy: bool = True,
    ) -> None:
        self.send_outcome = send_outcome
        self.receive_unavailable = receive_unavailable
        self.send_unavailable = send_unavailable
        self.healthy = healthy
        self.receive_call_count = 0
        self.send_call_count = 0
        self._inbound: deque[NormalizedMessage] = deque()
        self._inbound_fingerprints: dict[tuple[str, str], str] = {}
        self._conversations: dict[str, ChannelConversation] = {}
        self._send_results: dict[
            str, tuple[str, ChannelSendReceipt]
        ] = {}
        self._lock = Lock()

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._inbound)

    @property
    def sent_receipts(self) -> list[ChannelSendReceipt]:
        with self._lock:
            return [result for _fingerprint, result in self._send_results.values()]

    def normalize_message(self, raw: FakePDDInboundMessage) -> NormalizedMessage:
        return NormalizedMessage(
            channel=self.channel,
            conversation_id=raw.chat_id,
            external_message_id=raw.message_id,
            sender=raw.buyer_id,
            content=raw.body,
            timestamp=raw.created_at,
        )

    def enqueue_customer_message(self, raw: FakePDDInboundMessage) -> bool:
        fingerprint = self._fingerprint(raw.model_dump(mode="json"))
        dedupe_key = (raw.chat_id, raw.message_id)
        with self._lock:
            previous = self._inbound_fingerprints.get(dedupe_key)
            if previous is not None:
                if previous != fingerprint:
                    raise ChannelIdempotencyConflict(
                        "fake PDD message ID was reused with different content"
                    )
                return False

            message = self.normalize_message(raw)
            self._inbound_fingerprints[dedupe_key] = fingerprint
            self._inbound.append(message)
            current = self._conversations.get(raw.chat_id)
            participants = set(current.participant_ids if current else ())
            participants.add(raw.buyer_id)
            self._conversations[raw.chat_id] = ChannelConversation(
                channel=self.channel,
                conversation_id=raw.chat_id,
                participant_ids=tuple(sorted(participants)),
                message_count=(current.message_count if current else 0) + 1,
                last_message_at=raw.created_at,
            )
            return True

    def receive_message(self) -> NormalizedMessage | None:
        if self.receive_unavailable:
            raise ChannelAdapterUnavailable("FakePDDAdapter receive is unavailable")
        with self._lock:
            self.receive_call_count += 1
            if not self._inbound:
                return None
            return self._inbound.popleft()

    def send_message(self, message: OutboundMessage) -> ChannelSendReceipt:
        if self.send_unavailable:
            raise ChannelAdapterUnavailable("FakePDDAdapter send is unavailable")
        if message.channel != self.channel:
            raise ValueError(
                f"outbound channel does not match adapter: {message.channel}"
            )
        fingerprint = self._fingerprint(message.model_dump(mode="json"))
        with self._lock:
            if message.conversation_id not in self._conversations:
                raise ChannelConversationNotFound(
                    f"fake conversation not found: {message.conversation_id}"
                )
            replay = self._send_results.get(message.idempotency_key)
            if replay is not None:
                previous_fingerprint, previous_receipt = replay
                if previous_fingerprint != fingerprint:
                    raise ChannelIdempotencyConflict(
                        "send idempotency key was reused with a different message"
                    )
                return previous_receipt

            self.send_call_count += 1
            error_code = {
                ReceiptOutcome.SUCCESS: None,
                ReceiptOutcome.FAILED: "FAKE_PDD_SEND_FAILED",
                ReceiptOutcome.UNKNOWN: "FAKE_PDD_SEND_UNKNOWN",
            }[self.send_outcome]
            receipt = ChannelSendReceipt(
                receipt_id=new_id("channel-send-receipt"),
                channel=self.channel,
                conversation_id=message.conversation_id,
                execution_id=message.execution_id,
                idempotency_key=message.idempotency_key,
                external_message_id=(
                    new_id("fake-pdd-reply")
                    if self.send_outcome is ReceiptOutcome.SUCCESS
                    else None
                ),
                outcome=self.send_outcome,
                error_code=error_code,
                details={
                    "mode": "FAKE",
                    "adapter": self.adapter_name,
                    "approved_by": message.approved_by,
                    "real_platform_called": False,
                    "customer_message_sent": False,
                    "simulated_reply_recorded": (
                        self.send_outcome is ReceiptOutcome.SUCCESS
                    ),
                },
                recorded_at=utc_now(),
            )
            self._send_results[message.idempotency_key] = (fingerprint, receipt)
            return receipt

    def get_conversation(self, conversation_id: str) -> ChannelConversation | None:
        with self._lock:
            return self._conversations.get(conversation_id)

    def health_check(self) -> AdapterHealth:
        return AdapterHealth(
            adapter_name=self.adapter_name,
            channel=self.channel,
            status=(
                AdapterHealthStatus.HEALTHY
                if self.healthy
                else AdapterHealthStatus.UNHEALTHY
            ),
            checked_at=utc_now(),
            real_platform_connected=False,
            details={
                "mode": "FAKE",
                "pending_messages": self.pending_count,
                "real_pdd_connected": False,
            },
        )

    @staticmethod
    def _fingerprint(payload: dict[str, object]) -> str:
        return hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
