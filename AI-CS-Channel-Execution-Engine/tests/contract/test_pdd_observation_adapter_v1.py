from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from channel_engine.channel import (
    AdapterHealthStatus,
    ChannelAuthenticationScheme,
    ChannelConnectionState,
    ChannelCredentialReference,
    ChannelSessionUnavailable,
    FakeChannelAuthenticationBroker,
    FakePDDObservationTransport,
    NormalizedMessage,
    PDDAdapter,
    PDDObservationAdapter,
    PDDObservationConflict,
    PDDObservationTransport,
    PDDObservationUnavailable,
    PDDObservedMessage,
    PlatformAdapter,
)


class FakeClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current += delta


def credential() -> ChannelCredentialReference:
    return ChannelCredentialReference(
        credential_id="secret-manager/pdd/observation-account",
        provider="secret-manager",
        version="pdd-observe-v1",
        account_ref="pdd-observation-account-ref",
        auth_scheme=ChannelAuthenticationScheme.MANAGED_SESSION,
    )


def observed_message(**updates: object) -> PDDObservedMessage:
    values: dict[str, object] = {
        "platform": "pdd",
        "conversation_id": "pdd-conversation-001",
        "external_message_id": "pdd-message-001",
        "sender": "pdd-buyer-001",
        "content": "请问这个合成商品什么时候发货？",
        "timestamp": datetime(2026, 8, 4, 12, 1, tzinfo=timezone.utc),
    }
    values.update(updates)
    return PDDObservedMessage.model_validate(values)


def build_adapter(
    clock: FakeClock,
    *,
    transport: FakePDDObservationTransport | None = None,
):
    active_transport = transport or FakePDDObservationTransport(clock=clock)
    broker = FakeChannelAuthenticationBroker(clock=clock)
    adapter = PDDAdapter(
        credential(),
        broker,
        active_transport,
        poll_batch_size=20,
        clock=clock,
    )
    return adapter, active_transport, broker


def test_pdd_observation_contract_has_no_outbound_capability() -> None:
    clock = FakeClock()
    adapter, transport, _broker = build_adapter(clock)

    assert isinstance(adapter, PDDObservationAdapter)
    assert isinstance(transport, PDDObservationTransport)
    assert not isinstance(adapter, PlatformAdapter)
    assert not hasattr(adapter, "send_message")
    assert not hasattr(transport, "send")
    assert not hasattr(transport, "refund")
    assert not hasattr(transport, "modify_order")


def test_pdd_message_maps_to_normalized_six_field_model() -> None:
    clock = FakeClock()
    adapter, _transport, _broker = build_adapter(clock)
    raw = observed_message()

    normalized = adapter.map_message(raw)

    assert normalized == NormalizedMessage(
        channel="pdd",
        conversation_id="pdd-conversation-001",
        external_message_id="pdd-message-001",
        sender="pdd-buyer-001",
        content="请问这个合成商品什么时候发货？",
        timestamp=raw.timestamp,
    )
    assert set(normalized.model_dump()) == {
        "channel",
        "conversation_id",
        "external_message_id",
        "sender",
        "content",
        "timestamp",
    }
    with pytest.raises(ValidationError):
        observed_message(timestamp=datetime(2026, 8, 4, 12, 1))
    with pytest.raises(ValidationError):
        observed_message(platform="another-platform")


def test_session_lifecycle_heartbeat_reconnect_health_and_disconnect() -> None:
    clock = FakeClock()
    adapter, transport, broker = build_adapter(clock)

    initial_health = adapter.health_check()
    first_session = adapter.connect()
    replayed_session = adapter.connect()
    heartbeat = adapter.heartbeat()

    assert initial_health.status is AdapterHealthStatus.UNHEALTHY
    assert replayed_session == first_session
    assert transport.open_count == 1
    assert broker.call_count == 1
    assert heartbeat.status.value == "OK"
    assert transport.heartbeat_count == 1
    assert adapter.health_check().status is AdapterHealthStatus.HEALTHY
    assert adapter.health_check().real_platform_connected is False
    assert adapter.health_check().details["send_enabled"] is False
    assert adapter.health_check().details["automatic_reply_enabled"] is False
    assert adapter.lifecycle.connection.state is ChannelConnectionState.CONNECTED

    adapter.disconnect()
    assert adapter.get_session() is None
    assert transport.close_count == 1
    assert adapter.health_check().status is AdapterHealthStatus.UNHEALTHY
    with pytest.raises(ChannelSessionUnavailable):
        adapter.receive_message()

    second_session = adapter.reconnect()
    assert second_session.session_id != first_session.session_id
    assert broker.call_count == 2
    assert transport.open_count == 2
    assert adapter.health_check().status is AdapterHealthStatus.HEALTHY


def test_heartbeat_degradation_requires_reconnect_before_observation() -> None:
    clock = FakeClock()
    transport = FakePDDObservationTransport(clock=clock, healthy=False)
    adapter, _transport, _broker = build_adapter(clock, transport=transport)
    adapter.connect()

    heartbeat = adapter.heartbeat()

    assert heartbeat.status.value == "FAILED"
    assert adapter.health_check().status is AdapterHealthStatus.DEGRADED
    with pytest.raises(ChannelSessionUnavailable):
        adapter.receive_message()

    transport.healthy = True
    adapter.reconnect()
    assert adapter.heartbeat().status.value == "OK"
    assert adapter.health_check().status is AdapterHealthStatus.HEALTHY


def test_receive_is_ordered_cursor_based_and_duplicate_safe() -> None:
    clock = FakeClock()
    adapter, transport, _broker = build_adapter(clock)
    first = observed_message()
    second = observed_message(
        external_message_id="pdd-message-002",
        content="第二条合成观察消息",
    )
    transport.enqueue(first, first, second)
    adapter.connect()

    first_normalized = adapter.receive_message()
    second_normalized = adapter.receive_message()
    exhausted = adapter.receive_message()

    assert first_normalized is not None
    assert first_normalized.external_message_id == "pdd-message-001"
    assert second_normalized is not None
    assert second_normalized.external_message_id == "pdd-message-002"
    assert exhausted is None
    assert adapter.observed_message_count == 2
    assert adapter.duplicate_message_count == 1
    assert adapter.observation_cursor == "fake-pdd-cursor-1"
    assert transport.poll_count == 2
    health = adapter.health_check()
    assert health.details["cursor_present"] is True
    assert health.details["observed_message_count"] == 2
    assert health.details["duplicate_message_count"] == 1


def test_duplicate_message_with_different_content_fails_closed() -> None:
    clock = FakeClock()
    adapter, transport, _broker = build_adapter(clock)
    original = observed_message()
    transport.enqueue(original)
    adapter.connect()
    assert adapter.receive_message() is not None
    original_cursor = adapter.observation_cursor

    transport.enqueue(
        original.model_copy(update={"content": "同一消息ID的冲突内容"})
    )
    with pytest.raises(PDDObservationConflict, match="different content"):
        adapter.receive_message()

    assert adapter.observation_cursor == original_cursor
    assert adapter.observed_message_count == 1
    assert adapter.health_check().status is AdapterHealthStatus.DEGRADED
    assert (
        adapter.health_check().details["last_receive_error"]
        == "PDD_MESSAGE_ID_CONFLICT"
    )


def test_poll_failure_is_visible_as_degraded_health() -> None:
    clock = FakeClock()
    transport = FakePDDObservationTransport(
        clock=clock,
        poll_unavailable=True,
    )
    adapter, _transport, _broker = build_adapter(clock, transport=transport)
    adapter.connect()

    with pytest.raises(PDDObservationUnavailable, match="poll failed"):
        adapter.receive_message()

    health = adapter.health_check()
    assert health.status is AdapterHealthStatus.DEGRADED
    assert health.details["last_receive_error"] == "PDD_OBSERVATION_POLL_FAILED"
    assert health.details["real_pdd_connected"] is False
    assert transport.real_platform_call_count == 0


def test_credential_reference_and_session_are_redacted() -> None:
    clock = FakeClock()
    adapter, _transport, _broker = build_adapter(clock)
    session = adapter.connect()
    combined = (
        adapter.lifecycle.credential.model_dump_json()
        + session.model_dump_json()
        + adapter.health_check().model_dump_json()
    )

    assert "plaintext-pdd-token" not in combined
    for forbidden_key in ('"token"', '"password"', '"cookie"', '"secret"'):
        assert forbidden_key not in combined
    assert adapter.lifecycle.credential.provider == "secret-manager"
