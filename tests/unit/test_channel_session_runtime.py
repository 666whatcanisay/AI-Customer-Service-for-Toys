from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from channel_engine.channel import (
    ChannelMessageV1,
    FakeChannelAdapter,
    FakeChannelInbound,
)
from channel_engine.session import (
    ChannelInstance,
    ChannelInstanceManager,
    ChannelInstanceStatus,
    ChannelSession,
    ChannelSessionStatus,
    ChannelSessionStore,
    CredentialReference,
    CursorGapDetected,
    FakeCredentialProvider,
    InboundEnvelope,
    InvalidSessionTransition,
    MessageDeliveryConflict,
    MessageReliabilityService,
    transition_instance,
    transition_session,
)
from channel_engine.storage.orm import ChannelMessageInboxRow


NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)


class MutableClock:
    def __init__(self) -> None:
        self.current = NOW

    def __call__(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current += delta


def reference(store_id: str = "store-a") -> CredentialReference:
    return CredentialReference(
        credential_ref=f"vault://channels/{store_id}",
        provider="test-vault",
        version="v1",
    )


def message(
    *,
    store_id: str = "store-a",
    message_id: str = "message-1",
    content: str = "synthetic message",
) -> ChannelMessageV1:
    return ChannelMessageV1(
        message_id=message_id,
        channel="fake",
        store_id=store_id,
        conversation_id="conversation-1",
        sender="customer-1",
        content=content,
        timestamp=NOW,
    )


def build_instance_runtime(foundation, *, max_attempts: int = 5):
    clock = MutableClock()
    store = ChannelSessionStore(foundation["uow_factory"])
    credential = reference()
    provider = FakeCredentialProvider((credential,), clock=clock)
    delivery = MessageReliabilityService(
        foundation["uow_factory"],
        store,
        max_delivery_attempts=max_attempts,
        clock=clock,
    )
    manager = ChannelInstanceManager(
        store,
        provider,
        delivery,
        clock=clock,
    )
    adapter = FakeChannelAdapter(
        channel="fake",
        store_id="store-a",
        clock=clock,
    )
    instance = manager.create_instance(
        instance_id="instance-store-a",
        platform="fake",
        store_id="store-a",
        adapter_type="FakeChannelAdapter",
        credential_ref=credential,
        adapter=adapter,
    )
    return clock, store, provider, delivery, manager, adapter, instance


def test_session_and_instance_state_machines_fail_closed() -> None:
    instance = ChannelInstance(
        instance_id="instance-1",
        platform="fake",
        store_id="store-a",
        status=ChannelInstanceStatus.CREATED,
        adapter_type="FakeChannelAdapter",
        created_at=NOW,
        updated_at=NOW,
    )
    session = ChannelSession(
        session_id="session-1",
        instance_id="instance-1",
        status=ChannelSessionStatus.CREATED,
        credential_ref=reference(),
        created_at=NOW,
        updated_at=NOW,
    )

    starting = transition_instance(
        instance, ChannelInstanceStatus.STARTING, NOW
    )
    connected = transition_instance(
        starting, ChannelInstanceStatus.CONNECTED, NOW
    )
    connected_session = transition_session(
        session,
        ChannelSessionStatus.CONNECTED,
        NOW,
        credential_lease_ref="lease-ref://session-1",
        heartbeat_time=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )
    expired = transition_session(
        connected_session,
        ChannelSessionStatus.EXPIRED,
        NOW + timedelta(minutes=6),
        failure_code="LEASE_EXPIRED",
    )

    assert connected.status is ChannelInstanceStatus.CONNECTED
    assert expired.status is ChannelSessionStatus.EXPIRED
    with pytest.raises(InvalidSessionTransition):
        transition_session(expired, ChannelSessionStatus.CONNECTED, NOW)
    with pytest.raises(InvalidSessionTransition):
        transition_instance(instance, ChannelInstanceStatus.CONNECTED, NOW)


@pytest.mark.parametrize(
    "unsafe_ref",
    [
        "vault://entry?token=plaintext",
        "vault://entry?cookie=plaintext",
        "vault://entry?password=plaintext",
        "vault://entry?secret=plaintext",
        "vault://Bearer%20plaintext",
    ],
)
def test_credential_reference_rejects_embedded_secret_material(
    unsafe_ref: str,
) -> None:
    with pytest.raises(ValidationError, match="prohibited secret"):
        CredentialReference(
            credential_ref=unsafe_ref,
            provider="test-vault",
            version="v1",
        )


def test_cursor_persist_redeliver_ack_and_restart_recovery(foundation) -> None:
    _, store, _, delivery, _, _, instance = build_instance_runtime(foundation)
    envelope = InboundEnvelope(
        message=message(),
        source_cursor="source:1",
        source_sequence=1,
    )

    persisted = delivery.persist(instance.instance_id, (envelope,))
    duplicate = delivery.persist(instance.instance_id, (envelope,))
    first = delivery.receive_pending(instance.instance_id)
    second = delivery.receive_pending(instance.instance_id)

    assert persisted[0].duplicate is False
    assert duplicate[0].duplicate is True
    assert first[0].delivery_id == second[0].delivery_id
    assert first[0].delivery_attempt == 1
    assert second[0].delivery_attempt == 2

    replacement = MessageReliabilityService(
        foundation["uow_factory"], store
    )
    recovered = replacement.receive_pending(instance.instance_id)
    assert recovered[0].delivery_id == first[0].delivery_id
    assert recovered[0].delivery_attempt == 3

    ack = replacement.ack(instance.instance_id, recovered[0].delivery_id)
    replay = replacement.ack(instance.instance_id, recovered[0].delivery_id)
    assert replay.ack_id == ack.ack_id
    assert replay.duplicate is True
    assert replacement.receive_pending(instance.instance_id) == ()
    cursor = replacement.get_cursor(instance.instance_id)
    assert cursor.last_sequence == 1
    assert cursor.last_acked_sequence == 1


def test_ack_cursor_advances_only_across_contiguous_messages(foundation) -> None:
    _, _, _, delivery, _, _, instance = build_instance_runtime(foundation)
    delivery.persist(
        instance.instance_id,
        (
            InboundEnvelope(
                message=message(message_id="message-1"),
                source_cursor="source:1",
                source_sequence=1,
            ),
            InboundEnvelope(
                message=message(message_id="message-2"),
                source_cursor="source:2",
                source_sequence=2,
            ),
        ),
    )
    deliveries = delivery.receive_pending(instance.instance_id)

    delivery.ack(instance.instance_id, deliveries[1].delivery_id)
    assert delivery.get_cursor(instance.instance_id).last_acked_sequence == 0
    delivery.ack(instance.instance_id, deliveries[0].delivery_id)
    assert delivery.get_cursor(instance.instance_id).last_acked_sequence == 2


def test_cursor_gap_conflict_and_cross_store_message_are_blocked(foundation) -> None:
    _, _, _, delivery, _, _, instance = build_instance_runtime(foundation)
    with pytest.raises(CursorGapDetected):
        delivery.persist(
            instance.instance_id,
            (
                InboundEnvelope(
                    message=message(),
                    source_cursor="source:2",
                    source_sequence=2,
                ),
            ),
        )
    with pytest.raises(MessageDeliveryConflict, match="store_id"):
        delivery.persist(
            instance.instance_id,
            (
                InboundEnvelope(
                    message=message(store_id="store-b"),
                    source_cursor="source:1",
                    source_sequence=1,
                ),
            ),
        )


def test_retry_marker_is_bounded_and_requires_manual_intervention(foundation) -> None:
    clock, _, _, delivery, _, _, instance = build_instance_runtime(
        foundation, max_attempts=2
    )
    delivery.persist(
        instance.instance_id,
        (
            InboundEnvelope(
                message=message(),
                source_cursor="source:1",
                source_sequence=1,
            ),
        ),
    )
    first = delivery.receive_pending(instance.instance_id)[0]
    marker = delivery.mark_retry(
        instance.instance_id,
        first.delivery_id,
        reason_code="CONVERSATION_TEMPORARY_FAILURE",
        retry_after=timedelta(seconds=1),
    )
    assert delivery.receive_pending(instance.instance_id) == ()
    clock.advance(timedelta(seconds=1))
    second = delivery.receive_pending(instance.instance_id)[0]
    assert second.retry_marker is not None
    assert second.retry_marker.reason_code == marker.reason_code
    assert delivery.receive_pending(instance.instance_id) == ()

    with foundation["uow_factory"]() as uow:
        assert uow.session is not None
        row = uow.session.get(
            ChannelMessageInboxRow,
            {
                "instance_id": instance.instance_id,
                "message_id": "message-1",
            },
        )
        assert row is not None
        assert row.state == "MANUAL_INTERVENTION"
        assert row.retry_reason == "DELIVERY_BUDGET_EXHAUSTED"


def test_source_ack_occurs_only_after_inbox_persistence(foundation) -> None:
    _, _, _, delivery, manager, adapter, instance = build_instance_runtime(foundation)
    manager.start_instance(instance.instance_id)
    adapter.enqueue_message(
        FakeChannelInbound(
            message_id="message-1",
            conversation_id="conversation-1",
            sender="customer-1",
            content="synthetic source delivery",
            timestamp=NOW,
        )
    )

    first = manager.poll_messages(instance.instance_id)

    assert len(first) == 1
    assert adapter.source_ack_count == 1
    assert adapter.pending_count == 0
    assert delivery.get_cursor(instance.instance_id).last_sequence == 1
    assert delivery.get_cursor(instance.instance_id).last_acked_sequence == 0

    redelivery = manager.poll_messages(instance.instance_id)
    assert redelivery[0].delivery_id == first[0].delivery_id
    assert redelivery[0].delivery_attempt == 2
    assert adapter.source_ack_count == 1

    delivery.ack(instance.instance_id, first[0].delivery_id)
    assert manager.poll_messages(instance.instance_id) == ()
