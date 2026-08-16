from __future__ import annotations

import hashlib
import json
from collections import deque
from collections.abc import Callable
from enum import StrEnum
from threading import RLock
from typing import Literal, Protocol, runtime_checkable

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from channel_engine.models import ReceiptOutcome
from channel_engine.models.entities import new_id, utc_now
from channel_engine.reliability import ComponentHealth, ProbeReading

from .platform import (
    AuthorizedOutboundMessage,
    ExecutionBoundaryDenied,
    SendAuthorizationVerifier,
)
from .protocol import (
    AdapterHealth,
    AdapterHealthStatus,
    ChannelConversation,
    ChannelSendReceipt,
    NormalizedMessage,
)


CHANNEL_ADAPTER_CONTRACT_VERSION = "1.0"


class AdapterFoundationModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    adapter_contract_version: Literal["1.0"] = CHANNEL_ADAPTER_CONTRACT_VERSION


class AdapterLifecycleState(StrEnum):
    STARTING = "STARTING"
    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"
    DISCONNECTED = "DISCONNECTED"
    RECOVERING = "RECOVERING"


class ChannelCapabilities(AdapterFoundationModel):
    message_receive: bool
    send_message: bool
    image: bool = False
    order_query: bool = False


class ChannelMessageV1(AdapterFoundationModel):
    message_id: str = Field(min_length=1, max_length=255)
    channel: str = Field(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9][a-z0-9._-]{0,79}$",
    )
    store_id: str = Field(min_length=1, max_length=128)
    conversation_id: str = Field(min_length=1, max_length=255)
    sender: str = Field(min_length=1, max_length=255)
    content: str = Field(
        min_length=1,
        max_length=8_000,
        pattern=r"^[\s\S]*\S[\s\S]*$",
    )
    timestamp: AwareDatetime

    def to_runtime_message(self) -> NormalizedMessage:
        """Map into the established Conversation Runtime input without AI work."""

        return NormalizedMessage(
            channel=self.channel,
            store_id=self.store_id,
            conversation_id=self.conversation_id,
            external_message_id=self.message_id,
            sender=self.sender,
            content=self.content,
            timestamp=self.timestamp,
        )


class FakeChannelInbound(AdapterFoundationModel):
    message_id: str = Field(min_length=1, max_length=255)
    conversation_id: str = Field(min_length=1, max_length=255)
    sender: str = Field(min_length=1, max_length=255)
    content: str = Field(
        min_length=1,
        max_length=8_000,
        pattern=r"^[\s\S]*\S[\s\S]*$",
    )
    timestamp: AwareDatetime = Field(default_factory=utc_now)


class AdapterInboundEnvelope(AdapterFoundationModel):
    message: ChannelMessageV1
    source_cursor: str = Field(min_length=1, max_length=512)
    source_sequence: int = Field(ge=1)


class AdapterSourceAck(AdapterFoundationModel):
    channel: str
    store_id: str
    source_cursor: str
    source_sequence: int = Field(ge=0)
    duplicate: bool = False
    acknowledged_at: AwareDatetime


class ChannelAdapterStatus(AdapterFoundationModel):
    adapter_name: str = Field(min_length=1, max_length=128)
    channel: str = Field(min_length=1, max_length=80)
    store_id: str = Field(min_length=1, max_length=128)
    lifecycle: AdapterLifecycleState
    health: AdapterHealthStatus
    capabilities: ChannelCapabilities
    real_platform_connected: bool = False
    checked_at: AwareDatetime
    reason_code: str = Field(min_length=3, max_length=128)


class ChannelManagerStatus(AdapterFoundationModel):
    adapters: tuple[ChannelAdapterStatus, ...]
    registered_channels: tuple[str, ...]
    connected_count: int = Field(ge=0)
    degraded_count: int = Field(ge=0)
    overall: AdapterHealthStatus
    checked_at: AwareDatetime


@runtime_checkable
class ChannelAdapterV1(Protocol):
    @property
    def channel(self) -> str: ...

    @property
    def store_id(self) -> str: ...

    @property
    def adapter_name(self) -> str: ...

    @property
    def lifecycle_state(self) -> AdapterLifecycleState: ...

    @property
    def capabilities(self) -> ChannelCapabilities: ...

    def connect(self) -> ChannelAdapterStatus: ...

    def disconnect(self) -> ChannelAdapterStatus: ...

    def receive_messages(self, limit: int = 100) -> tuple[ChannelMessageV1, ...]: ...

    def send_message(
        self, command: AuthorizedOutboundMessage
    ) -> ChannelSendReceipt: ...

    def get_conversation(
        self, conversation_id: str
    ) -> ChannelConversation | None: ...

    def health_check(self) -> AdapterHealth: ...

    def recover(self) -> ChannelAdapterStatus: ...


@runtime_checkable
class CursorAckChannelAdapterV1(ChannelAdapterV1, Protocol):
    def receive_envelopes(
        self, limit: int = 100
    ) -> tuple[AdapterInboundEnvelope, ...]: ...

    def acknowledge(self, source_cursor: str) -> AdapterSourceAck: ...

    def resume_from(self, source_cursor: str | None, last_sequence: int) -> None: ...


class ManagedChannelUnavailable(RuntimeError):
    pass


class ChannelMessageConflict(ValueError):
    pass


class FakeChannelAdapter:
    """Store-aware contract adapter. It never performs platform I/O."""

    adapter_name = "FakeChannelAdapter"

    def __init__(
        self,
        *,
        channel: str = "fake",
        store_id: str = "fake-store",
        authorization_verifier: SendAuthorizationVerifier | None = None,
        fail_connect: bool = False,
        failed_recovery_attempts: int = 0,
        send_outcome: ReceiptOutcome = ReceiptOutcome.SUCCESS,
        clock: Callable = utc_now,
    ) -> None:
        if failed_recovery_attempts < 0:
            raise ValueError("failed_recovery_attempts cannot be negative")
        self.channel = channel
        self.store_id = store_id
        self._authorization_verifier = authorization_verifier
        self.fail_connect = fail_connect
        self.failed_recovery_attempts = failed_recovery_attempts
        self.send_outcome = send_outcome
        self._clock = clock
        self._state = AdapterLifecycleState.DISCONNECTED
        self._reason_code = "ADAPTER_DISCONNECTED"
        self._inbound: deque[tuple[int, ChannelMessageV1]] = deque()
        self._message_fingerprints: dict[tuple[str, str, str], str] = {}
        self._conversations: dict[str, ChannelConversation] = {}
        self._send_results: dict[str, tuple[str, ChannelSendReceipt]] = {}
        self._lock = RLock()
        self.connect_count = 0
        self.disconnect_count = 0
        self.receive_call_count = 0
        self.send_call_count = 0
        self.recovery_count = 0
        self.source_ack_count = 0
        self._next_source_sequence = 1
        self._source_acked_sequence = 0
        self._transition_history: list[AdapterLifecycleState] = [
            AdapterLifecycleState.DISCONNECTED
        ]

    @property
    def lifecycle_state(self) -> AdapterLifecycleState:
        with self._lock:
            return self._state

    @property
    def transition_history(self) -> tuple[AdapterLifecycleState, ...]:
        with self._lock:
            return tuple(self._transition_history)

    @property
    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            message_receive=True,
            send_message=self._authorization_verifier is not None,
            image=False,
            order_query=False,
        )

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._inbound)

    @property
    def sent_receipts(self) -> tuple[ChannelSendReceipt, ...]:
        with self._lock:
            return tuple(item[1] for item in self._send_results.values())

    def connect(self) -> ChannelAdapterStatus:
        with self._lock:
            if self._state is AdapterLifecycleState.CONNECTED:
                return self.status()
            self._state = AdapterLifecycleState.STARTING
            self._transition_history.append(self._state)
            self.connect_count += 1
            if self.fail_connect:
                self._state = AdapterLifecycleState.DEGRADED
                self._transition_history.append(self._state)
                self._reason_code = "FAKE_ADAPTER_CONNECT_FAILED"
                raise ManagedChannelUnavailable(self._reason_code)
            self._state = AdapterLifecycleState.CONNECTED
            self._transition_history.append(self._state)
            self._reason_code = "FAKE_ADAPTER_CONNECTED"
            return self.status()

    def disconnect(self) -> ChannelAdapterStatus:
        with self._lock:
            if self._state is not AdapterLifecycleState.DISCONNECTED:
                self.disconnect_count += 1
            self._state = AdapterLifecycleState.DISCONNECTED
            self._transition_history.append(self._state)
            self._reason_code = "ADAPTER_DISCONNECTED"
            return self.status()

    def normalize_message(self, raw: FakeChannelInbound) -> ChannelMessageV1:
        return ChannelMessageV1(
            message_id=raw.message_id,
            channel=self.channel,
            store_id=self.store_id,
            conversation_id=raw.conversation_id,
            sender=raw.sender,
            content=raw.content,
            timestamp=raw.timestamp,
        )

    def enqueue_message(self, raw: FakeChannelInbound) -> bool:
        message = self.normalize_message(raw)
        key = (message.store_id, message.conversation_id, message.message_id)
        fingerprint = self._fingerprint(message.model_dump(mode="json"))
        with self._lock:
            previous = self._message_fingerprints.get(key)
            if previous is not None:
                if previous != fingerprint:
                    raise ChannelMessageConflict(
                        "message_id was reused with different normalized content"
                    )
                return False
            self._message_fingerprints[key] = fingerprint
            self._inbound.append((self._next_source_sequence, message))
            self._next_source_sequence += 1
            current = self._conversations.get(message.conversation_id)
            participants = set(current.participant_ids if current else ())
            participants.add(message.sender)
            self._conversations[message.conversation_id] = ChannelConversation(
                channel=self.channel,
                conversation_id=message.conversation_id,
                participant_ids=tuple(sorted(participants)),
                message_count=(current.message_count if current else 0) + 1,
                last_message_at=message.timestamp,
            )
            return True

    def receive_messages(self, limit: int = 100) -> tuple[ChannelMessageV1, ...]:
        if limit < 1 or limit > 100:
            raise ValueError("receive limit must be between 1 and 100")
        self._assert_connected()
        with self._lock:
            self.receive_call_count += 1
            messages: list[ChannelMessageV1] = []
            while self._inbound and len(messages) < limit:
                sequence, message = self._inbound.popleft()
                self._source_acked_sequence = max(
                    self._source_acked_sequence, sequence
                )
                messages.append(message)
            return tuple(messages)

    def receive_envelopes(
        self, limit: int = 100
    ) -> tuple[AdapterInboundEnvelope, ...]:
        if limit < 1 or limit > 100:
            raise ValueError("receive limit must be between 1 and 100")
        self._assert_connected()
        with self._lock:
            self.receive_call_count += 1
            return tuple(
                AdapterInboundEnvelope(
                    message=message,
                    source_cursor=f"fake:{sequence}",
                    source_sequence=sequence,
                )
                for sequence, message in list(self._inbound)[:limit]
            )

    def acknowledge(self, source_cursor: str) -> AdapterSourceAck:
        self._assert_connected()
        try:
            prefix, raw_sequence = source_cursor.split(":", 1)
            sequence = int(raw_sequence)
        except (ValueError, TypeError) as exc:
            raise ValueError("invalid fake source cursor") from exc
        if prefix != "fake" or sequence < 0:
            raise ValueError("invalid fake source cursor")
        with self._lock:
            highest_available = self._next_source_sequence - 1
            if sequence > highest_available:
                raise ValueError("source cursor has not been received")
            duplicate = sequence <= self._source_acked_sequence
            if not duplicate:
                while self._inbound and self._inbound[0][0] <= sequence:
                    self._inbound.popleft()
                self._source_acked_sequence = sequence
                self.source_ack_count += 1
            return AdapterSourceAck(
                channel=self.channel,
                store_id=self.store_id,
                source_cursor=source_cursor,
                source_sequence=sequence,
                duplicate=duplicate,
                acknowledged_at=self._clock(),
            )

    def resume_from(self, source_cursor: str | None, last_sequence: int) -> None:
        if last_sequence < 0:
            raise ValueError("last_sequence cannot be negative")
        with self._lock:
            if self._inbound:
                raise ValueError("cannot replace cursor while messages are pending")
            self._source_acked_sequence = last_sequence
            self._next_source_sequence = last_sequence + 1
            if source_cursor is not None and not source_cursor:
                raise ValueError("source_cursor cannot be blank")

    def receive_message(self) -> NormalizedMessage | None:
        """Compatibility bridge for the established Conversation Runtime."""

        batch = self.receive_messages(limit=1)
        return batch[0].to_runtime_message() if batch else None

    def send_message(
        self, command: AuthorizedOutboundMessage
    ) -> ChannelSendReceipt:
        if not isinstance(command, AuthorizedOutboundMessage):
            raise ExecutionBoundaryDenied(
                "ChannelAdapterV1 rejects bare outbound content"
            )
        self._assert_connected()
        if self._authorization_verifier is None:
            raise ExecutionBoundaryDenied(
                "send capability requires a ledger authorization verifier"
            )
        self._authorization_verifier.verify(command)
        message = command.message
        if message.channel != self.channel:
            raise ExecutionBoundaryDenied("authorized send targets another channel")
        if message.conversation_id not in self._conversations:
            raise ExecutionBoundaryDenied("authorized conversation is unknown")
        fingerprint = self._fingerprint(command.model_dump(mode="json"))
        with self._lock:
            replay = self._send_results.get(message.idempotency_key)
            if replay is not None:
                if replay[0] != fingerprint:
                    raise ExecutionBoundaryDenied(
                        "send idempotency key is bound to another command"
                    )
                return replay[1]
            self.send_call_count += 1
            error_code = {
                ReceiptOutcome.SUCCESS: None,
                ReceiptOutcome.FAILED: "FAKE_CHANNEL_SEND_FAILED",
                ReceiptOutcome.UNKNOWN: "FAKE_CHANNEL_SEND_UNKNOWN",
            }[self.send_outcome]
            receipt = ChannelSendReceipt(
                receipt_id=new_id("fake-channel-receipt"),
                channel=self.channel,
                conversation_id=message.conversation_id,
                execution_id=message.execution_id,
                idempotency_key=message.idempotency_key,
                external_message_id=(
                    new_id("fake-channel-message")
                    if self.send_outcome is ReceiptOutcome.SUCCESS
                    else None
                ),
                outcome=self.send_outcome,
                error_code=error_code,
                details={
                    "mode": "FAKE",
                    "store_id": self.store_id,
                    "real_platform_called": False,
                    "customer_message_sent": False,
                    "automatic_send": False,
                },
                recorded_at=self._clock(),
            )
            self._send_results[message.idempotency_key] = (fingerprint, receipt)
            return receipt

    def get_conversation(self, conversation_id: str) -> ChannelConversation | None:
        with self._lock:
            return self._conversations.get(conversation_id)

    def health_check(self) -> AdapterHealth:
        state = self.lifecycle_state
        health = {
            AdapterLifecycleState.CONNECTED: AdapterHealthStatus.HEALTHY,
            AdapterLifecycleState.STARTING: AdapterHealthStatus.DEGRADED,
            AdapterLifecycleState.RECOVERING: AdapterHealthStatus.DEGRADED,
            AdapterLifecycleState.DEGRADED: AdapterHealthStatus.UNHEALTHY,
            AdapterLifecycleState.DISCONNECTED: AdapterHealthStatus.UNHEALTHY,
        }[state]
        return AdapterHealth(
            adapter_name=self.adapter_name,
            channel=self.channel,
            status=health,
            checked_at=self._clock(),
            real_platform_connected=False,
            details={
                "adapter_contract_version": CHANNEL_ADAPTER_CONTRACT_VERSION,
                "store_id": self.store_id,
                "lifecycle": state.value,
                "reason_code": self._reason_code,
                "pending_messages": self.pending_count,
                "real_platform_called": False,
                "automatic_send_enabled": False,
            },
        )

    def status(self) -> ChannelAdapterStatus:
        health = self.health_check()
        return ChannelAdapterStatus(
            adapter_name=self.adapter_name,
            channel=self.channel,
            store_id=self.store_id,
            lifecycle=self.lifecycle_state,
            health=health.status,
            capabilities=self.capabilities,
            real_platform_connected=False,
            checked_at=health.checked_at,
            reason_code=self._reason_code,
        )

    def simulate_degraded(self, reason_code: str = "FAKE_ADAPTER_UNAVAILABLE") -> None:
        with self._lock:
            self._state = AdapterLifecycleState.DEGRADED
            self._transition_history.append(self._state)
            self._reason_code = reason_code

    def recover(self) -> ChannelAdapterStatus:
        with self._lock:
            self._state = AdapterLifecycleState.RECOVERING
            self._transition_history.append(self._state)
            self._reason_code = "ADAPTER_RECOVERING"
            self.recovery_count += 1
            if self.recovery_count <= self.failed_recovery_attempts:
                self._state = AdapterLifecycleState.DEGRADED
                self._transition_history.append(self._state)
                self._reason_code = "FAKE_ADAPTER_RECOVERY_FAILED"
            else:
                self._state = AdapterLifecycleState.CONNECTED
                self._transition_history.append(self._state)
                self._reason_code = "FAKE_ADAPTER_RECOVERED"
            return self.status()

    def _assert_connected(self) -> None:
        if self.lifecycle_state is not AdapterLifecycleState.CONNECTED:
            raise ManagedChannelUnavailable("channel adapter is not CONNECTED")

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


class ChannelManager:
    def __init__(self, *, clock: Callable = utc_now) -> None:
        self._clock = clock
        self._adapters: dict[str, ChannelAdapterV1] = {}
        self._lock = RLock()

    def register(self, adapter: ChannelAdapterV1) -> bool:
        if not isinstance(adapter, ChannelAdapterV1):
            raise TypeError("adapter does not implement ChannelAdapterV1")
        with self._lock:
            existing = self._adapters.get(adapter.channel)
            if existing is adapter:
                return False
            if existing is not None:
                raise ValueError(
                    f"channel already has a managed adapter: {adapter.channel}"
                )
            self._adapters[adapter.channel] = adapter
            return True

    def get(self, channel: str) -> ChannelAdapterV1:
        with self._lock:
            adapter = self._adapters.get(channel)
        if adapter is None:
            raise LookupError(f"managed channel is not registered: {channel}")
        return adapter

    def registered_channels(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._adapters))

    def start_adapter(self, channel: str) -> ChannelAdapterStatus:
        return self.get(channel).connect()

    def stop_adapter(self, channel: str) -> ChannelAdapterStatus:
        return self.get(channel).disconnect()

    def start_all(self) -> ChannelManagerStatus:
        started: list[str] = []
        try:
            for channel in self.registered_channels():
                self.start_adapter(channel)
                started.append(channel)
        except Exception:
            for channel in reversed(started):
                try:
                    self.stop_adapter(channel)
                except Exception:
                    pass
            raise
        return self.status()

    def stop_all(self) -> ChannelManagerStatus:
        failures: list[Exception] = []
        for channel in reversed(self.registered_channels()):
            try:
                self.stop_adapter(channel)
            except Exception as exc:
                failures.append(exc)
        if failures:
            raise ManagedChannelUnavailable("one or more adapters failed to stop")
        return self.status()

    def recover_adapter(self, channel: str) -> ChannelAdapterStatus:
        return self.get(channel).recover()

    def recover_all(self) -> bool:
        recovered = True
        for channel in self.registered_channels():
            adapter = self.get(channel)
            if adapter.lifecycle_state is AdapterLifecycleState.DEGRADED:
                status = adapter.recover()
                recovered = (
                    status.lifecycle is AdapterLifecycleState.CONNECTED and recovered
                )
        return recovered and bool(self.registered_channels())

    def health_check(self) -> dict[str, AdapterHealth]:
        result: dict[str, AdapterHealth] = {}
        for channel in self.registered_channels():
            adapter = self.get(channel)
            try:
                result[channel] = adapter.health_check()
            except Exception as exc:
                result[channel] = AdapterHealth(
                    adapter_name=adapter.adapter_name,
                    channel=channel,
                    status=AdapterHealthStatus.UNHEALTHY,
                    checked_at=self._clock(),
                    real_platform_connected=False,
                    details={"error_type": type(exc).__name__},
                )
        return result

    def status(self) -> ChannelManagerStatus:
        health = self.health_check()
        adapters = tuple(
            ChannelAdapterStatus(
                adapter_name=self.get(channel).adapter_name,
                channel=channel,
                store_id=self.get(channel).store_id,
                lifecycle=self.get(channel).lifecycle_state,
                health=health[channel].status,
                capabilities=self.get(channel).capabilities,
                real_platform_connected=health[channel].real_platform_connected,
                checked_at=health[channel].checked_at,
                reason_code=str(
                    health[channel].details.get(
                        "reason_code",
                        f"ADAPTER_{health[channel].status.value}",
                    )
                ),
            )
            for channel in self.registered_channels()
        )
        connected = sum(
            item.lifecycle is AdapterLifecycleState.CONNECTED for item in adapters
        )
        degraded = sum(
            item.lifecycle
            in {AdapterLifecycleState.DEGRADED, AdapterLifecycleState.RECOVERING}
            for item in adapters
        )
        values = tuple(item.status for item in health.values())
        overall = (
            AdapterHealthStatus.UNHEALTHY
            if not values or AdapterHealthStatus.UNHEALTHY in values
            else (
                AdapterHealthStatus.DEGRADED
                if AdapterHealthStatus.DEGRADED in values
                else AdapterHealthStatus.HEALTHY
            )
        )
        return ChannelManagerStatus(
            adapters=adapters,
            registered_channels=self.registered_channels(),
            connected_count=connected,
            degraded_count=degraded,
            overall=overall,
            checked_at=self._clock(),
        )


class ChannelManagerHealthProbe:
    def __init__(self, manager: ChannelManager) -> None:
        self._manager = manager

    def __call__(self) -> ProbeReading:
        status = self._manager.status()
        health = {
            AdapterHealthStatus.HEALTHY: ComponentHealth.HEALTHY,
            AdapterHealthStatus.DEGRADED: ComponentHealth.DEGRADED,
            AdapterHealthStatus.UNHEALTHY: ComponentHealth.UNHEALTHY,
        }[status.overall]
        return ProbeReading(
            health=health,
            available=(
                bool(status.adapters)
                and status.connected_count == len(status.adapters)
            ),
            reason_code=(
                "CHANNEL_ADAPTERS_HEALTHY"
                if health is ComponentHealth.HEALTHY
                else (
                    "CHANNEL_ADAPTERS_DEGRADED"
                    if health is ComponentHealth.DEGRADED
                    else "CHANNEL_ADAPTERS_UNHEALTHY"
                )
            ),
        )


__all__ = [
    "AdapterLifecycleState",
    "AdapterInboundEnvelope",
    "AdapterSourceAck",
    "CHANNEL_ADAPTER_CONTRACT_VERSION",
    "ChannelAdapterStatus",
    "ChannelAdapterV1",
    "ChannelCapabilities",
    "ChannelManager",
    "ChannelManagerHealthProbe",
    "ChannelManagerStatus",
    "CursorAckChannelAdapterV1",
    "ChannelMessageConflict",
    "ChannelMessageV1",
    "FakeChannelAdapter",
    "FakeChannelInbound",
    "ManagedChannelUnavailable",
]
