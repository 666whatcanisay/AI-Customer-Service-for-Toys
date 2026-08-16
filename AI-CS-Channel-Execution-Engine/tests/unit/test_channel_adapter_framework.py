from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from channel_engine.channel import (
    AdapterAlreadyRegistered,
    AdapterHealthStatus,
    AdapterNotRegistered,
    AdapterRegistry,
    ChannelAdapter,
    ChannelAdapterUnavailable,
    ChannelConversationNotFound,
    ChannelIdempotencyConflict,
    FakePDDAdapter,
    FakePDDInboundMessage,
    NormalizedMessage,
    OutboundMessage,
)
from channel_engine.models import ReceiptOutcome


NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)


def inbound_message(**updates: object) -> FakePDDInboundMessage:
    values: dict[str, object] = {
        "chat_id": "fake-chat-1",
        "message_id": "fake-message-1",
        "buyer_id": "fake-buyer-1",
        "body": "Where is my order?",
        "created_at": NOW,
    }
    values.update(updates)
    return FakePDDInboundMessage.model_validate(values)


def outbound_message(**updates: object) -> OutboundMessage:
    values: dict[str, object] = {
        "channel": "fake-pdd",
        "conversation_id": "fake-chat-1",
        "execution_id": "execution-1",
        "approved_by": "human-operator",
        "content": "This is a simulated approved reply.",
        "idempotency_key": "send-execution-1",
        "requested_at": NOW,
    }
    values.update(updates)
    return OutboundMessage.model_validate(values)


def prepare_adapter(**kwargs: object) -> FakePDDAdapter:
    adapter = FakePDDAdapter(**kwargs)
    assert adapter.enqueue_customer_message(inbound_message()) is True
    return adapter


def test_fake_pdd_receive_normalizes_platform_message_and_conversation() -> None:
    adapter = FakePDDAdapter()
    raw = inbound_message()

    assert isinstance(adapter, ChannelAdapter)
    assert adapter.enqueue_customer_message(raw) is True
    assert adapter.pending_count == 1

    message = adapter.receive_message()

    assert message == NormalizedMessage(
        channel="fake-pdd",
        conversation_id="fake-chat-1",
        external_message_id="fake-message-1",
        sender="fake-buyer-1",
        content="Where is my order?",
        timestamp=NOW,
    )
    assert adapter.receive_message() is None
    conversation = adapter.get_conversation("fake-chat-1")
    assert conversation is not None
    assert conversation.participant_ids == ("fake-buyer-1",)
    assert conversation.message_count == 1
    assert conversation.last_message_at == NOW


def test_fake_pdd_inbound_message_is_idempotent_and_conflicts_fail_closed() -> None:
    adapter = FakePDDAdapter()
    raw = inbound_message()

    assert adapter.enqueue_customer_message(raw) is True
    assert adapter.enqueue_customer_message(raw) is False
    assert adapter.pending_count == 1

    with pytest.raises(ChannelIdempotencyConflict):
        adapter.enqueue_customer_message(
            raw.model_copy(update={"body": "different content"})
        )
    assert adapter.pending_count == 1


def test_fake_pdd_send_returns_immutable_idempotent_fake_receipt() -> None:
    adapter = prepare_adapter()
    command = outbound_message()

    first = adapter.send_message(command)
    replay = adapter.send_message(command)

    assert replay == first
    assert adapter.send_call_count == 1
    assert first.outcome is ReceiptOutcome.SUCCESS
    assert first.execution_id == "execution-1"
    assert first.external_message_id is not None
    assert first.details["real_platform_called"] is False
    assert first.details["customer_message_sent"] is False
    assert first.details["simulated_reply_recorded"] is True
    assert adapter.sent_receipts == [first]
    with pytest.raises(ValidationError):
        first.outcome = ReceiptOutcome.FAILED  # type: ignore[misc]

    with pytest.raises(ChannelIdempotencyConflict):
        adapter.send_message(command.model_copy(update={"content": "changed reply"}))
    assert adapter.send_call_count == 1


@pytest.mark.parametrize(
    ("outcome", "error_code"),
    [
        (ReceiptOutcome.FAILED, "FAKE_PDD_SEND_FAILED"),
        (ReceiptOutcome.UNKNOWN, "FAKE_PDD_SEND_UNKNOWN"),
    ],
)
def test_fake_pdd_send_supports_failed_and_unknown_receipts(
    outcome: ReceiptOutcome, error_code: str
) -> None:
    adapter = prepare_adapter(send_outcome=outcome)

    receipt = adapter.send_message(outbound_message())

    assert receipt.outcome is outcome
    assert receipt.error_code == error_code
    assert receipt.external_message_id is None
    assert receipt.details["customer_message_sent"] is False


def test_fake_pdd_send_requires_known_conversation_and_human_provenance() -> None:
    adapter = FakePDDAdapter()
    with pytest.raises(ChannelConversationNotFound):
        adapter.send_message(outbound_message())
    with pytest.raises(ValidationError):
        outbound_message(approved_by="   ")
    with pytest.raises(ValueError, match="does not match"):
        prepare_adapter().send_message(outbound_message(channel="another-channel"))


def test_fake_pdd_adapter_exposes_fail_closed_exceptions_and_health() -> None:
    receive_broken = prepare_adapter(receive_unavailable=True)
    with pytest.raises(ChannelAdapterUnavailable):
        receive_broken.receive_message()

    send_broken = prepare_adapter(send_unavailable=True)
    with pytest.raises(ChannelAdapterUnavailable):
        send_broken.send_message(outbound_message())

    unhealthy = FakePDDAdapter(healthy=False).health_check()
    assert unhealthy.status is AdapterHealthStatus.UNHEALTHY
    assert unhealthy.real_platform_connected is False
    assert unhealthy.details["real_pdd_connected"] is False


def test_registry_registers_discovers_and_checks_health() -> None:
    registry = AdapterRegistry()
    adapter = FakePDDAdapter()

    assert registry.register(adapter) is True
    assert registry.register(adapter) is False
    assert registry.discover() == ("fake-pdd",)
    assert registry.get("fake-pdd") is adapter
    health = registry.health_check()
    assert health["fake-pdd"].status is AdapterHealthStatus.HEALTHY
    assert health["fake-pdd"].real_platform_connected is False

    with pytest.raises(AdapterAlreadyRegistered):
        registry.register(FakePDDAdapter())
    with pytest.raises(AdapterNotRegistered):
        registry.get("missing-channel")


def test_registry_isolates_adapter_health_exception() -> None:
    class BrokenHealthAdapter(FakePDDAdapter):
        channel = "broken-fake"

        def health_check(self):  # type: ignore[no-untyped-def]
            raise RuntimeError("synthetic health failure")

    registry = AdapterRegistry()
    registry.register(FakePDDAdapter())
    registry.register(BrokenHealthAdapter())

    report = registry.health_check()

    assert report["fake-pdd"].status is AdapterHealthStatus.HEALTHY
    assert report["broken-fake"].status is AdapterHealthStatus.UNHEALTHY
    assert report["broken-fake"].details == {"error_type": "RuntimeError"}


def test_normalized_message_rejects_missing_timezone_and_blank_content() -> None:
    with pytest.raises(ValidationError):
        NormalizedMessage(
            channel="fake-pdd",
            conversation_id="chat-1",
            external_message_id="message-1",
            sender="buyer-1",
            content="message",
            timestamp=datetime(2026, 8, 4, 12, 0),
        )
    with pytest.raises(ValidationError):
        NormalizedMessage(
            channel="fake-pdd",
            conversation_id="chat-1",
            external_message_id="message-1",
            sender="buyer-1",
            content="   ",
            timestamp=NOW,
        )
