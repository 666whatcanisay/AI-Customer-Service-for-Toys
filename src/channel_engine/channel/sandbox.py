from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from threading import RLock
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from channel_engine.execution import (
    ClaimedExecutionContext,
    ExecutionCommand,
    ExecutionResult,
)
from channel_engine.gateway import AICSGateway, DecisionRequest, DecisionResponse
from channel_engine.models import ReceiptOutcome
from channel_engine.models.entities import new_id, utc_now
from channel_engine.reliability import ComponentHealth, ProbeReading
from channel_engine.session import (
    ChannelInstanceManager,
    ChannelInstanceView,
    ChannelSessionStatus,
)

from .adapter_foundation import (
    AdapterInboundEnvelope,
    AdapterLifecycleState,
    AdapterSourceAck,
    ChannelAdapterStatus,
    ChannelMessageV1,
    FakeChannelAdapter,
    FakeChannelInbound,
    ManagedChannelUnavailable,
)
from .execution_boundary import LedgerExecutionAuthorizationService
from .platform import (
    AuthorizedOutboundMessage,
    ExecutionBoundaryDenied,
    SendAuthorizationVerifier,
)
from .protocol import (
    ChannelConversation,
    ChannelSendReceipt,
    store_scoped_conversation_ref,
)


SANDBOX_ADAPTER_VERSION = "1.0"


class SandboxModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sandbox_adapter_version: Literal["1.0"] = SANDBOX_ADAPTER_VERSION


class SandboxEventType(StrEnum):
    CUSTOMER_MESSAGE_RECEIVED = "customer_message_received"
    MESSAGE_DUPLICATE = "message_duplicate"
    MESSAGE_DELAY = "message_delay"
    ACK_FAILURE = "ack_failure"
    SESSION_EXPIRED = "session_expired"
    BROWSER_DISCONNECTED = "browser_disconnected"
    NETWORK_FAILURE = "network_failure"
    ADAPTER_CRASHED = "adapter_crashed"
    RECOVERY_COMPLETED = "recovery_completed"


class SandboxEventRecord(SandboxModel):
    event_id: str = Field(min_length=1, max_length=128)
    event_type: SandboxEventType
    store_id: str = Field(min_length=1, max_length=128)
    details: dict[str, str | int | bool] = Field(default_factory=dict)
    occurred_at: AwareDatetime


class SandboxAckFailure(RuntimeError):
    pass


class SandboxGatewayTimeout(TimeoutError):
    pass


class SandboxClock:
    """Deterministic, thread-safe clock used by sandbox scenarios only."""

    def __init__(self, initial: datetime | None = None) -> None:
        value = initial or utc_now()
        if value.tzinfo is None:
            raise ValueError("sandbox clock requires an aware datetime")
        self._current = value
        self._lock = RLock()

    def __call__(self) -> datetime:
        with self._lock:
            return self._current

    def advance(self, delta: timedelta) -> datetime:
        if delta <= timedelta(0):
            raise ValueError("sandbox clock advance must be positive")
        with self._lock:
            self._current += delta
            return self._current


class SandboxDependencyProbe:
    """Mutable Browser/Gateway probe with no external connectivity."""

    def __init__(
        self,
        *,
        healthy_reason: str,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._clock = clock
        self._health = ComponentHealth.HEALTHY
        self._available = True
        self._reason_code = healthy_reason
        self._lock = RLock()
        self.check_count = 0

    def __call__(self) -> ProbeReading:
        with self._lock:
            self.check_count += 1
            return ProbeReading(
                health=self._health,
                available=self._available,
                reason_code=self._reason_code,
            )

    def disconnect(self, reason_code: str) -> None:
        with self._lock:
            self._health = ComponentHealth.UNHEALTHY
            self._available = False
            self._reason_code = reason_code

    def degrade(self, reason_code: str) -> None:
        with self._lock:
            self._health = ComponentHealth.DEGRADED
            self._available = True
            self._reason_code = reason_code

    def recover(self, reason_code: str = "SANDBOX_DEPENDENCY_RECOVERED") -> bool:
        with self._lock:
            self._health = ComponentHealth.HEALTHY
            self._available = True
            self._reason_code = reason_code
        return True


class SandboxGateway:
    """Failure-injectable wrapper around a fake gateway."""

    def __init__(self, delegate: AICSGateway) -> None:
        self._delegate = delegate
        self._timeouts_remaining = 0
        self._healthy = True
        self._lock = RLock()
        self.call_count = 0
        self.timeout_count = 0

    def timeout_next(self, attempts: int = 1) -> None:
        if attempts < 1 or attempts > 100:
            raise ValueError("timeout attempts must be between 1 and 100")
        with self._lock:
            self._timeouts_remaining += attempts

    def decide(self, request: DecisionRequest) -> DecisionResponse:
        with self._lock:
            self.call_count += 1
            if self._timeouts_remaining:
                self._timeouts_remaining -= 1
                self.timeout_count += 1
                self._healthy = False
                raise SandboxGatewayTimeout("sandbox gateway timeout")
        return self._delegate.decide(request)

    def health_check(self) -> ProbeReading:
        with self._lock:
            return ProbeReading(
                health=(
                    ComponentHealth.HEALTHY
                    if self._healthy
                    else ComponentHealth.UNHEALTHY
                ),
                available=self._healthy,
                reason_code=(
                    "SANDBOX_GATEWAY_HEALTHY"
                    if self._healthy
                    else "SANDBOX_GATEWAY_TIMEOUT"
                ),
            )

    def recover(self) -> bool:
        with self._lock:
            self._healthy = True
            self._timeouts_remaining = 0
        return True


class SandboxChannelAdapter(FakeChannelAdapter):
    """PDD-like deterministic adapter with explicit failure injection.

    The adapter has no network client, browser driver, credentials, or platform
    endpoint. All outbound receipts explicitly report that nothing was sent.
    """

    adapter_name = "SandboxChannelAdapter"

    def __init__(
        self,
        *,
        store_id: str = "sandbox-store",
        authorization_verifier: SendAuthorizationVerifier | None = None,
        failed_recovery_attempts: int = 0,
        send_outcome: ReceiptOutcome = ReceiptOutcome.SUCCESS,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        super().__init__(
            channel="sandbox",
            store_id=store_id,
            authorization_verifier=authorization_verifier,
            failed_recovery_attempts=failed_recovery_attempts,
            send_outcome=send_outcome,
            clock=clock,
        )
        self._sandbox_clock = clock
        self._delay_until: datetime | None = None
        self._ack_failures_remaining = 0
        self._network_failed = False
        self._crashed = False
        self._history: dict[str, tuple[int, ChannelMessageV1]] = {}
        self._events: list[SandboxEventRecord] = []

    @property
    def events(self) -> tuple[SandboxEventRecord, ...]:
        with self._lock:
            return tuple(self._events)

    def enqueue_message(self, raw: FakeChannelInbound) -> bool:
        accepted = super().enqueue_message(raw)
        if not accepted:
            return False
        with self._lock:
            sequence, message = self._inbound[-1]
            self._history[message.message_id] = (sequence, message)
            original = self._conversations[message.conversation_id]
            scoped_ref = store_scoped_conversation_ref(
                self.store_id, message.conversation_id
            )
            self._conversations[scoped_ref] = ChannelConversation(
                channel=original.channel,
                conversation_id=scoped_ref,
                participant_ids=original.participant_ids,
                message_count=original.message_count,
                last_message_at=original.last_message_at,
            )
        return True

    def customer_message_received(
        self,
        *,
        message_id: str,
        conversation_id: str,
        content: str,
        sender: str = "sandbox-customer",
        timestamp: datetime | None = None,
    ) -> SandboxEventRecord:
        accepted = self.enqueue_message(
            FakeChannelInbound(
                message_id=message_id,
                conversation_id=conversation_id,
                sender=sender,
                content=content,
                timestamp=timestamp or self._sandbox_clock(),
            )
        )
        return self._record(
            SandboxEventType.CUSTOMER_MESSAGE_RECEIVED,
            {
                "message_id": message_id,
                "conversation_id": conversation_id,
                "accepted": accepted,
            },
        )

    def message_duplicate(self, message_id: str) -> SandboxEventRecord:
        with self._lock:
            history = self._history.get(message_id)
            if history is None:
                raise ValueError("sandbox duplicate source message does not exist")
            sequence, message = history
            if not any(
                queued_sequence == sequence and queued.message_id == message_id
                for queued_sequence, queued in self._inbound
            ):
                self._inbound.appendleft((sequence, message))
        return self._record(
            SandboxEventType.MESSAGE_DUPLICATE,
            {"message_id": message_id, "source_sequence": sequence},
        )

    def message_delay(self, delay: timedelta) -> SandboxEventRecord:
        if delay <= timedelta(0) or delay > timedelta(hours=24):
            raise ValueError("message delay must be between zero and 24 hours")
        with self._lock:
            self._delay_until = self._sandbox_clock() + delay
        return self._record(
            SandboxEventType.MESSAGE_DELAY,
            {"delay_milliseconds": int(delay.total_seconds() * 1000)},
        )

    def ack_failure(self, attempts: int = 1) -> SandboxEventRecord:
        if attempts < 1 or attempts > 100:
            raise ValueError("ACK failure attempts must be between 1 and 100")
        with self._lock:
            self._ack_failures_remaining += attempts
        return self._record(
            SandboxEventType.ACK_FAILURE,
            {"attempts": attempts},
        )

    def network_failure(self) -> SandboxEventRecord:
        with self._lock:
            self._network_failed = True
        self.simulate_degraded("SANDBOX_NETWORK_FAILURE")
        return self._record(SandboxEventType.NETWORK_FAILURE, {})

    def adapter_crashed(self) -> SandboxEventRecord:
        with self._lock:
            self._crashed = True
        self.simulate_degraded("SANDBOX_ADAPTER_CRASHED")
        return self._record(SandboxEventType.ADAPTER_CRASHED, {})

    def session_expired(self) -> SandboxEventRecord:
        return self._record(SandboxEventType.SESSION_EXPIRED, {})

    def browser_disconnected(self) -> SandboxEventRecord:
        return self._record(SandboxEventType.BROWSER_DISCONNECTED, {})

    def receive_envelopes(
        self, limit: int = 100
    ) -> tuple[AdapterInboundEnvelope, ...]:
        if limit < 1 or limit > 100:
            raise ValueError("receive limit must be between 1 and 100")
        self._assert_sandbox_available()
        with self._lock:
            self.receive_call_count += 1
            if self._delay_until is not None:
                if self._sandbox_clock() < self._delay_until:
                    return ()
                self._delay_until = None
            return tuple(
                AdapterInboundEnvelope(
                    message=message,
                    source_cursor=f"sandbox:{sequence}",
                    source_sequence=sequence,
                )
                for sequence, message in list(self._inbound)[:limit]
            )

    def receive_messages(self, limit: int = 100) -> tuple[ChannelMessageV1, ...]:
        envelopes = self.receive_envelopes(limit=limit)
        if envelopes:
            self.acknowledge(envelopes[-1].source_cursor)
        return tuple(item.message for item in envelopes)

    def acknowledge(self, source_cursor: str) -> AdapterSourceAck:
        self._assert_sandbox_available()
        try:
            prefix, raw_sequence = source_cursor.split(":", 1)
            sequence = int(raw_sequence)
        except (ValueError, TypeError) as exc:
            raise ValueError("invalid sandbox source cursor") from exc
        if prefix != "sandbox" or sequence < 0:
            raise ValueError("invalid sandbox source cursor")
        with self._lock:
            if self._ack_failures_remaining:
                self._ack_failures_remaining -= 1
                raise SandboxAckFailure("injected sandbox ACK failure")
            highest_available = self._next_source_sequence - 1
            if sequence > highest_available:
                raise ValueError("source cursor has not been received")
            duplicate = sequence <= self._source_acked_sequence
            while self._inbound and self._inbound[0][0] <= sequence:
                self._inbound.popleft()
            if not duplicate:
                self._source_acked_sequence = sequence
                self.source_ack_count += 1
            return AdapterSourceAck(
                channel=self.channel,
                store_id=self.store_id,
                source_cursor=source_cursor,
                source_sequence=sequence,
                duplicate=duplicate,
                acknowledged_at=self._sandbox_clock(),
            )

    def send_message(
        self, command: AuthorizedOutboundMessage
    ) -> ChannelSendReceipt:
        self._assert_sandbox_available()
        receipt = super().send_message(command)
        details = {
            **receipt.details,
            "mode": "SANDBOX",
            "sandbox_adapter_version": SANDBOX_ADAPTER_VERSION,
            "real_platform_called": False,
            "customer_message_sent": False,
        }
        sandbox_receipt = receipt.model_copy(update={"details": details})
        with self._lock:
            fingerprint, _original = self._send_results[
                command.message.idempotency_key
            ]
            self._send_results[command.message.idempotency_key] = (
                fingerprint,
                sandbox_receipt,
            )
        return sandbox_receipt

    def recover(self) -> ChannelAdapterStatus:
        with self._lock:
            self._network_failed = False
            self._crashed = False
        status = super().recover()
        if status.lifecycle is AdapterLifecycleState.CONNECTED:
            self._record(
                SandboxEventType.RECOVERY_COMPLETED,
                {"recovery_count": self.recovery_count},
            )
        return status

    def _assert_sandbox_available(self) -> None:
        with self._lock:
            if self._crashed:
                raise ManagedChannelUnavailable("sandbox adapter crashed")
            if self._network_failed:
                raise ManagedChannelUnavailable("sandbox network unavailable")
        self._assert_connected()

    def _record(
        self,
        event_type: SandboxEventType,
        details: dict[str, str | int | bool],
    ) -> SandboxEventRecord:
        record = SandboxEventRecord(
            event_id=new_id("sandbox-event"),
            event_type=event_type,
            store_id=self.store_id,
            details=details,
            occurred_at=self._sandbox_clock(),
        )
        with self._lock:
            self._events.append(record)
        return record


class SandboxExecutionAdapter:
    """Lease-fenced bridge from ExecutionWorker to SandboxChannelAdapter."""

    def __init__(
        self,
        adapter: SandboxChannelAdapter,
        authorization_service: LedgerExecutionAuthorizationService,
    ) -> None:
        self.adapter = adapter
        self.authorization_service = authorization_service
        self.call_count = 0

    def execute(self, command: ExecutionCommand) -> ExecutionResult:
        raise ExecutionBoundaryDenied(
            "sandbox execution requires claimed execution context"
        )

    def execute_claimed(
        self,
        command: ExecutionCommand,
        context: ClaimedExecutionContext,
    ) -> ExecutionResult:
        self.call_count += 1
        if (
            command.execution_id != context.execution_id
            or command.decision_id != context.decision_id
        ):
            return self._denied("SANDBOX_EXECUTION_CONTEXT_MISMATCH")
        try:
            authorized = self.authorization_service.issue(
                execution_id=context.execution_id,
                worker_id=context.worker_id,
                execution_lease_token=context.lease_token,
            )
            if (
                authorized.authorization.approval_id != context.approval_id
                or authorized.authorization.approved_by != context.approved_by
                or authorized.message.content != command.proposed_content
                or authorized.message.idempotency_key != command.idempotency_key
            ):
                return self._denied("SANDBOX_EXECUTION_CONTEXT_MISMATCH")
            receipt = self.adapter.send_message(authorized)
        except ExecutionBoundaryDenied:
            return self._denied("SANDBOX_SEND_AUTHORIZATION_DENIED")
        except ManagedChannelUnavailable:
            return self._denied("SANDBOX_CHANNEL_UNAVAILABLE")
        return ExecutionResult(
            outcome=receipt.outcome,
            external_reference=receipt.external_message_id,
            error_code=receipt.error_code,
            details={
                "mode": "SANDBOX_CONTROLLED_EXECUTION",
                "channel_receipt_id": receipt.receipt_id,
                "approval_id": authorized.authorization.approval_id,
                "human_approved": True,
                "automatic_reply": False,
                "real_channel_called": False,
                "customer_message_sent": False,
                "sandbox_adapter_version": SANDBOX_ADAPTER_VERSION,
            },
        )

    @staticmethod
    def _denied(error_code: str) -> ExecutionResult:
        return ExecutionResult(
            outcome=ReceiptOutcome.FAILED,
            error_code=error_code,
            details={
                "mode": "SANDBOX_CONTROLLED_EXECUTION",
                "human_approved": False,
                "automatic_reply": False,
                "real_channel_called": False,
                "customer_message_sent": False,
            },
        )


class SandboxScenarioController:
    """Coordinates adapter and dependency faults through public runtime APIs."""

    def __init__(
        self,
        *,
        adapter: SandboxChannelAdapter,
        manager: ChannelInstanceManager,
        instance_id: str,
        clock: SandboxClock,
        browser_probe: SandboxDependencyProbe,
    ) -> None:
        self.adapter = adapter
        self.manager = manager
        self.instance_id = instance_id
        self.clock = clock
        self.browser_probe = browser_probe

    def expire_session(self) -> ChannelInstanceView:
        view = self.manager.view(self.instance_id)
        session = view.session
        if (
            session is None
            or session.status is not ChannelSessionStatus.CONNECTED
            or session.expires_at is None
        ):
            raise ValueError("sandbox requires a connected expiring session")
        expires_at = session.expires_at
        now = self.clock()
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        self.clock.advance(
            max(
                timedelta(microseconds=1),
                expires_at - now + timedelta(microseconds=1),
            )
        )
        self.adapter.session_expired()
        return self.manager.heartbeat_instance(self.instance_id)

    def disconnect_browser(self) -> None:
        self.browser_probe.disconnect("SANDBOX_BROWSER_DISCONNECTED")
        self.adapter.browser_disconnected()

    def recover_browser(self) -> bool:
        return self.browser_probe.recover("SANDBOX_BROWSER_RECOVERED")

    def recover_channel(self) -> ChannelInstanceView:
        return self.manager.recover_instance(self.instance_id)


__all__ = [
    "SANDBOX_ADAPTER_VERSION",
    "SandboxAckFailure",
    "SandboxChannelAdapter",
    "SandboxClock",
    "SandboxDependencyProbe",
    "SandboxEventRecord",
    "SandboxEventType",
    "SandboxExecutionAdapter",
    "SandboxGateway",
    "SandboxGatewayTimeout",
    "SandboxScenarioController",
]
