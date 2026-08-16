from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from channel_engine.channel import (
    AdapterHealthStatus,
    AdapterLifecycleState,
    CursorAckChannelAdapterV1,
    ExecutionBoundaryDenied,
    SandboxAckFailure,
    SandboxChannelAdapter,
    SandboxClock,
    SandboxEventType,
    SandboxGateway,
    SandboxGatewayTimeout,
)
from channel_engine.gateway import DecisionRequest, FakeGateway
from channel_engine.gateway.contract import CONTRACT_VERSION


NOW = datetime(2026, 8, 4, 14, 0, tzinfo=timezone.utc)


def decision_request() -> DecisionRequest:
    return DecisionRequest(
        contract_version=CONTRACT_VERSION,
        request_id="sandbox-request-1",
        idempotency_key="sandbox-idempotency-1",
        correlation_id="sandbox-correlation-1",
        conversation_id="sandbox-conversation-1",
        message_id="sandbox-message-1",
        customer_message="synthetic sandbox message",
        context={"mode": "SANDBOX"},
        requested_at=NOW,
    )


def test_sandbox_adapter_delay_receive_health_and_lifecycle() -> None:
    clock = SandboxClock(NOW)
    adapter = SandboxChannelAdapter(store_id="store-a", clock=clock)

    assert isinstance(adapter, CursorAckChannelAdapterV1)
    assert adapter.connect().lifecycle is AdapterLifecycleState.CONNECTED
    event = adapter.customer_message_received(
        message_id="message-1",
        conversation_id="conversation-1",
        content="synthetic delayed message",
    )
    adapter.message_delay(timedelta(seconds=5))

    assert event.event_type is SandboxEventType.CUSTOMER_MESSAGE_RECEIVED
    assert adapter.receive_envelopes() == ()
    clock.advance(timedelta(seconds=5))
    envelopes = adapter.receive_envelopes()
    assert len(envelopes) == 1
    assert envelopes[0].source_cursor == "sandbox:1"
    assert envelopes[0].message.store_id == "store-a"

    ack = adapter.acknowledge(envelopes[0].source_cursor)
    assert ack.duplicate is False
    assert adapter.pending_count == 0
    health = adapter.health_check()
    assert health.status is AdapterHealthStatus.HEALTHY
    assert health.real_platform_connected is False
    assert health.details["automatic_send_enabled"] is False

    adapter.customer_message_received(
        message_id="message-2",
        conversation_id="conversation-1",
        content="synthetic receive_messages message",
    )
    batch = adapter.receive_messages()
    assert [item.message_id for item in batch] == ["message-2"]
    assert adapter.pending_count == 0

    assert adapter.disconnect().lifecycle is AdapterLifecycleState.DISCONNECTED


def test_sandbox_rejects_bare_outbound_content() -> None:
    adapter = SandboxChannelAdapter()
    adapter.connect()

    with pytest.raises(ExecutionBoundaryDenied):
        adapter.send_message("bare synthetic text")  # type: ignore[arg-type]

    assert adapter.send_call_count == 0


def test_ack_failure_then_duplicate_source_delivery_is_idempotent() -> None:
    clock = SandboxClock(NOW)
    adapter = SandboxChannelAdapter(clock=clock)
    adapter.connect()
    adapter.customer_message_received(
        message_id="message-ack",
        conversation_id="conversation-ack",
        content="synthetic ACK failure message",
    )
    adapter.ack_failure()
    envelope = adapter.receive_envelopes()[0]

    with pytest.raises(SandboxAckFailure):
        adapter.acknowledge(envelope.source_cursor)

    assert adapter.pending_count == 1
    first_ack = adapter.acknowledge(envelope.source_cursor)
    assert first_ack.duplicate is False
    adapter.message_duplicate("message-ack")
    duplicate = adapter.receive_envelopes()[0]
    replay_ack = adapter.acknowledge(duplicate.source_cursor)

    assert replay_ack.duplicate is True
    assert replay_ack.source_sequence == first_ack.source_sequence
    assert adapter.pending_count == 0
    assert [item.event_type for item in adapter.events] == [
        SandboxEventType.CUSTOMER_MESSAGE_RECEIVED,
        SandboxEventType.ACK_FAILURE,
        SandboxEventType.MESSAGE_DUPLICATE,
    ]


def test_network_and_crash_faults_use_bounded_recovery() -> None:
    adapter = SandboxChannelAdapter(failed_recovery_attempts=1)
    adapter.connect()

    adapter.network_failure()
    assert adapter.health_check().status is AdapterHealthStatus.UNHEALTHY
    assert adapter.recover().lifecycle is AdapterLifecycleState.DEGRADED
    assert adapter.recover().lifecycle is AdapterLifecycleState.CONNECTED

    adapter.adapter_crashed()
    assert adapter.health_check().status is AdapterHealthStatus.UNHEALTHY
    assert adapter.recover().lifecycle is AdapterLifecycleState.CONNECTED
    assert adapter.recovery_count == 3


def test_sandbox_gateway_timeout_is_injected_and_recoverable() -> None:
    gateway = SandboxGateway(FakeGateway())
    gateway.timeout_next()

    with pytest.raises(SandboxGatewayTimeout):
        gateway.decide(decision_request())

    assert gateway.timeout_count == 1
    assert gateway.health_check().available is False
    assert gateway.recover() is True
    response = gateway.decide(decision_request())
    assert response.requires_approval is True
    assert gateway.health_check().available is True
