from __future__ import annotations

from channel_engine.channel import ChannelMessage, FakeChannel
from channel_engine.gateway import DecisionRequest, FakeGateway
from channel_engine.models import DecisionAction


def test_fake_gateway_is_deterministic_and_requires_approval() -> None:
    gateway = FakeGateway()
    response = gateway.decide(
        DecisionRequest(
            conversation_id="conv-1",
            message_id="msg-1",
            customer_message="Where is my order?",
        )
    )

    assert response.action is DecisionAction.SUGGEST_REPLY
    assert response.requires_approval is True
    assert response.gateway_version == "fake-gateway.v1"
    assert response.metadata["real_ai_cs_called"] is False
    assert "Where is my order?" in (response.proposed_content or "")
    assert gateway.call_count == 1


def test_fake_channel_is_fifo() -> None:
    channel = FakeChannel()
    first = ChannelMessage(
        channel_name="fake",
        conversation_external_ref="conversation-1",
        external_message_id="message-1",
        text="first",
    )
    second = first.model_copy(
        update={"external_message_id": "message-2", "text": "second"}
    )
    channel.enqueue(first)
    channel.enqueue(second)

    assert channel.pending_count == 2
    assert channel.receive() == first
    assert channel.receive() == second
    assert channel.receive() is None
