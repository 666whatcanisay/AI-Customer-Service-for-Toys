from __future__ import annotations

from datetime import datetime, timezone

from channel_engine.channel import FakePDDAdapter, FakePDDInboundMessage
from channel_engine.conversation import ConversationService
from channel_engine.models import DecisionState


def test_fake_pdd_adapter_to_decision_flow_never_auto_sends(foundation) -> None:
    adapter = FakePDDAdapter()
    raw = FakePDDInboundMessage(
        chat_id="adapter-flow-chat",
        message_id="adapter-flow-message",
        buyer_id="adapter-flow-buyer",
        body="Please check my fake order",
        created_at=datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc),
    )
    assert adapter.enqueue_customer_message(raw) is True
    normalized = adapter.receive_message()
    assert normalized is not None

    service = ConversationService(foundation["uow_factory"], foundation["gateway"])
    first = service.receive(normalized)

    assert first.decision_state is DecisionState.WAITING_APPROVAL
    assert first.requires_approval is True
    assert adapter.send_call_count == 0
    assert adapter.sent_receipts == []
    assert foundation["gateway"].call_count == 1
    assert foundation["executor"].call_count == 0

    assert adapter.enqueue_customer_message(raw) is False
    replay = service.receive(adapter.normalize_message(raw))
    assert replay == first
    assert foundation["gateway"].call_count == 1
    assert adapter.send_call_count == 0
