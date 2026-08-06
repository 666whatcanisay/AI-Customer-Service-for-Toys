from __future__ import annotations

from datetime import datetime, timezone

from channel_engine.channel import FakeChannelAdapter, FakeChannelInbound
from channel_engine.conversation import ConversationService
from channel_engine.execution import ExecutionCoordinator, ExecutionWorker, FakeExecutionAdapter
from channel_engine.models import DecisionState, ExecutionState, ReceiptOutcome
from channel_engine.policy import ApprovalPolicy


def test_fake_adapter_conversation_decision_approval_execution_receipt(
    foundation,
) -> None:
    adapter = FakeChannelAdapter(channel="fake", store_id="fake-store")
    adapter.connect()
    adapter.enqueue_message(
        FakeChannelInbound(
            message_id="foundation-message-1",
            conversation_id="foundation-conversation-1",
            sender="fake-customer",
            content="synthetic question for adapter foundation",
            timestamp=datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc),
        )
    )
    batch = adapter.receive_messages()
    assert len(batch) == 1

    intake = ConversationService(
        foundation["uow_factory"], foundation["gateway"]
    ).receive(batch[0].to_runtime_message())
    assert intake.decision_state is DecisionState.WAITING_APPROVAL
    assert adapter.send_call_count == 0

    enqueued = ExecutionCoordinator(
        foundation["uow_factory"], ApprovalPolicy()
    ).approve_and_enqueue(intake.decision_id, "human-operator")
    execution_adapter = FakeExecutionAdapter(outcome=ReceiptOutcome.SUCCESS)
    result = ExecutionWorker(
        foundation["uow_factory"], execution_adapter, "adapter-foundation-worker"
    ).run_once()

    assert result is not None
    assert result.execution_id == enqueued.execution_id
    assert result.execution_state is ExecutionState.SUCCESS
    assert result.receipt_id is not None
    assert adapter.send_call_count == 0
    assert execution_adapter.call_count == 1
    with foundation["uow_factory"]() as uow:
        receipt = uow.require_repository().get_receipt_for_execution(
            enqueued.execution_id
        )
    assert receipt is not None
    assert receipt.details["customer_message_sent"] is False
