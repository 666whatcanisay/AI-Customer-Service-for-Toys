from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from channel_engine.channel import (
    AdapterHealthStatus,
    AdapterLifecycleState,
    AuthorizedOutboundMessage,
    ChannelAdapterV1,
    ChannelCapabilities,
    ChannelManager,
    ChannelMessageConflict,
    ChannelMessageV1,
    ExecutionBoundaryDenied,
    ExecutionSendAuthorization,
    FakeChannelAdapter,
    FakeChannelInbound,
    OutboundMessage,
)
from channel_engine.models import ReceiptOutcome


NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)


class FakeLedgerVerifier:
    def __init__(self) -> None:
        self.call_count = 0

    def verify(self, command: AuthorizedOutboundMessage) -> None:
        self.call_count += 1
        if command.authorization.expires_at <= NOW:
            raise ExecutionBoundaryDenied("authorization expired")


def inbound(**updates: object) -> FakeChannelInbound:
    values: dict[str, object] = {
        "message_id": "message-1",
        "conversation_id": "conversation-1",
        "sender": "customer-1",
        "content": "synthetic customer question",
        "timestamp": NOW,
    }
    values.update(updates)
    return FakeChannelInbound.model_validate(values)


def authorized_command() -> AuthorizedOutboundMessage:
    message = OutboundMessage(
        channel="fake",
        conversation_id="conversation-1",
        execution_id="execution-1",
        approved_by="human-operator",
        content="approved synthetic reply",
        idempotency_key="send-execution-1",
        requested_at=NOW,
    )
    authorization = ExecutionSendAuthorization(
        authorization_id="authorization-1",
        decision_id="decision-1",
        approval_id="approval-1",
        execution_id="execution-1",
        approved_by="human-operator",
        worker_id="worker-1",
        execution_lease_token="fake-lease-reference",
        issued_at=NOW,
        expires_at=NOW + timedelta(minutes=1),
    )
    return AuthorizedOutboundMessage(message=message, authorization=authorization)


def test_channel_adapter_v1_interface_and_lifecycle() -> None:
    adapter = FakeChannelAdapter()

    assert isinstance(adapter, ChannelAdapterV1)
    assert adapter.lifecycle_state is AdapterLifecycleState.DISCONNECTED
    assert adapter.connect().lifecycle is AdapterLifecycleState.CONNECTED
    assert adapter.health_check().status is AdapterHealthStatus.HEALTHY
    assert adapter.disconnect().lifecycle is AdapterLifecycleState.DISCONNECTED
    assert adapter.health_check().real_platform_connected is False
    assert not hasattr(adapter, "generate_reply")


def test_message_normalization_is_store_aware_and_runtime_compatible() -> None:
    adapter = FakeChannelAdapter(channel="fake", store_id="store-001")
    normalized = adapter.normalize_message(inbound())

    assert normalized == ChannelMessageV1(
        message_id="message-1",
        channel="fake",
        store_id="store-001",
        conversation_id="conversation-1",
        sender="customer-1",
        content="synthetic customer question",
        timestamp=NOW,
    )
    runtime_message = normalized.to_runtime_message()
    assert runtime_message.external_message_id == normalized.message_id
    assert runtime_message.channel == normalized.channel
    assert runtime_message.content == normalized.content
    with pytest.raises(ValidationError):
        ChannelMessageV1(
            message_id="message-2",
            channel="fake",
            store_id="store-001",
            conversation_id="conversation-1",
            sender="customer-1",
            content="message",
            timestamp=datetime(2026, 8, 4, 12, 0),
        )


def test_batch_receive_deduplicates_and_conflicts_fail_closed() -> None:
    adapter = FakeChannelAdapter()
    adapter.connect()
    first = inbound()
    second = inbound(message_id="message-2", content="second")

    assert adapter.enqueue_message(first) is True
    assert adapter.enqueue_message(first) is False
    assert adapter.enqueue_message(second) is True
    assert [item.message_id for item in adapter.receive_messages(limit=2)] == [
        "message-1",
        "message-2",
    ]
    assert adapter.receive_messages() == ()
    with pytest.raises(ChannelMessageConflict):
        adapter.enqueue_message(first.model_copy(update={"content": "changed"}))


def test_capabilities_are_versioned_immutable_and_fail_closed() -> None:
    receive_only = FakeChannelAdapter()
    assert receive_only.capabilities == ChannelCapabilities(
        message_receive=True,
        send_message=False,
        image=False,
        order_query=False,
    )
    with pytest.raises(ValidationError):
        receive_only.capabilities.send_message = True  # type: ignore[misc]

    verifier = FakeLedgerVerifier()
    controlled = FakeChannelAdapter(authorization_verifier=verifier)
    assert controlled.capabilities.send_message is True
    controlled.connect()
    controlled.enqueue_message(inbound())
    controlled.receive_messages()

    with pytest.raises(ExecutionBoundaryDenied, match="bare outbound"):
        controlled.send_message(authorized_command().message)  # type: ignore[arg-type]

    receipt = controlled.send_message(authorized_command())
    replay = controlled.send_message(authorized_command())
    assert receipt == replay
    assert receipt.outcome is ReceiptOutcome.SUCCESS
    assert receipt.details["real_platform_called"] is False
    assert receipt.details["customer_message_sent"] is False
    assert verifier.call_count == 2
    assert controlled.send_call_count == 1


def test_channel_manager_registers_starts_stops_and_reports_capability() -> None:
    manager = ChannelManager()
    adapter = FakeChannelAdapter()

    assert manager.register(adapter) is True
    assert manager.register(adapter) is False
    assert manager.registered_channels() == ("fake",)
    assert manager.status().overall is AdapterHealthStatus.UNHEALTHY

    started = manager.start_all()
    assert started.overall is AdapterHealthStatus.HEALTHY
    assert started.connected_count == 1
    assert started.adapters[0].capabilities.message_receive is True
    assert manager.get("fake") is adapter

    stopped = manager.stop_all()
    assert stopped.overall is AdapterHealthStatus.UNHEALTHY
    assert adapter.lifecycle_state is AdapterLifecycleState.DISCONNECTED


def test_adapter_recovery_exposes_recovering_boundary() -> None:
    manager = ChannelManager()
    adapter = FakeChannelAdapter(failed_recovery_attempts=1)
    manager.register(adapter)
    manager.start_all()
    adapter.simulate_degraded()

    first = manager.recover_adapter("fake")
    second = manager.recover_adapter("fake")

    assert first.lifecycle is AdapterLifecycleState.DEGRADED
    assert first.reason_code == "FAKE_ADAPTER_RECOVERY_FAILED"
    assert second.lifecycle is AdapterLifecycleState.CONNECTED
    assert second.reason_code == "FAKE_ADAPTER_RECOVERED"
    assert adapter.recovery_count == 2
    assert AdapterLifecycleState.RECOVERING in adapter.transition_history
    assert adapter.transition_history[:3] == (
        AdapterLifecycleState.DISCONNECTED,
        AdapterLifecycleState.STARTING,
        AdapterLifecycleState.CONNECTED,
    )
