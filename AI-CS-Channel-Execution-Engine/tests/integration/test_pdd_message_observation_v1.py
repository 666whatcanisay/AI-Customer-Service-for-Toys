from __future__ import annotations

from datetime import datetime, timedelta, timezone
from itertools import count

import pytest
from sqlalchemy import select

from channel_engine.conversation import ConversationService
from channel_engine.gateway.integration import (
    FakeGatewayTokenProvider,
    GatewayClient,
    GatewayServiceIdentity,
    MockAICSGateway,
    MockAICSGatewayTransport,
)
from channel_engine.pdd_adapter import (
    FakePDDMessageReader,
    PDDCapturedMessage,
    PDDMessageObservationError,
    PDDMessageObservationPolicy,
    PDDMessageObservationRuntime,
    PDDMessageReaderState,
    PDDObservationDisposition,
    PDDPrivacyCategory,
)
from channel_engine.storage.orm import ApprovalRow, DecisionRow, ExecutionRow, MessageRow, ReceiptRow


NOW = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)
SECRET = b"pdd-message-observation-secret-32"
IDENTITY = GatewayServiceIdentity(
    client_id="channel-engine",
    key_id="pdd-message-observation-key",
    credential_ref="vault://ai-cs/pdd-message-observation/key",
)


def build_runtime(foundation, reader: FakePDDMessageReader):
    server = MockAICSGateway(
        {(IDENTITY.client_id, IDENTITY.key_id): SECRET},
        clock=lambda: NOW,
    )
    nonce = count(1)
    gateway = GatewayClient(
        MockAICSGatewayTransport(server),
        IDENTITY,
        FakeGatewayTokenProvider(
            {IDENTITY.credential_ref: (IDENTITY.key_id, SECRET)},
            clock=lambda: NOW,
        ),
        clock=lambda: NOW,
        nonce_factory=lambda: f"pddmessage{next(nonce):016d}",
        sleeper=lambda _delay: None,
    )
    runtime = PDDMessageObservationRuntime(
        reader,
        ConversationService(foundation["uow_factory"], gateway),
        foundation["uow_factory"],
        policy=PDDMessageObservationPolicy(
            delay_warning_seconds=30.0,
            maximum_message_age_seconds=300.0,
            maximum_future_skew_seconds=30.0,
        ),
        clock=lambda: NOW,
    )
    return runtime, server


def message(
    *,
    external_message_id: str = "pdd-message-001",
    content: str = "我叫张三；手机号13800138000；地址：上海浦东新区；卡号6222020202020202；什么时候发货？",
    timestamp: datetime = NOW,
) -> PDDCapturedMessage:
    return PDDCapturedMessage(
        store_id="pdd-store-001",
        conversation_id="pdd-conversation-001",
        external_message_id=external_message_id,
        sender="张三",
        content=content,
        timestamp=timestamp,
        captured_at=NOW,
    )


def persisted_rows(foundation):
    with foundation["session_factory"]() as session:
        return {
            "messages": list(session.scalars(select(MessageRow))),
            "decisions": list(session.scalars(select(DecisionRow))),
            "approvals": list(session.scalars(select(ApprovalRow))),
            "executions": list(session.scalars(select(ExecutionRow))),
            "receipts": list(session.scalars(select(ReceiptRow))),
        }


def test_observed_message_is_redacted_before_gateway_and_stops_at_waiting_approval(
    foundation,
) -> None:
    reader = FakePDDMessageReader(store_id="pdd-store-001", clock=lambda: NOW)
    reader.enqueue(message())
    runtime, server = build_runtime(foundation, reader)

    evidence = runtime.observe_once()
    rows = persisted_rows(foundation)

    assert len(evidence) == 1
    assert evidence[0].decision_state == "WAITING_APPROVAL"
    assert evidence[0].trace_id == evidence[0].message_id
    assert set(evidence[0].redaction_categories) == {
        PDDPrivacyCategory.NAME,
        PDDPrivacyCategory.PHONE,
        PDDPrivacyCategory.ADDRESS,
        PDDPrivacyCategory.PAYMENT,
    }
    assert len(rows["messages"]) == 1
    assert len(rows["decisions"]) == 1
    assert rows["decisions"][0].state == "WAITING_APPROVAL"
    assert rows["approvals"] == []
    assert rows["executions"] == []
    assert rows["receipts"] == []
    persisted = f"{rows['messages'][0].content}|{rows['decisions'][0].proposed_content}"
    assert "张三" not in persisted
    assert "13800138000" not in persisted
    assert "上海浦东新区" not in persisted
    assert "6222020202020202" not in persisted
    assert server.decision_server.decision_compute_count == 1
    assert runtime.safety_snapshot().execution_created == 0
    assert runtime.safety_snapshot().receipt_created == 0
    assert runtime.safety_snapshot().send_operations == 0


def test_duplicate_message_recovers_idempotently_without_duplicate_decision(
    foundation,
) -> None:
    reader = FakePDDMessageReader(store_id="pdd-store-001", clock=lambda: NOW)
    runtime, server = build_runtime(foundation, reader)
    captured = message(content="普通售前问题，不包含隐私信息")

    reader.enqueue(captured)
    first = runtime.observe_once()[0]
    reader.enqueue(captured)
    duplicate = runtime.observe_once()[0]
    rows = persisted_rows(foundation)

    assert first.disposition is PDDObservationDisposition.ACCEPTED
    assert duplicate.disposition is PDDObservationDisposition.DUPLICATE
    assert duplicate.message_id == first.message_id
    assert duplicate.decision_id == first.decision_id
    assert server.decision_server.decision_compute_count == 1
    assert len(rows["messages"]) == 1
    assert len(rows["decisions"]) == 1
    assert rows["executions"] == []
    assert rows["receipts"] == []

def test_delayed_message_is_marked_and_stale_message_fails_closed(foundation) -> None:
    reader = FakePDDMessageReader(store_id="pdd-store-001", clock=lambda: NOW)
    runtime, server = build_runtime(foundation, reader)
    reader.enqueue(
        message(
            external_message_id="pdd-message-delayed",
            content="延迟到达的售前问题",
            timestamp=NOW - timedelta(seconds=60),
        )
    )

    delayed = runtime.observe_once()[0]

    assert delayed.delayed is True
    assert delayed.latency_seconds == 60.0
    reader.enqueue(
        message(
            external_message_id="pdd-message-stale",
            content="超出窗口的历史问题",
            timestamp=NOW - timedelta(seconds=301),
        )
    )
    with pytest.raises(PDDMessageObservationError) as raised:
        runtime.observe_once()
    assert raised.value.error_code == "PDD_MESSAGE_STALE"
    assert server.decision_server.decision_compute_count == 1
    assert len(persisted_rows(foundation)["messages"]) == 1


def test_expired_session_stops_before_capture_gateway_or_persistence(foundation) -> None:
    reader = FakePDDMessageReader(store_id="pdd-store-001", clock=lambda: NOW)
    reader.enqueue(message(content="不会进入系统的问题"))
    reader.set_state(PDDMessageReaderState.EXPIRED)
    runtime, server = build_runtime(foundation, reader)

    with pytest.raises(PDDMessageObservationError) as raised:
        runtime.observe_once()

    assert raised.value.error_code == "PDD_MESSAGE_READER_SESSION_EXPIRED"
    assert server.decision_server.decision_compute_count == 0
    rows = persisted_rows(foundation)
    assert rows["messages"] == []
    assert rows["decisions"] == []
    assert rows["executions"] == []
    assert rows["receipts"] == []


def test_duplicate_identity_with_different_content_fails_closed(foundation) -> None:
    reader = FakePDDMessageReader(store_id="pdd-store-001", clock=lambda: NOW)
    runtime, server = build_runtime(foundation, reader)
    reader.enqueue(message(content="第一个问题"))
    runtime.observe_once()
    reader.enqueue(message(content="同一消息标识下的不同内容"))

    with pytest.raises(ValueError, match="different content"):
        runtime.observe_once()

    assert server.decision_server.decision_compute_count == 1
    rows = persisted_rows(foundation)
    assert len(rows["messages"]) == 1
    assert len(rows["decisions"]) == 1
    assert rows["executions"] == []
    assert rows["receipts"] == []
