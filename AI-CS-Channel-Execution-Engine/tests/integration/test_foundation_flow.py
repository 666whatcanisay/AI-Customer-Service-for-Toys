from __future__ import annotations

from channel_engine.channel import ChannelMessage
from channel_engine.conversation import ConversationService
from channel_engine.execution import ExecutionCoordinator, ExecutionWorker, FakeExecutor
from channel_engine.models import (
    DecisionState,
    ExecutionState,
    ReceiptOutcome,
    UnknownExecutionRequiresReconciliation,
    assert_not_automatic_retry,
)
from channel_engine.policy import ApprovalPolicy


def test_message_to_receipt_flow_requires_human_approval(foundation) -> None:
    service = ConversationService(foundation["uow_factory"], foundation["gateway"])
    coordinator = ExecutionCoordinator(
        foundation["uow_factory"], ApprovalPolicy()
    )
    worker = ExecutionWorker(
        foundation["uow_factory"], foundation["executor"], "integration-worker"
    )

    intake = service.receive(
        ChannelMessage(
            channel_name="fake-channel",
            conversation_external_ref="customer-conversation-1",
            external_message_id="customer-message-1",
            text="Can you help me with this product?",
        )
    )

    assert intake.decision_state is DecisionState.WAITING_APPROVAL
    assert intake.requires_approval is True
    assert foundation["executor"].call_count == 0

    enqueued = coordinator.approve_and_enqueue(intake.decision_id, "human-operator")

    assert enqueued.execution_state is ExecutionState.PENDING
    assert foundation["executor"].call_count == 0

    outcome = worker.run_once()
    assert outcome is not None
    assert outcome.execution_state is ExecutionState.SUCCESS
    assert outcome.receipt_outcome is ReceiptOutcome.SUCCESS
    assert foundation["executor"].call_count == 1

    with foundation["uow_factory"]() as uow:
        repo = uow.require_repository()
        assert repo.get_decision(intake.decision_id).state is DecisionState.APPROVED
        execution = repo.get_execution(enqueued.execution_id)
        receipt = repo.get_receipt_for_execution(enqueued.execution_id)
        outbox = repo.list_pending_outbox()

    assert execution.state is ExecutionState.SUCCESS
    assert receipt is not None
    assert receipt.outcome is ReceiptOutcome.SUCCESS
    assert receipt.details["real_channel_called"] is False
    assert receipt.details["customer_message_sent"] is False
    assert len(outbox) >= 7
    assert {item.topic for item in outbox} >= {
        "MESSAGE_RECEIVED",
        "DECISION_WAITING_APPROVAL",
        "DECISION_APPROVED",
        "EXECUTION_STARTED",
        "EXECUTION_SUCCEEDED",
        "RECEIPT_RECORDED",
    }


def test_rejection_never_calls_executor(foundation) -> None:
    service = ConversationService(foundation["uow_factory"], foundation["gateway"])
    coordinator = ExecutionCoordinator(
        foundation["uow_factory"], ApprovalPolicy()
    )
    intake = service.receive(
        ChannelMessage(
            channel_name="fake-channel",
            conversation_external_ref="customer-conversation-2",
            external_message_id="customer-message-2",
            text="Please answer",
        )
    )

    rejected = coordinator.reject(intake.decision_id, "human-operator", "not safe")

    assert rejected.decision_state is DecisionState.REJECTED
    assert foundation["executor"].call_count == 0


def test_duplicate_channel_message_is_idempotent(foundation) -> None:
    service = ConversationService(foundation["uow_factory"], foundation["gateway"])
    inbound = ChannelMessage(
        channel_name="fake-channel",
        conversation_external_ref="customer-conversation-idempotent",
        external_message_id="customer-message-idempotent",
        text="same message",
    )

    first = service.receive(inbound)
    second = service.receive(inbound)

    assert second == first
    assert foundation["gateway"].call_count == 1


def test_duplicate_external_message_with_changed_content_is_rejected(foundation) -> None:
    service = ConversationService(foundation["uow_factory"], foundation["gateway"])
    first = ChannelMessage(
        channel_name="fake-channel",
        conversation_external_ref="customer-conversation-conflict",
        external_message_id="customer-message-conflict",
        text="original message",
    )
    service.receive(first)

    try:
        service.receive(first.model_copy(update={"content": "changed message"}))
    except ValueError as exc:
        assert "different content" in str(exc)
    else:
        raise AssertionError("conflicting duplicate message was accepted")


def test_unknown_execution_requires_manual_reconciliation(foundation) -> None:
    unknown_executor = FakeExecutor(outcome=ReceiptOutcome.UNKNOWN)
    service = ConversationService(foundation["uow_factory"], foundation["gateway"])
    coordinator = ExecutionCoordinator(
        foundation["uow_factory"], ApprovalPolicy()
    )
    worker = ExecutionWorker(
        foundation["uow_factory"], unknown_executor, "unknown-worker"
    )
    intake = service.receive(
        ChannelMessage(
            channel_name="fake-channel",
            conversation_external_ref="customer-conversation-3",
            external_message_id="customer-message-3",
            text="Please answer",
        )
    )

    enqueued = coordinator.approve_and_enqueue(intake.decision_id, "human-operator")
    outcome = worker.run_once()
    assert outcome is not None
    assert outcome.execution_state is ExecutionState.UNKNOWN

    with foundation["uow_factory"]() as uow:
        execution = uow.require_repository().get_execution(enqueued.execution_id)

    try:
        assert_not_automatic_retry(execution)
    except UnknownExecutionRequiresReconciliation:
        pass
    else:
        raise AssertionError("UNKNOWN execution was incorrectly treated as retryable")
