from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from channel_engine.channel import (
    FakePDDWebSocketServer,
    PDDWebSocketConflict,
    PDDWebSocketConnectionError,
    PDDWebSocketConnectionState,
    PDDWebSocketEvent,
    PDDWebSocketEventParser,
    PDDWebSocketInboxState,
    PDDWebSocketMessagePayload,
    PDDWebSocketMissedSequence,
    PDDWebSocketProtocolError,
    PDDWebSocketSyncState,
    PDDWebSocketTransport,
    PDDWebSocketTransportPort,
    SqlAlchemyPDDWebSocketStore,
)
from channel_engine.storage.orm import PDDWebSocketInboxRow


STREAM_ID = "pdd-websocket:synthetic-account"


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 8, 4, 22, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


def event(
    sequence: int,
    message_id: str,
    *,
    content: str | None = None,
    conversation_id: str = "synthetic-websocket-conversation",
) -> PDDWebSocketEvent:
    return PDDWebSocketEvent(
        sequence=sequence,
        cursor=f"cursor-{sequence}",
        message_id=message_id,
        conversation_id=conversation_id,
        sender="synthetic-websocket-customer",
        timestamp=datetime(2026, 8, 4, 22, 0, tzinfo=timezone.utc)
        + timedelta(seconds=sequence),
        payload=PDDWebSocketMessagePayload(
            content=content or f"synthetic payload {message_id}",
            attributes={"source": "fake-server"},
        ),
    )


def build_transport(foundation, clock: Clock, server: FakePDDWebSocketServer):
    store = SqlAlchemyPDDWebSocketStore(foundation["session_factory"])
    transport = PDDWebSocketTransport(
        server.client(),
        store,
        PDDWebSocketEventParser(),
        stream_id=STREAM_ID,
        heartbeat_interval=timedelta(seconds=15),
        heartbeat_timeout_seconds=3.0,
        receive_timeout_seconds=2.0,
        clock=clock,
    )
    assert isinstance(transport, PDDWebSocketTransportPort)
    return store, transport


def test_fake_server_lifecycle_pipeline_and_persist_before_ack(foundation) -> None:
    clock = Clock()
    server = FakePDDWebSocketServer(clock=clock)
    store, transport = build_transport(foundation, clock, server)
    server.enqueue_event(event(10, "message-10"), ack_token="ack-message-10")

    connected = transport.connect()
    assert connected.state is PDDWebSocketConnectionState.CONNECTED
    heartbeat = transport.heartbeat()
    assert heartbeat.healthy is True
    assert heartbeat.state is PDDWebSocketConnectionState.HEALTHY
    assert server.ping_timeouts == [3.0]

    message = transport.receive()
    assert message is not None
    assert message.channel == "pdd"
    assert message.conversation_id == "synthetic-websocket-conversation"
    assert message.external_message_id == "message-10"
    assert message.sender == "synthetic-websocket-customer"
    assert message.content == "synthetic payload message-10"
    assert server.receive_timeouts == [2.0]
    assert server.ack_history == []
    checkpoint = store.load_checkpoint(STREAM_ID)
    assert checkpoint.cursor == "cursor-10"
    assert checkpoint.last_sequence == 10
    assert checkpoint.acknowledged_cursor is None
    assert checkpoint.last_acknowledged_sequence == -1
    assert checkpoint.received_count == 1

    receipt = transport.ack(message)
    assert receipt.sequence == 10
    assert receipt.duplicate_ack is False
    assert server.ack_history == ["ack-message-10"]
    checkpoint = store.load_checkpoint(STREAM_ID)
    assert checkpoint.acknowledged_cursor == "cursor-10"
    assert checkpoint.last_acknowledged_sequence == 10
    assert checkpoint.acknowledged_count == 1
    operation_kinds = [entry.split(":", 1)[0] for entry in transport.operation_log]
    assert operation_kinds.index("receive") < operation_kinds.index("persist")
    assert operation_kinds.index("persist") < operation_kinds.index("ack")

    with foundation["session_factory"]() as session:
        row = session.scalar(select(PDDWebSocketInboxRow))
    assert row is not None
    assert row.state == PDDWebSocketInboxState.ACKED.value
    assert transport.disconnect().state is PDDWebSocketConnectionState.DISCONNECTED


def test_heartbeat_interval_timeout_and_automatic_reconnect(foundation) -> None:
    clock = Clock()
    server = FakePDDWebSocketServer(clock=clock)
    _store, transport = build_transport(foundation, clock, server)
    transport.connect()
    assert transport.heartbeat().attempted is True
    assert transport.heartbeat().attempted is False
    assert server.ping_timeouts == [3.0]

    clock.advance(timedelta(seconds=16))
    server.enqueue_heartbeat(False)
    server.enqueue_heartbeat(True)
    recovered = transport.heartbeat()

    assert recovered.healthy is True
    assert recovered.reconnected is True
    assert recovered.state is PDDWebSocketConnectionState.HEALTHY
    assert transport.snapshot().generation == 2
    assert len(server.connect_history) == 2
    assert server.ping_timeouts == [3.0, 3.0, 3.0]


def test_disconnect_then_explicit_reconnect_resumes_receive(foundation) -> None:
    clock = Clock()
    server = FakePDDWebSocketServer(clock=clock)
    _store, transport = build_transport(foundation, clock, server)
    server.enqueue_event(event(1, "message-1"))
    transport.connect()
    transport.heartbeat()
    server.disconnect_next_receive = True

    with pytest.raises(PDDWebSocketConnectionError, match="disconnected"):
        transport.receive()
    assert transport.snapshot().state is PDDWebSocketConnectionState.DEGRADED

    recovered = transport.reconnect()
    assert recovered.state is PDDWebSocketConnectionState.HEALTHY
    received = transport.receive()
    assert received is not None
    assert received.external_message_id == "message-1"
    assert server.connect_history[-1] == (None, -1)


def test_duplicate_is_suppressed_and_changed_payload_fails_closed(
    foundation,
) -> None:
    clock = Clock()
    server = FakePDDWebSocketServer(clock=clock)
    store, transport = build_transport(foundation, clock, server)
    original = event(1, "stable-message")
    server.enqueue_event(original, ack_token="ack-original")
    server.enqueue_event(original, ack_token="ack-duplicate")
    transport.connect()
    transport.heartbeat()

    received = transport.receive()
    assert received is not None
    transport.ack(received)
    assert transport.receive() is None
    checkpoint = store.load_checkpoint(STREAM_ID)
    assert checkpoint.duplicate_count == 1
    assert checkpoint.cursor == "cursor-1"
    assert server.ack_history == ["ack-original", "ack-duplicate"]

    changed = event(1, "stable-message", content="changed synthetic payload")
    server.enqueue_event(changed, ack_token="ack-conflict")
    with pytest.raises(PDDWebSocketConflict, match="changed payload"):
        transport.receive()
    assert transport.snapshot().state is PDDWebSocketConnectionState.FAILED
    failed = store.load_checkpoint(STREAM_ID)
    assert failed.cursor == "cursor-1"
    assert failed.sync_state is PDDWebSocketSyncState.FAILED
    assert failed.last_error_code == "PDD_WEBSOCKET_IDENTITY_REUSED"
    assert "ack-conflict" not in server.ack_history


def test_malformed_payload_and_missed_sequence_are_never_acked(foundation) -> None:
    clock = Clock()
    malformed_server = FakePDDWebSocketServer(clock=clock)
    malformed_store, malformed = build_transport(
        foundation,
        clock,
        malformed_server,
    )
    malformed_server.enqueue_raw("{not-json", ack_token="ack-malformed")
    malformed.connect()
    with pytest.raises(PDDWebSocketProtocolError, match="canonical"):
        malformed.receive()
    assert malformed_store.load_checkpoint(STREAM_ID).last_sequence == -1
    assert malformed_server.ack_history == []

    second_stream = "pdd-websocket:synthetic-gap-account"
    gap_server = FakePDDWebSocketServer(clock=clock)
    gap_store = SqlAlchemyPDDWebSocketStore(foundation["session_factory"])
    gap = PDDWebSocketTransport(
        gap_server.client(),
        gap_store,
        PDDWebSocketEventParser(),
        stream_id=second_stream,
        clock=clock,
    )
    gap_server.enqueue_event(event(1, "message-1"), ack_token="ack-1")
    gap_server.enqueue_event(event(3, "message-3"), ack_token="ack-3")
    gap.connect()
    first = gap.receive()
    assert first is not None
    gap.ack(first)
    with pytest.raises(PDDWebSocketMissedSequence, match="gap"):
        gap.receive()
    checkpoint = gap_store.load_checkpoint(second_stream)
    assert checkpoint.cursor == "cursor-1"
    assert checkpoint.last_sequence == 1
    assert checkpoint.last_error_code == "PDD_WEBSOCKET_SEQUENCE_GAP"
    assert gap_server.ack_history == ["ack-1"]


def test_ack_must_follow_persisted_sequence_order(foundation) -> None:
    clock = Clock()
    server = FakePDDWebSocketServer(clock=clock)
    _store, transport = build_transport(foundation, clock, server)
    server.enqueue_event(event(10, "message-10"), ack_token="ack-10")
    server.enqueue_event(event(11, "message-11"), ack_token="ack-11")
    transport.connect()
    unpersisted = PDDWebSocketEventParser.normalize(event(99, "not-persisted"))
    with pytest.raises(PDDWebSocketConflict, match="persisted inbox"):
        transport.ack(unpersisted)
    assert server.ack_history == []
    first = transport.receive()
    second = transport.receive()
    assert first is not None and second is not None

    with pytest.raises(PDDWebSocketConflict, match="sequence order"):
        transport.ack(second)
    assert server.ack_history == []
    transport.ack(first)
    transport.ack(second)
    assert server.ack_history == ["ack-10", "ack-11"]


def test_cursor_and_unacknowledged_inbox_recover_across_transport_restart(
    foundation,
) -> None:
    clock = Clock()
    server = FakePDDWebSocketServer(clock=clock)
    store, first_transport = build_transport(foundation, clock, server)
    server.enqueue_event(event(10, "message-10"), ack_token="ack-10")
    first_transport.connect()
    first_delivery = first_transport.receive()
    assert first_delivery is not None
    assert store.load_checkpoint(STREAM_ID).last_acknowledged_sequence == -1
    first_transport.disconnect()

    replacement_store, replacement = build_transport(foundation, clock, server)
    replacement.connect()
    assert server.connect_history[-1] == (None, -1)
    redelivered = replacement.receive()
    assert redelivered is not None
    assert redelivered.external_message_id == "message-10"
    replacement.ack(redelivered)
    replacement.disconnect()

    server.enqueue_event(event(11, "message-11"), ack_token="ack-11")
    final_store, final_transport = build_transport(foundation, clock, server)
    final_transport.connect()
    assert server.connect_history[-1] == ("cursor-10", 10)
    next_message = final_transport.receive()
    assert next_message is not None
    assert next_message.external_message_id == "message-11"
    assert final_store.load_checkpoint(STREAM_ID).last_sequence == 11
    assert replacement_store.load_checkpoint(STREAM_ID).duplicate_count == 1
