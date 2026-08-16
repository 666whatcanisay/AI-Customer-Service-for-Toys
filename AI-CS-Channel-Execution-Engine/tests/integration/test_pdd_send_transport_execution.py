from __future__ import annotations

import pytest

from channel_engine.channel import (
    FakePDDHTTPSender,
    FakePDDHTTPSenderMode,
    FakePDDSendSessionProvider,
    LedgerExecutionAuthorizationService,
    NormalizedMessage,
    PDDControlledSendExecutionAdapter,
    PDDSendTransport,
)
from channel_engine.conversation import ConversationService
from channel_engine.execution import ExecutionCoordinator, ExecutionWorker
from channel_engine.models import (
    EventType,
    ExecutionState,
    ReceiptOutcome,
)
from channel_engine.models.entities import utc_now
from channel_engine.policy import ApprovalPolicy


def _enqueue_approved_execution(foundation, suffix: str):
    intake = ConversationService(
        foundation["uow_factory"],
        foundation["gateway"],
    ).receive(
        NormalizedMessage(
            channel="pdd",
            conversation_id=f"pdd-send-e2e-conversation-{suffix}",
            external_message_id=f"pdd-send-e2e-message-{suffix}",
            sender="fake-customer",
            content=f"Please create a human-approved reply for {suffix}.",
            timestamp=utc_now(),
        )
    )
    enqueued = ExecutionCoordinator(
        foundation["uow_factory"],
        ApprovalPolicy(),
    ).approve_and_enqueue(intake.decision_id, "pdd-send-e2e-human")
    return intake, enqueued


def _worker(foundation, sender: FakePDDHTTPSender, suffix: str):
    transport = PDDSendTransport(
        LedgerExecutionAuthorizationService(foundation["uow_factory"]),
        FakePDDSendSessionProvider(),
        sender,
    )
    bridge = PDDControlledSendExecutionAdapter(transport)
    worker = ExecutionWorker(
        foundation["uow_factory"],
        bridge,
        f"pdd-send-e2e-worker-{suffix}",
    )
    return transport, bridge, worker


def test_worker_to_fake_http_sender_records_canonical_receipt_event_and_outbox(
    foundation,
) -> None:
    intake, enqueued = _enqueue_approved_execution(foundation, "success")
    sender = FakePDDHTTPSender()
    transport, bridge, worker = _worker(foundation, sender, "success")

    result = worker.run_once()

    assert result is not None
    assert result.execution_state is ExecutionState.SUCCESS
    assert result.receipt_outcome is ReceiptOutcome.SUCCESS
    assert bridge.call_count == 1
    assert transport.send_call_count == 1
    assert sender.send_count == 1
    assert sender.real_platform_call_count == 0
    assert worker.run_once() is None
    with foundation["uow_factory"]() as uow:
        repo = uow.require_repository()
        execution = repo.get_execution(enqueued.execution_id)
        receipt = repo.get_receipt_for_execution(enqueued.execution_id)
        outbox = repo.list_outbox()
    assert execution.state is ExecutionState.SUCCESS
    assert receipt is not None
    assert receipt.outcome is ReceiptOutcome.SUCCESS
    assert receipt.details["decision_id"] == intake.decision_id
    assert receipt.details["approval_id"] == enqueued.approval_id
    assert receipt.details["approved_by"] == "pdd-send-e2e-human"
    assert receipt.details["trigger_state"] == "TRIGGERED_CONFIRMED"
    assert receipt.details["automatic_retry_allowed"] is False
    assert receipt.details["real_platform_called"] is False
    assert receipt.details["customer_message_sent"] is False
    assert receipt.details["refund_performed"] is False
    assert receipt.details["order_modified"] is False
    event_types = [item.payload["event_type"] for item in outbox]
    assert EventType.EXECUTION_STARTED.value in event_types
    assert EventType.EXECUTION_SUCCEEDED.value in event_types
    assert EventType.RECEIPT_RECORDED.value in event_types


@pytest.mark.parametrize(
    "mode",
    [FakePDDHTTPSenderMode.TIMEOUT, FakePDDHTTPSenderMode.UNKNOWN],
)
def test_worker_unknown_send_is_terminal_and_never_auto_retried(
    foundation,
    mode: FakePDDHTTPSenderMode,
) -> None:
    _intake, enqueued = _enqueue_approved_execution(
        foundation,
        mode.value.lower(),
    )
    sender = FakePDDHTTPSender(mode)
    transport, _bridge, worker = _worker(
        foundation,
        sender,
        mode.value.lower(),
    )

    result = worker.run_once()

    assert result is not None
    assert result.execution_state is ExecutionState.UNKNOWN
    assert result.receipt_outcome is ReceiptOutcome.UNKNOWN
    assert sender.send_count == 1
    assert worker.run_once() is None
    assert sender.send_count == 1
    with foundation["uow_factory"]() as uow:
        repo = uow.require_repository()
        execution = repo.get_execution(enqueued.execution_id)
        receipt = repo.get_receipt_for_execution(enqueued.execution_id)
        outbox = repo.list_outbox()
    assert execution.state is ExecutionState.UNKNOWN
    assert receipt is not None and receipt.outcome is ReceiptOutcome.UNKNOWN
    assert receipt.details["trigger_state"] == "TRIGGERED_UNCONFIRMED"
    assert receipt.details["automatic_retry_allowed"] is False
    assert receipt.details["reconciliation_required"] is True
    assert EventType.EXECUTION_UNKNOWN.value in [
        item.payload["event_type"] for item in outbox
    ]
    assert transport.send_call_count == 1
