from __future__ import annotations

import pytest
from pydantic import ValidationError

from channel_engine.channel import (
    ExecutionBoundaryDenied,
    PDDControlledExecutionAdapter,
    PDDObservedMessage,
    PDDOutboundMode,
)
from channel_engine.conversation import ConversationService
from channel_engine.execution import (
    ExecutionCoordinator,
    ExecutionQueue,
    ExecutionWorker,
)
from channel_engine.models import (
    ApprovalState,
    DecisionState,
    EventType,
    ExecutionState,
    MessageState,
    OutboxState,
    ReceiptOutcome,
)
from channel_engine.models.entities import utc_now
from channel_engine.outbox import FakeEventPublisher, OutboxPublisher
from channel_engine.policy import ApprovalPolicy

from tests.pdd_controlled_support import controlled_adapter, mock_ai_cs_gateway


def observe_and_decide(foundation, adapter, suffix: str, *, mock_ai_cs: bool = False):
    adapter.transport.enqueue(
        PDDObservedMessage(
            platform="pdd",
            conversation_id=f"pdd-controlled-conversation-{suffix}",
            external_message_id=f"pdd-controlled-message-{suffix}",
            sender=f"pdd-controlled-buyer-{suffix}",
            content=f"Please answer this controlled PDD request: {suffix}",
            timestamp=utc_now(),
        )
    )
    adapter.connect()
    inbound = adapter.receive_message()
    assert inbound is not None
    if mock_ai_cs:
        gateway, server = mock_ai_cs_gateway()
    else:
        gateway, server = foundation["gateway"], None
    intake = ConversationService(foundation["uow_factory"], gateway).receive(inbound)
    return intake, server


def approve(foundation, decision_id: str):
    return ExecutionCoordinator(
        foundation["uow_factory"],
        ApprovalPolicy(),
    ).approve_and_enqueue(decision_id, "pdd-controlled-human-operator")


def run_controlled_worker(
    foundation,
    adapter,
    authorization,
    *,
    worker_id: str = "pdd-controlled-worker",
):
    bridge = PDDControlledExecutionAdapter(adapter, authorization)
    worker = ExecutionWorker(
        foundation["uow_factory"],
        bridge,
        worker_id,
    )
    result = worker.run_once()
    assert result is not None
    return worker, bridge, result


def event_types(foundation) -> list[str]:
    with foundation["uow_factory"]() as uow:
        items = uow.require_repository().list_outbox()
    return [str(item.payload["event_type"]) for item in items]


def test_full_pdd_human_approved_fake_send_records_receipt_events_and_outbox(
    foundation,
) -> None:
    adapter, authorization, inbound_transport, outbound_transport = (
        controlled_adapter(foundation)
    )
    intake, mock_server = observe_and_decide(
        foundation,
        adapter,
        "success",
        mock_ai_cs=True,
    )

    assert intake.message_state is MessageState.COMPLETED
    assert intake.decision_state is DecisionState.WAITING_APPROVAL
    assert mock_server is not None and mock_server.decision_compute_count == 1
    assert outbound_transport.send_attempt_count == 0

    enqueued = approve(foundation, intake.decision_id)
    assert enqueued.execution_state is ExecutionState.PENDING
    with foundation["uow_factory"]() as uow:
        repo = uow.require_repository()
        approved_decision = repo.get_decision(intake.decision_id)
        approved_record = repo.get_approval_for_decision(intake.decision_id)
        pending_execution = repo.get_execution(enqueued.execution_id)
    assert approved_decision.state is DecisionState.APPROVED
    assert approved_record is not None
    assert approved_record.state is ApprovalState.APPROVED
    assert pending_execution.state is ExecutionState.PENDING
    worker, bridge, result = run_controlled_worker(
        foundation,
        adapter,
        authorization,
    )

    assert result.execution_state is ExecutionState.SUCCESS
    assert result.receipt_outcome is ReceiptOutcome.SUCCESS
    assert bridge.call_count == 1
    assert outbound_transport.send_attempt_count == 1
    assert outbound_transport.simulated_accept_count == 1
    assert outbound_transport.real_platform_call_count == 0
    assert inbound_transport.real_platform_call_count == 0
    assert worker.run_once() is None

    with foundation["uow_factory"]() as uow:
        repo = uow.require_repository()
        execution = repo.get_execution(enqueued.execution_id)
        receipt = repo.get_receipt_for_execution(enqueued.execution_id)
        outbox = repo.list_outbox()
    assert execution.state is ExecutionState.SUCCESS
    assert receipt is not None
    assert receipt.outcome is ReceiptOutcome.SUCCESS
    assert receipt.external_reference == (
        f"fake-pdd-controlled-{enqueued.execution_id}"
    )
    assert receipt.details["policy"] == "ALLOW_SEND_MESSAGE"
    assert receipt.details["decision_id"] == intake.decision_id
    assert receipt.details["approval_id"] == enqueued.approval_id
    assert receipt.details["approved_by"] == "pdd-controlled-human-operator"
    assert receipt.details["human_approved"] is True
    assert receipt.details["automatic_reply"] is False
    assert receipt.details["real_channel_called"] is False
    assert receipt.details["customer_message_sent"] is False
    assert receipt.details["refund_performed"] is False
    assert receipt.details["order_modified"] is False

    types = event_types(foundation)
    assert EventType.DECISION_APPROVED.value in types
    assert EventType.EXECUTION_STARTED.value in types
    assert EventType.EXECUTION_SUCCEEDED.value in types
    assert EventType.RECEIPT_RECORDED.value in types
    assert len(outbox) == len(types)
    assert all(item.status is OutboxState.PENDING for item in outbox)

    publisher_transport = FakeEventPublisher()
    published = OutboxPublisher(
        foundation["uow_factory"],
        publisher_transport,
        "pdd-controlled-outbox-publisher",
    ).run_until_idle()
    assert len(published) == len(outbox)
    assert all(item.status is OutboxState.PUBLISHED for item in published)
    assert len(publisher_transport.published_events) == len(outbox)

    with pytest.raises(ValidationError, match="frozen"):
        receipt.outcome = ReceiptOutcome.UNKNOWN  # type: ignore[misc]


@pytest.mark.parametrize(
    ("mode", "expected_error"),
    [
        (PDDOutboundMode.TIMEOUT, "PDD_SEND_TIMEOUT_UNKNOWN"),
        (PDDOutboundMode.UNKNOWN, "FAKE_PDD_SEND_UNKNOWN"),
    ],
)
def test_pdd_uncertain_send_becomes_unknown_and_is_not_retried(
    foundation,
    mode: PDDOutboundMode,
    expected_error: str,
) -> None:
    adapter, authorization, _inbound, outbound = controlled_adapter(
        foundation,
        mode,
    )
    intake, _server = observe_and_decide(foundation, adapter, mode.value.lower())
    enqueued = approve(foundation, intake.decision_id)

    worker, _bridge, result = run_controlled_worker(
        foundation,
        adapter,
        authorization,
        worker_id=f"pdd-{mode.value.lower()}-worker",
    )

    assert result.execution_state is ExecutionState.UNKNOWN
    assert result.receipt_outcome is ReceiptOutcome.UNKNOWN
    assert outbound.send_attempt_count == 1
    assert worker.run_once() is None
    assert outbound.send_attempt_count == 1
    with foundation["uow_factory"]() as uow:
        repo = uow.require_repository()
        execution = repo.get_execution(enqueued.execution_id)
        receipt = repo.get_receipt_for_execution(enqueued.execution_id)
    assert execution.state is ExecutionState.UNKNOWN
    assert receipt is not None and receipt.outcome is ReceiptOutcome.UNKNOWN
    assert receipt.details["error_code"] == expected_error
    assert EventType.EXECUTION_UNKNOWN.value in event_types(foundation)


def test_pdd_failed_send_records_failed_receipt(foundation) -> None:
    adapter, authorization, _inbound, outbound = controlled_adapter(
        foundation,
        PDDOutboundMode.FAILED,
    )
    intake, _server = observe_and_decide(foundation, adapter, "failed")
    enqueued = approve(foundation, intake.decision_id)

    _worker, _bridge, result = run_controlled_worker(
        foundation,
        adapter,
        authorization,
        worker_id="pdd-failed-worker",
    )

    assert result.execution_state is ExecutionState.FAILED
    assert result.receipt_outcome is ReceiptOutcome.FAILED
    assert outbound.send_attempt_count == 1
    with foundation["uow_factory"]() as uow:
        receipt = uow.require_repository().get_receipt_for_execution(
            enqueued.execution_id
        )
    assert receipt is not None
    assert receipt.details["error_code"] == "FAKE_PDD_SEND_REJECTED"
    assert EventType.EXECUTION_FAILED.value in event_types(foundation)


def test_duplicate_send_replays_one_fake_transport_result(foundation) -> None:
    adapter, authorization, _inbound, outbound = controlled_adapter(foundation)
    intake, _server = observe_and_decide(foundation, adapter, "duplicate")
    enqueued = approve(foundation, intake.decision_id)
    queue = ExecutionQueue(
        foundation["uow_factory"],
        "pdd-duplicate-worker",
    )
    lease = queue.claim()
    assert lease is not None
    command = authorization.issue(
        execution_id=enqueued.execution_id,
        worker_id=lease.worker_id,
        execution_lease_token=lease.lease_token,
    )

    first = adapter.send_message(command)
    replay = adapter.send_message(command)

    assert replay == first
    assert first.outcome is ReceiptOutcome.SUCCESS
    assert adapter.send_call_count == 1
    assert outbound.send_attempt_count == 1
    assert outbound.simulated_accept_count == 1
    assert outbound.real_platform_call_count == 0

    tampered = command.model_copy(
        update={
            "message": command.message.model_copy(
                update={"content": "A different, unapproved message."}
            )
        }
    )
    with pytest.raises(ExecutionBoundaryDenied, match="does not match"):
        adapter.send_message(tampered)
    assert outbound.send_attempt_count == 1


def test_waiting_approval_never_enqueues_or_sends(foundation) -> None:
    adapter, authorization, _inbound, outbound = controlled_adapter(foundation)
    intake, _server = observe_and_decide(
        foundation,
        adapter,
        "approval-missing",
    )
    bridge = PDDControlledExecutionAdapter(adapter, authorization)
    worker = ExecutionWorker(
        foundation["uow_factory"],
        bridge,
        "pdd-no-approval-worker",
    )

    assert intake.decision_state is DecisionState.WAITING_APPROVAL
    assert worker.run_once() is None
    assert bridge.call_count == 0
    assert adapter.send_call_count == 0
    assert outbound.send_attempt_count == 0
    with foundation["uow_factory"]() as uow:
        repo = uow.require_repository()
        assert repo.get_approval_for_decision(intake.decision_id) is None
        assert repo.get_execution_for_decision(intake.decision_id) is None
