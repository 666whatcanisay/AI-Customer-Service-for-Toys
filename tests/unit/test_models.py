from __future__ import annotations

import pytest
from pydantic import ValidationError

from channel_engine.models import (
    Conversation,
    Decision,
    DecisionAction,
    DecisionState,
    Execution,
    ExecutionState,
    Message,
    MessageState,
)


def test_domain_models_have_stable_prefixed_ids() -> None:
    conversation = Conversation(channel_name="fake", external_ref="conversation-1")
    message = Message(
        conversation_id=conversation.conversation_id,
        external_message_id="message-1",
        content="hello",
    )
    decision = Decision(
        conversation_id=conversation.conversation_id,
        message_id=message.message_id,
        action=DecisionAction.SUGGEST_REPLY,
        proposed_content="proposal",
        gateway_version="fake.v1",
    )
    execution = Execution(
        decision_id=decision.decision_id,
        approval_id="approval-1",
        idempotency_key="execute-1",
    )

    assert conversation.conversation_id.startswith("conv-")
    assert message.message_id.startswith("msg-")
    assert decision.decision_id.startswith("decision-")
    assert execution.execution_id.startswith("execution-")
    assert message.state is MessageState.RECEIVED
    assert decision.state is DecisionState.CREATED
    assert execution.state is ExecutionState.PENDING


def test_message_rejects_empty_content() -> None:
    with pytest.raises(ValidationError):
        Message(
            conversation_id="conv-1",
            external_message_id="message-1",
            content="",
        )


def test_models_are_immutable() -> None:
    conversation = Conversation(channel_name="fake", external_ref="conversation-1")
    with pytest.raises(ValidationError):
        conversation.status = "CLOSED"  # type: ignore[misc]
